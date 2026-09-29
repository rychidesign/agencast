"""Static checks before a run (scenario.md §7). All errors have class `config`
and are reported together.
"""
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import ConfigErrors, AgencastError
from .expressions import ExprError, infer, kind, parse, template_type, tkind
from .loader import (LoadError, load_yaml, nested_lists, read_frontmatter, read_yaml, scenario_schema_errors,
                     schema_errors, seconds, step_kind, version_error)
from .mcp_client import api_name, load_mcp, secret_names
from .providers import DEFAULT_BASE_URL, list_image_models, list_models, shape_type

NOOUT = "no output"  # type of parallel/switch/fail/output steps
DEFAULT_TIMEOUT = {"ask": "2m", "task": "15m", "jev": "30s", "image": "3m"}  # scenario.md §3 (draft)
# Fields that allow {{ }} templates (scenario.md §5); "*" = any key/index.
TEMPLATE_FIELDS = [("ask", "prompt"), ("task", "prompt"), ("image", "prompt"), ("jev", "state"),
                   ("image", "aspect_ratio"), ("image", "quality"), ("image", "resolution"),
                   ("jev", "questions", "*", "instructions"), ("jev", "questions", "*", "criteria", "*"),
                   ("fail",), ("output", "*"), ("call", "inputs", "*"), ("dedupe_key",)]
INPUT_TYPES = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean",
               "list": "list", "object": "object", "file": "file"}


@dataclass
class Agent:
    name: str
    data: dict
    body: str
    skills: list  # [(name, description, body)]


@dataclass
class StepInfo:
    id: str
    kind: str
    nn: int          # depth-first order in the file (run-record.md <nn>)
    data: dict
    cond: frozenset  # conditions that may prevent the step from running
    anc: frozenset   # ancestor conditions (references within the same branch are valid)
    out: object = None
    dir: str = ""    # 3b: call step directory for a callee step ("steps/03-propose/"), with id as path "propose/copy"

    @property
    def key(self) -> str:
        """ID in the scenario file — the output key used in expressions (`steps.<key>`)."""
        return self.id.rsplit("/", 1)[-1]

    @property
    def folder(self) -> str:
        return f"{self.dir}steps/{self.nn:02d}-{self.key}"


@dataclass
class Project:
    """A validated scenario with everything the engine needs."""
    scenario_path: Path
    workflows: Path
    scenario: dict
    config: dict
    agents: dict[str, Agent]
    steps: dict[str, StepInfo]
    order: list[StepInfo] = field(default_factory=list)
    callees: dict[str, "Project"] = field(default_factory=dict)  # 3b: scenarios invoked by call steps, by name
    mcp: dict = field(default_factory=dict)  # servers from mcp.yaml

    @property
    def base(self) -> Path:
        """Project root (above workflows/); base for relative runs_dir and storage.local.path."""
        return self.workflows.parent

    @property
    def runs_dir(self) -> Path:
        return self.base / self.config["runs_dir"]


# --- config.yaml ----------------------------------------------------------------

def env_fields(obj, path=()) -> list[tuple[str, str]]:
    """(path, NAME) for all `*_env` fields."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.endswith("_env") and isinstance(v, str):
                out.append((".".join(path + (k,)), v))
            else:
                out += env_fields(v, path + (str(k),))
    return out


def load_config(workflows: Path, errs: list) -> dict | None:
    p = workflows / "config.yaml"
    if not p.is_file():
        errs.append(f"{p}: missing — copy workflows/config.example.yaml to config.yaml and edit it (project owner only)")
        return None
    try:
        text = p.read_text(encoding="utf-8")
        c = load_yaml(text, "config.yaml")
    except LoadError as e:
        errs.append(str(e))
        return None
    if v := version_error(c, "config.yaml"):
        errs.append(v)
        return None
    if e := schema_errors("config", c, "config.yaml", source=text):
        errs.extend(e)
        return None
    seen = {}
    for path, name in env_fields(c):
        if name in seen:
            errs.append(f"config.yaml: {seen[name]} and {path} use the same variable {name} — "
                        "each secret must have its own variable")
        seen[name] = path
    c["openrouter"].setdefault("base_url", DEFAULT_BASE_URL)
    c["openrouter"].setdefault("jev_model", "jev-1.13")
    c.setdefault("runs_dir", "./runs")
    c["limits"].setdefault("max_call_depth", 3)
    return c


def require_config(workflows: Path) -> dict:
    """`load_config`, errors → ConfigErrors."""
    errs = []
    c = load_config(workflows, errs)
    if errs:
        raise ConfigErrors(errs)
    return c


# --- agents and skills ------------------------------------------------------------

def in_subdir(wf: Path, d: str, fname: str) -> str:
    """Suffix for 'does not exist': the file is one level down in an ignored subfolder."""
    hit = next(iter(sorted((wf / d).glob(f"*/{fname}"))), None)
    return f" (file is in subfolder {d}/{hit.parent.name}/, subfolders are not read)" if hit else ""


def load_skill(wf: Path, name: str, errs: list, ref: str):
    where = f"skills/{name}/SKILL.md"
    p = wf / where
    if not p.is_file():
        errs.append(f"{ref}: skill '{name}' does not exist ({where})")
        return None
    try:
        fm, body = read_frontmatter(p, where)
    except LoadError as e:
        errs.append(str(e))
        return None
    if e := schema_errors("skill", fm, where):
        errs.extend(e)
        return None
    if fm["name"] != name:
        errs.append(f"{where}: name '{fm['name']}' does not match the folder name")
    if not body.strip():
        errs.append(f"{where}: skill body is empty")
    return name, fm["description"], body


def load_agent(wf: Path, name: str, config: dict, errs: list, ref: str | None = None,
               mcp: dict | None = None) -> Agent | None:
    where = f"agents/{name}.md"
    p = wf / where
    if not p.is_file():
        errs.append(f"{ref + ': ' if ref else ''}agent '{name}' does not exist ({where})"
                    + in_subdir(wf, "agents", f"{name}.md"))
        return None
    try:
        fm, body = read_frontmatter(p, where)
    except LoadError as e:
        errs.append(str(e))
        return None
    if v := version_error(fm, where):
        errs.append(v)
        return None
    alias = f"{where}: model '{fm.get('model')}' is not an alias in config.yaml (aliases: {', '.join(config['models'])})"
    if e := schema_errors("agent", fm, where):  # model ID instead of alias: report the alias error, not the schema regex
        errs.extend(alias if x.startswith(f"{where}: model: ") else x for x in e)
        return None
    n = len(errs)
    if fm["name"] != name:
        errs.append(f"{where}: name '{fm['name']}' does not match the file name")
    if not body.strip():
        errs.append(f"{where}: body (agent instructions) is empty")
    if fm["model"] not in config["models"]:
        errs.append(alias)
    if set(fm.get("tools", {})) != set(fm.get("mcp", [])):
        errs.append(f"{where}: tools keys must exactly match the servers in mcp")
    servers = load_mcp(wf, errs) if mcp is None else mcp
    for srv in fm.get("mcp", []):  # the project owner controls permissions in mcp.yaml (config.md, §5.2)
        s = servers.get(srv)
        if s is None:
            errs.append(f"{where}: MCP server '{srv}' is not in workflows/mcp.yaml (only the project owner can edit the registry, "
                        "see mcp.example.yaml)")
        elif name not in s["agents"]:
            errs.append(f"{where}: the project owner has not allowed server '{srv}' for agent '{name}' "
                        f"(mcp.yaml → servers.{srv}.agents: {', '.join(s['agents'])})")
        elif "tools" in s and (extra := [t for t in fm.get("tools", {}).get(srv, []) if t not in s["tools"]]):
            errs.append(f"{where}: the project owner has not allowed tools {', '.join(extra)} on server '{srv}' "
                        f"(mcp.yaml → servers.{srv}.tools: {', '.join(s['tools'])})")
    skills = [s for s in (load_skill(wf, s, errs, where) for s in fm.get("skills", [])) if s]
    return Agent(name, fm, body, skills) if len(errs) == n else None


def effective_tools(agent: dict, task: dict) -> dict[str, list]:
    """Tools a task step may use: step ⊆ agent (§5.2); validation prevents steps from expanding permissions."""
    servers = task.get("mcp", agent.get("mcp", []))
    return {s: (task.get("tools") or {}).get(s, agent.get("tools", {}).get(s, [])) for s in servers}


def mcp_servers_used(p: "Project") -> set[str]:
    """Servers a run may start: effective sets for all task steps (including called scenarios)."""
    projects, used = [p], set()
    while projects:
        q = projects.pop()
        projects += q.callees.values()
        used |= {s for st in q.steps.values() if st.kind == "task"
                 for s in effective_tools(q.agents[st.data["task"]["agent"]].data, st.data["task"])}
    return used


# --- inputs -----------------------------------------------------------------------

def _matches(t: str, v) -> bool:
    if t == "integer":
        return kind(v) == "number" and float(v).is_integer()
    return kind(v) == INPUT_TYPES[t]


def resolve_inputs(scenario: dict, given: dict, from_text: bool = False) -> dict:
    """Run inputs with defaults applied; errors prevent the run from starting (scenario.md inputs)."""
    import json
    specs, errs, out = scenario.get("inputs") or {}, [], {}
    for name in given:
        if name not in specs:
            errs.append(f"unknown input '{name}' (scenario has: {', '.join(specs) or 'no inputs'})")
    for name, sp in specs.items():
        t = sp["type"]
        if name not in given:
            if sp.get("required"):
                errs.append(f"missing required input '{name}' ({t})")
            else:
                out[name] = sp["default"]
            continue
        v = given[name]
        if t == "file":
            errs.append(f"input '{name}' has type file — it can only be passed via call, not the CLI or a webhook")
            continue
        if from_text and t != "string":
            try:
                v = json.loads(v)
            except ValueError:
                pass
        if not _matches(t, v):
            errs.append(f"input '{name}' must be {t}, got {kind(v)}")
        out[name] = v
    if errs:
        raise ConfigErrors(errs)
    return out


# --- scenario -----------------------------------------------------------------------

def validate(scenario_path, *, transport=None, check_models: bool = True) -> Project:
    """Load and validate a scenario, config, agents and skills. Errors → ConfigErrors."""
    path = Path(scenario_path).resolve()
    where = path.name
    if not path.is_file():
        raise ConfigErrors([f"{scenario_path}: file does not exist"])
    if path.parent.name != "scenarios":
        raise ConfigErrors([f"{scenario_path}: only scenarios stored directly in the folder can run: "
                            "workflows/scenarios/ — move it there (subfolders such as archive/ are ignored)"])
    wf = path.parent.parent
    errs = []
    config = load_config(wf, errs)
    sc = _read_scenario(path, errs)
    if errs or config is None:
        raise ConfigErrors(errs)
    chk = _Checker(sc, config, wf, where)
    chk.run()
    errs += chk.errs
    if not errs and check_models:
        try:
            models = list_models(config["openrouter"]["base_url"], wf.parent / config["runs_dir"], transport)
        except AgencastError as e:
            raise ConfigErrors([f"{e.cls}: {e.message}"]) from None
        models_by_id = {m["id"] for m in models}
        needs_images = any(
            (config["models"][alias].get("api", "chat") == "images" and "image" in need)
            or (config["models"][alias].get("api", "chat") == "chat"
                and config["models"][alias]["id"] not in models_by_id)
            for alias, need in chk.model_needs.items())
        image_models = []
        if needs_images:
            try:
                image_models = list_image_models(config["openrouter"]["base_url"],
                                                 wf.parent / config["runs_dir"], transport)
            except AgencastError as e:
                raise ConfigErrors([f"{e.cls}: {e.message}"]) from None
        errs += check_models_list(config, chk.model_needs, models, image_models)
    if errs:
        raise ConfigErrors(errs)
    return chk.project(path)


def _read_scenario(path: Path, errs: list) -> dict | None:
    """Scenario file: YAML, version, JSON Schema, name = file. Append errors to `errs`."""
    where = path.name
    try:
        sc = read_yaml(path, where)
    except LoadError as e:
        errs.append(str(e))
        return None
    if v := version_error(sc, where):
        errs.append(v)
        return None
    n = len(errs)
    errs += scenario_schema_errors(sc, where)
    if sc.get("name") != path.stem:
        errs.append(f"{where}: name '{sc.get('name')}' does not match the file name")
    return sc if len(errs) == n else None


def check_models_list(config: dict, needs: dict, models: list, image_models: list = ()) -> list[str]:
    """Check aliases against GET /models or /images/models (scenario.md §7, §5.5, §5.7)."""
    by_id, image_by_id, errs = {m["id"]: m for m in models}, {m["id"]: m for m in image_models}, []
    for alias, need in sorted(needs.items()):
        model, mid = config["models"][alias], config["models"][alias]["id"]
        images_api = model.get("api", "chat") == "images"
        if images_api and "image" in need:
            m = image_by_id.get(mid)
            if not m:
                errs.append(f"config.yaml: models.{alias}.id '{mid}' is not in GET /images/models")
            else:
                if "image" not in m["output_modalities"]:
                    errs.append(f"config.yaml: model '{mid}' (alias {alias}) does not support image output")
                for requirement in need - {"image"}:
                    parameter, _, requested = requirement.partition(":")
                    if parameter not in ("aspect_ratio", "quality", "resolution"):
                        continue
                    value, _, source = requested.partition("\t")
                    supported = m["supported_parameters"].get(parameter) or {}
                    values = supported.get("values") if isinstance(supported, dict) else None
                    if values is not None and value not in values:
                        errs.append(f"config.yaml: model '{mid}' (alias {alias}) does not support {parameter} {value}"
                                    + (f" ({source})" if source else ""))
        chat_need = need - {"image"} - {n for n in need if n.startswith(
            ("aspect_ratio:", "quality:", "resolution:"))} if images_api else need
        if not chat_need:
            continue
        m = by_id.get(mid)
        if not m:
            if not images_api and "image" in need and mid in image_by_id:
                errs.append(f"config.yaml: model '{mid}' (alias {alias}) is only available in the Images API — "
                            f"set models.{alias}.api: images")
                continue
            errs.append(f"config.yaml: models.{alias}.id '{mid}' is not in GET /models — typo? "
                        "(e.g. claude-haiku-4.5, not -4-5)")
            continue
        if "image" in chat_need and "image" not in m["output_modalities"]:
            errs.append(f"config.yaml: model '{mid}' (alias {alias}) does not support image output")
        if "tools" in chat_need and "tools" not in m["supported_parameters"]:
            errs.append(f"config.yaml: model '{mid}' (alias {alias}) does not support tools — an agent using it cannot run in a task step")
        if "schema" in chat_need and not {"structured_outputs", "tools"} & set(m["supported_parameters"]):
            errs.append(f"config.yaml: model '{mid}' (alias {alias}) supports neither structured_outputs nor tools — "
                        "the step's schema could not be enforced")
    return errs


def _strings(obj, path=(), skip=()):
    """(path, text) for all strings, including keys; `skip` = nested step lists."""
    if path in skip:
        return
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield path + (k, "#key"), k
            yield from _strings(v, path + (k,), skip)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, path + (i,), skip)


def _template_field(p) -> bool:
    return any(len(p) == len(f) and all(a == "*" or a == b for a, b in zip(f, p)) for f in TEMPLATE_FIELDS)


class _Checker:
    def __init__(self, sc: dict, config: dict, wf: Path, where: str, stack: tuple = (), model_needs=None):
        self.sc, self.config, self.wf, self.where = sc, config, wf, where
        self.stack = stack + (sc["name"],)  # 3b: call chain from the top-level scenario (cycles, depth)
        self.errs: list[str] = []
        self.steps: dict[str, StepInfo] = {}
        self.order: list[StepInfo] = []
        self.agents: dict[str, Agent | None] = {}
        self.callees: dict[str, Project] = {}
        self.model_needs: dict[str, set] = {} if model_needs is None else model_needs
        self.inputs_type = {k: INPUT_TYPES[v["type"]] for k, v in (sc.get("inputs") or {}).items()}
        self.mcp = load_mcp(wf, self.errs)
        own = {name: path for path, name in env_fields(config)}
        for name in secret_names(self.mcp):  # a config.yaml key would be sent to an MCP server (e.g. OPENROUTER_API_KEY)
            if name in own:
                self.errs.append(f"mcp.yaml: variable {name} is already used in config.yaml ({own[name]}) — "
                                 "the MCP server must have its own secret")

    def project(self, path: Path) -> Project:
        return Project(path, self.wf, self.sc, self.config, self.agents, self.steps, self.order, self.callees, self.mcp)

    def err(self, step, fld, msg):
        prefix = f'{self.where}: step "{step}"' if step else self.where
        self.errs.append(f"{prefix}, {fld}: {msg}" if fld else f"{prefix}: {msg}")

    def run(self):
        for name, sp in (self.sc.get("inputs") or {}).items():
            if "default" in sp and not _matches(sp["type"], sp["default"]):
                self.err(None, f"inputs.{name}.default", f"value does not match type {sp['type']}")
        self.number(self.sc["steps"], frozenset(), frozenset())
        header = {k: v for k, v in self.sc.items() if k != "steps"}
        for p, s in _strings(header):
            if "{{" in s:
                self.err(None, ".".join(map(str, p)), "template {{ }} is not allowed in the scenario header")
        for info in self.order:
            skip = {p for p, _ in nested_lists(info.data)}
            for p, s in _strings(info.data, skip=skip):
                if "{{" in s and not _template_field(p):
                    line = s.replace("\n", " ")
                    self.err(info.id, ".".join(map(str, p)).replace(".#key", " (key)"),
                             str(ExprError("template {{ }} is not allowed here — allowed only in prompt, jev.state, "
                                           "jev.questions (instructions, criteria), fail, output values, "
                                           "call.inputs and dedupe_key", line.index("{{"), line)))
        self.walk(self.sc["steps"], {}, top=True)
        outs = self.sc.get("outputs") or {}
        if len(self.stack) == 1 and self.config["storage"]["type"] == "r2" and any(o["type"] == "file" for o in outs.values()):
            self.err(None, None, "file output requires storage, but the framework does not yet support storage.type: r2 "
                                 "— set storage.type: local in config.yaml")
        last = self.sc["steps"][-1]
        if self.sc.get("outputs") and step_kind(last) != "output":
            self.err(None, None, "scenario has outputs, but the last step is not output")

    # -- first pass: numbers, unique IDs, conditions --
    def number(self, steps, anc, cond):
        for st in steps:
            sid, k = st["id"], step_kind(st)
            own = frozenset({sid}) if ("when" in st or st.get("on_error") == "continue") else frozenset()
            info = StepInfo(sid, k, len(self.order) + 1, st, cond | own, anc)
            self.order.append(info)
            if sid in self.steps:
                self.err(sid, None, "id is not unique (must be unique across the entire file, including branches)")
            else:
                self.steps[sid] = info
            for p, lst in nested_lists(st):
                frame = frozenset({f"{sid}:{'/'.join(p)}"})
                self.number(lst, anc | own | frame, cond | own | (frame if k == "switch" else frozenset()))

    def why(self, x: StepInfo) -> str:
        reasons = []
        for c in sorted(x.cond):
            if c == x.id:
                reasons.append("has when" if "when" in x.data else "has on_error: continue")
            elif ":switch/" in c:
                reasons.append(f"is in a switch branch '{c.split(':')[0]}'")
            else:
                reasons.append(f"is inside step '{c}', which may not run")
        return ", ".join(reasons)

    def resolver(self, scope: dict, r: StepInfo):
        def resolve(key):
            x = self.steps.get(key)
            if x is r:
                raise ExprError(f"step '{key}' cannot read its own output")
            if x and x.kind in ("parallel", "switch", "fail", "output"):
                raise ExprError(f"step '{key}' ({x.kind}) has no output — its nested steps have outputs")
            if key in scope:
                if not x.cond <= r.anc and "default" not in x.data:
                    raise ExprError(f"step '{key}' may not run ({self.why(x)}) and has no default — add a "
                                    "default with all output fields (§5.4)")
                return scope[key]
            if x and x.nn > r.nn:
                raise ExprError(f"step '{key}' comes later — expressions can only reference preceding steps")
            if x:
                raise ExprError(f"step '{key}' is in another parallel branch — completion order is unknown")
            avail = [k for k, v in scope.items() if v is not NOOUT]
            raise ExprError(f"step '{key}' does not exist (available: {', '.join(avail) or '—'})")
        return resolve

    def expr_type(self, info, fld, expr, res, want=None):
        if "{{" in expr:
            return None  # already reported in run(): templates are not allowed in expressions
        try:
            t = infer(expr, self.inputs_type, res)
        except ExprError as e:
            self.err(info.id, fld, str(e))
            return None
        if want and tkind(t) and tkind(t) != want:
            self.err(info.id, fld, f"expression must return {'true/false' if want == 'boolean' else want}, got {tkind(t)}"
                                   f"\n  {expr}")
        return t

    def template(self, info, fld, s, res):
        try:
            return template_type(s, self.inputs_type, res)
        except ExprError as e:
            self.err(info.id, fld, str(e))
            return None

    def need(self, alias, what=None):
        self.model_needs.setdefault(alias, set()).update({what} if what else set())

    # -- second pass: references, types, templates, step rules --
    def walk(self, steps, scope, top=False):
        added = {}
        for i, st in enumerate(steps):
            info = self.steps.get(st["id"])
            if info is None or info.data is not st:
                continue  # duplicate id, already reported
            sid, k = info.id, info.kind
            res = self.resolver(scope, info)
            if "when" in st:
                self.expr_type(info, "when", st["when"], res, want="boolean")
            out = NOOUT
            if k in ("ask", "task", "jev", "image", "call"):
                out = getattr(self, k)(info, res)
            elif k == "set":
                out = {n: self.expr_type(info, f"set.{n}", v, res) if isinstance(v, str) else kind(v)
                       for n, v in st["set"].items()}
            elif k == "fail":
                self.template(info, "fail", st["fail"], res)
            elif k == "output":
                self.output(info, res, last=top and i == len(steps) - 1)
            elif k in ("parallel", "switch"):
                if k == "switch":
                    self.expr_type(info, "switch.value", st["switch"]["value"], res, want="string")
                    self.switch_cases(info)
                merged = {}
                for _, lst in nested_lists(st):
                    merged.update(self.walk(lst, dict(scope)))
                scope.update(merged)
                added.update(merged)
            if k == "fail" and "when" not in st and i < len(steps) - 1:
                self.err(steps[i + 1].get("id"), None, f"step is unreachable — preceded by unconditional fail '{sid}'")
            if "default" in st and isinstance(out, dict):
                self.check_default(info, out)
            info.out = out
            scope[sid] = added[sid] = out
        return added

    def agent(self, name, info) -> Agent | None:
        if name not in self.agents:
            self.agents[name] = load_agent(self.wf, name, self.config, self.errs, f'{self.where}: step "{info.id}"',
                                           self.mcp)
        return self.agents[name]

    def ask(self, info, res, k="ask"):
        st, a = info.data, info.data[k]
        self.template(info, f"{k}.prompt", a["prompt"], res)
        agent = self.agent(a["agent"], info)
        if agent:
            self.need(agent.data["model"], "schema" if "schema" in a else None)
            lim = agent.data["limits"]
            if st.get("budget_usd", 0) > lim["budget_usd"]:
                self.err(info.id, "budget_usd", f"{st['budget_usd']} exceeds limits.budget_usd of agent "
                                                f"'{agent.name}' ({lim['budget_usd']}) — steps may only lower limits")
            if "timeout" in st and "timeout" in lim and seconds(st["timeout"]) > seconds(lim["timeout"]):
                self.err(info.id, "timeout", f"{st['timeout']} exceeds limits.timeout of agent '{agent.name}' "
                                             f"({lim['timeout']}) — steps may only lower limits")
        return shape_type(a["schema"]) if "schema" in a else {"text": "string"}

    def task(self, info, res):
        """Task step: limits and permissions step ⊆ agent ⊆ mcp.yaml (agent.md Permissions, §5.2, §5.8)."""
        st, t = info.data, info.data["task"]
        out = self.ask(info, res, "task")
        if "dedupe_key" in st:
            self.template(info, "dedupe_key", st["dedupe_key"], res)
        agent = self.agents.get(t["agent"])
        if not agent:
            return out
        a, name = agent.data, agent.name
        self.need(a["model"], "tools")
        if "max_turns" not in a["limits"]:
            self.err(info.id, "task.agent", f"agent '{name}' has no limits.max_turns — task requires a turn limit (§5.1)")
        elif t.get("max_turns", 0) > a["limits"]["max_turns"]:
            self.err(info.id, "task.max_turns", f"{t['max_turns']} exceeds limits.max_turns of agent '{name}' "
                                                f"({a['limits']['max_turns']}) — steps may only lower limits")
        for srv in t.get("mcp", []):
            if srv not in a.get("mcp", []):
                self.err(info.id, "task.mcp", f"server '{srv}' is not allowed by agent '{name}' (mcp: "
                                              f"{', '.join(a.get('mcp', [])) or '—'}) — steps may only narrow permissions")
        eff = effective_tools(a, t)
        for srv, tools in (t.get("tools") or {}).items():
            if srv not in eff:
                self.err(info.id, f"task.tools.{srv}", f"server '{srv}' is not used by this step (task.mcp / agent mcp)")
                continue
            for tool in tools:
                if tool not in a.get("tools", {}).get(srv, []):
                    self.err(info.id, "task.tools", f"step requests tool {srv}.{tool}, which agent '{name}' does not allow "
                                                    f"(tools.{srv})")
        names = {}
        for srv, tools in eff.items():
            s = self.mcp.get(srv)
            if s and "scenarios" in s and self.sc["name"] not in s["scenarios"]:
                self.err(info.id, None, f"scenario '{self.sc['name']}' cannot run an agent with server '{srv}' "
                                        f"(mcp.yaml → servers.{srv}.scenarios: {', '.join(s['scenarios'])})")
            for tool in tools:
                n = api_name(srv, tool)
                if n in names and names[n] != (srv, tool):
                    self.err(info.id, None, f"tools {'.'.join(names[n])} and {srv}.{tool} have "
                                            f"the same normalized name {n} (only [a-zA-Z0-9_-], max 64 characters)")
                names[n] = (srv, tool)
        return out

    def jev(self, info, res):
        j = info.data["jev"]
        self.template(info, "jev.state", j["state"], res)
        out, details = {}, {}
        for q, spec in j["questions"].items():
            self.template(info, f"jev.questions.{q}.instructions", spec["instructions"], res)
            crit = spec.get("criteria") or []
            for c, text in (crit.items() if isinstance(crit, dict) else enumerate(crit)):
                self.template(info, f"jev.questions.{q}.criteria.{c}", text, res)
            out[q] = "string" if spec["type"] == "choice" else "number"
            details[q] = "object"
        return {**out, "details": details}

    def image(self, info, res):
        im = info.data["image"]
        if im["model"] not in self.config["models"]:
            self.err(info.id, "image.model", f"'{im['model']}' is not an alias in config.yaml "
                                             f"(aliases: {', '.join(self.config['models'])})")
        else:
            self.need(im["model"], "image")
        for field, pattern in (("aspect_ratio", r"[1-9][0-9]*:[1-9][0-9]*"),
                               ("quality", r"auto|low|medium|high"), ("resolution", r"512|1K|2K|4K")):
            value = im.get(field, self.config["models"].get(im["model"], {}).get("quality")
                           if field == "quality" else None)
            if value is None:
                continue
            source = ""
            if "{{" in value:
                typ = tkind(self.template(info, f"image.{field}", value, res))
                if typ and typ != "string":
                    self.err(info.id, f"image.{field}", f"template must return a string, got {typ}")
                ref = re.fullmatch(r"\{\{\s*inputs\.([a-z][a-z0-9_]*)\s*\}\}", value)
                spec = (self.sc.get("inputs") or {}).get(ref[1], {}) if ref else {}
                if "default" not in spec:
                    continue
                value, source = spec["default"], f"input default for {ref[1]}"
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                self.err(info.id, f"image.{field}", f"invalid value {value!r}"
                         + (f" ({source})" if source else ""))
            elif im["model"] in self.config["models"]:
                self.need(im["model"], f"{field}:{value}" + (f"\t{source}" if source else ""))
        self.template(info, "image.prompt", im["prompt"], res)
        return {"file": "file"}

    def call(self, info, res):
        """Call step (scenario.md call, §5.3): called scenario, its inputs and outputs."""
        c = info.data["call"]
        given = c.get("inputs") or {}
        types = {k: self.template(info, f"call.inputs.{k}", v, res) if isinstance(v, str) else kind(v)
                 for k, v in given.items()}
        callee = self.callee(c["scenario"], info)
        if callee is None:
            return None
        specs, name = callee.scenario.get("inputs") or {}, c["scenario"]
        if extra := [k for k in given if k not in specs]:
            self.err(info.id, "call.inputs", f"scenario '{name}' has no inputs named: {', '.join(extra)} "
                                             f"(has: {', '.join(specs) or 'none'})")
        if missing := [k for k, sp in specs.items() if sp.get("required") and k not in given]:
            self.err(info.id, "call.inputs", f"missing required inputs for scenario '{name}': {', '.join(missing)}")
        for k, t in types.items():
            if k in specs and tkind(t) and tkind(t) != INPUT_TYPES[specs[k]["type"]]:
                self.err(info.id, f"call.inputs.{k}", f"input has type {specs[k]['type']}, value is {tkind(t)}")
        return {k: INPUT_TYPES[o["type"]] for k, o in (callee.scenario.get("outputs") or {}).items()}

    def callee(self, name: str, info) -> Project | None:
        """Validate a called scenario recursively; cycles and excessive depth are config errors."""
        path = self.wf / "scenarios" / f"{name}.yaml"
        if not path.is_file():
            self.err(info.id, "call.scenario", f"scenario '{name}' does not exist (scenarios/{name}.yaml)"
                     + in_subdir(self.wf, "scenarios", f"{name}.yaml"))
            return None
        if name in self.stack:
            self.err(info.id, "call.scenario", f"call cycle: {' → '.join(self.stack + (name,))}")
            return None
        depth, limit = len(self.stack), self.config["limits"]["max_call_depth"]
        if depth > limit:
            self.err(info.id, "call.scenario", f"call depth {depth} exceeds limits.max_call_depth ({limit}): "
                                               f"{' → '.join(self.stack + (name,))}")
            return None
        errs = []
        sc = _read_scenario(path, errs)
        self.errs += errs
        if sc is None:
            return None
        if sc.get("callable") is not True:
            self.err(info.id, "call.scenario", f"scenario '{name}' has no callable: true — it cannot be called "
                                               "(protects approval in n8n, §5.2)")
            return None
        chk = _Checker(sc, self.config, self.wf, path.name, self.stack, self.model_needs)
        chk.run()
        self.errs += chk.errs
        self.callees[name] = chk.project(path)
        return self.callees[name]

    def switch_cases(self, info):
        sw = info.data["switch"]
        try:
            tree = parse(sw["value"])
        except ExprError:
            return  # already reported
        match tree:
            case ast.Attribute(value=ast.Attribute(value=ast.Name(id="steps"), attr=sid), attr=q):
                x = self.steps.get(sid)
                spec = x.data["jev"]["questions"].get(q) if x and x.kind == "jev" else None
                if spec and spec["type"] == "choice":
                    extra = [c for c in sw["cases"] if c not in spec["criteria"]]
                    if extra:
                        self.err(info.id, "switch.cases", f"{', '.join(extra)} is not among the criteria choices for "
                                                          f"question '{q}' ({', '.join(spec['criteria'])})")

    def check_default(self, info, out: dict):
        d = info.data["default"]
        fields = {k: v for k, v in out.items() if not (info.kind == "jev" and k == "details")}
        missing = [k for k in fields if k not in d]
        extra = [k for k in d if k not in out]
        if missing:
            self.err(info.id, "default", f"must contain all output fields, missing: {', '.join(missing)}")
        if extra:
            self.err(info.id, "default", f"fields not returned by the step: {', '.join(extra)}")
        for k, v in d.items():
            want = tkind(fields.get(k))
            if want and v is not None and kind(v) != want:
                self.err(info.id, f"default.{k}", f"expected {want} or null, got {kind(v)}")

    def output(self, info, res, last):
        if not last:
            self.err(info.id, None, "output is allowed only once and only as the last step in the main steps list")
        outs = self.sc.get("outputs")
        if not outs:
            self.err(info.id, None, "scenario without outputs cannot have an output step — add outputs to the header")
            return
        o = info.data["output"]
        if missing := [k for k in outs if k not in o]:
            self.err(info.id, "output", f"missing outputs declared in the header: {', '.join(missing)}")
        if extra := [k for k in o if k not in outs]:
            self.err(info.id, "output", f"outputs not declared in the header: {', '.join(extra)}")
        for k, v in o.items():
            if k not in outs:
                continue
            want = outs[k]["type"]
            t = tkind(self.template(info, f"output.{k}", v, res) if isinstance(v, str) else kind(v))
            if want == "file" and t and t != "file":
                self.err(info.id, f"output.{k}", "file output must be a template referencing a file from an image step "
                                                 f"(e.g. {{{{ steps.photo.file }}}}), not {t}")
            elif want != "file" and t and t != INPUT_TYPES[want]:
                self.err(info.id, f"output.{k}", f"output has type {want}, value is {t}")
