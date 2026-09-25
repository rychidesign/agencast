"""Statické kontroly před během (scenario.md §7). Všechno je třída `config`
a hlásí se všechny chyby najednou.
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path

from . import ConfigErrors, MawError
from .expressions import ExprError, infer, kind, parse, template_type, tkind
from .loader import (LoadError, nested_lists, read_frontmatter, read_yaml, scenario_schema_errors,
                     schema_errors, seconds, step_kind, version_error)
from .mcp_client import api_name, load_mcp, secret_names
from .providers import DEFAULT_BASE_URL, list_models, shape_type

NOOUT = "bez výstupu"  # typ kroku parallel/switch/fail/output
DEFAULT_TIMEOUT = {"ask": "2m", "task": "15m", "jev": "30s", "image": "3m"}  # scenario.md §3 (návrh)
# Kde smí být šablona {{ }} (scenario.md §5); "*" = libovolný klíč/index.
TEMPLATE_FIELDS = [("ask", "prompt"), ("task", "prompt"), ("image", "prompt"), ("jev", "state"),
                   ("jev", "questions", "*", "instructions"), ("jev", "questions", "*", "criteria", "*"),
                   ("fail",), ("output", "*"), ("call", "inputs", "*"), ("dedupe_key",)]
INPUT_TYPES = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean",
               "list": "list", "object": "object", "file": "file"}


@dataclass
class Agent:
    name: str
    data: dict
    body: str
    skills: list  # [(jméno, description, tělo)]


@dataclass
class StepInfo:
    id: str
    kind: str
    nn: int          # pořadí v souboru, hloubkově (run-record.md <nn>)
    data: dict
    cond: frozenset  # co způsobí, že krok nemusí proběhnout
    anc: frozenset   # podmínky předků (odkaz uvnitř stejné větve je v pořádku)
    out: object = None
    dir: str = ""    # 3b: u kroku volaného scénáře složka kroku call ("steps/03-navrh/"), id je pak cesta "navrh/copy"

    @property
    def key(self) -> str:
        """Id v souboru scénáře — pod ním je výstup ve výrazech (`steps.<key>`)."""
        return self.id.rsplit("/", 1)[-1]

    @property
    def folder(self) -> str:
        return f"{self.dir}steps/{self.nn:02d}-{self.key}"


@dataclass
class Project:
    """Ověřený scénář se vším, co engine potřebuje."""
    scenario_path: Path
    workflows: Path
    scenario: dict
    config: dict
    agents: dict[str, Agent]
    steps: dict[str, StepInfo]
    order: list[StepInfo] = field(default_factory=list)
    callees: dict[str, "Project"] = field(default_factory=dict)  # 3b: scénáře volané krokem call, podle jména
    mcp: dict = field(default_factory=dict)  # servery z mcp.yaml

    @property
    def base(self) -> Path:
        """Kořen projektu (nad workflows/); relativní runs_dir a storage.local.path se berou odsud."""
        return self.workflows.parent

    @property
    def runs_dir(self) -> Path:
        return self.base / self.config["runs_dir"]


# --- config.yaml ----------------------------------------------------------------

def env_fields(obj, path=()) -> list[tuple[str, str]]:
    """(cesta, JMENO) všech polí `*_env`."""
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
        errs.append(f"{p}: chybí — zkopíruj workflows/config.example.yaml na config.yaml a uprav (mění jen vlastník)")
        return None
    try:
        c = read_yaml(p, "config.yaml")
    except LoadError as e:
        errs.append(str(e))
        return None
    if v := version_error(c, "config.yaml"):
        errs.append(v)
        return None
    if e := schema_errors("config", c, "config.yaml"):
        errs.extend(e)
        return None
    seen = {}
    for path, name in env_fields(c):
        if name in seen:
            errs.append(f"config.yaml: {seen[name]} a {path} používají stejnou proměnnou {name} — "
                        "každé tajemství má mít vlastní proměnnou")
        seen[name] = path
    c["openrouter"].setdefault("base_url", DEFAULT_BASE_URL)
    c["openrouter"].setdefault("jev_model", "jev-1.13")
    c.setdefault("runs_dir", "./runs")
    c["limits"].setdefault("max_call_depth", 3)
    return c


# --- agenti a skilly ------------------------------------------------------------

def load_skill(wf: Path, name: str, errs: list, ref: str):
    where = f"skills/{name}/SKILL.md"
    p = wf / where
    if not p.is_file():
        errs.append(f"{ref}: skill '{name}' neexistuje ({where})")
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
        errs.append(f"{where}: name '{fm['name']}' se neshoduje se jménem složky")
    if not body.strip():
        errs.append(f"{where}: tělo skillu je prázdné")
    return name, fm["description"], body


def load_agent(wf: Path, name: str, config: dict, errs: list, ref: str | None = None,
               mcp: dict | None = None) -> Agent | None:
    where = f"agents/{name}.md"
    p = wf / where
    if not p.is_file():
        errs.append(f"{ref + ': ' if ref else ''}agent '{name}' neexistuje ({where})")
        return None
    try:
        fm, body = read_frontmatter(p, where)
    except LoadError as e:
        errs.append(str(e))
        return None
    if v := version_error(fm, where):
        errs.append(v)
        return None
    if e := schema_errors("agent", fm, where):
        errs.extend(e)
        return None
    n = len(errs)
    if fm["name"] != name:
        errs.append(f"{where}: name '{fm['name']}' se neshoduje se jménem souboru")
    if not body.strip():
        errs.append(f"{where}: tělo (instrukce agenta) je prázdné")
    if fm["model"] not in config["models"]:
        errs.append(f"{where}: model '{fm['model']}' není alias v config.yaml (aliasy: {', '.join(config['models'])})")
    if set(fm.get("tools", {})) != set(fm.get("mcp", [])):
        errs.append(f"{where}: klíče tools musí být přesně servery z mcp")
    servers = load_mcp(wf, errs) if mcp is None else mcp
    for srv in fm.get("mcp", []):  # oprávnění drží vlastník v mcp.yaml (config.md, §5.2)
        s = servers.get(srv)
        if s is None:
            errs.append(f"{where}: MCP server '{srv}' není v workflows/mcp.yaml (registr mění jen vlastník, "
                        "vzor mcp.example.yaml)")
        elif name not in s["agents"]:
            errs.append(f"{where}: server '{srv}' agentovi '{name}' vlastník nepovolil "
                        f"(mcp.yaml → servers.{srv}.agents: {', '.join(s['agents'])})")
        elif "tools" in s and (extra := [t for t in fm.get("tools", {}).get(srv, []) if t not in s["tools"]]):
            errs.append(f"{where}: nástroje {', '.join(extra)} serveru '{srv}' vlastník nepovolil "
                        f"(mcp.yaml → servers.{srv}.tools: {', '.join(s['tools'])})")
    skills = [s for s in (load_skill(wf, s, errs, where) for s in fm.get("skills", [])) if s]
    return Agent(name, fm, body, skills) if len(errs) == n else None


def effective_tools(agent: dict, task: dict) -> dict[str, list]:
    """Nástroje, které krok task smí použít: krok ⊆ agent (§5.2); validate hlídá, že krok nerozšiřuje."""
    servers = task.get("mcp", agent.get("mcp", []))
    return {s: (task.get("tools") or {}).get(s, agent.get("tools", {}).get(s, [])) for s in servers}


def mcp_servers_used(p: "Project") -> set[str]:
    """Servery, které běh může spustit: efektivní sady všech kroků task (i ve volaných scénářích)."""
    projects, used = [p], set()
    while projects:
        q = projects.pop()
        projects += q.callees.values()
        used |= {s for st in q.steps.values() if st.kind == "task"
                 for s in effective_tools(q.agents[st.data["task"]["agent"]].data, st.data["task"])}
    return used


# --- vstupy -----------------------------------------------------------------------

def _matches(t: str, v) -> bool:
    if t == "integer":
        return kind(v) == "number" and float(v).is_integer()
    return kind(v) == INPUT_TYPES[t]


def resolve_inputs(scenario: dict, given: dict, from_text: bool = False) -> dict:
    """Vstupy běhu po doplnění default; chyba = běh vůbec nezačne (scenario.md inputs)."""
    import json
    specs, errs, out = scenario.get("inputs") or {}, [], {}
    for name in given:
        if name not in specs:
            errs.append(f"neznámý vstup '{name}' (scénář má: {', '.join(specs) or 'žádné vstupy'})")
    for name, sp in specs.items():
        t = sp["type"]
        if name not in given:
            if sp.get("required"):
                errs.append(f"chybí povinný vstup '{name}' ({t})")
            else:
                out[name] = sp["default"]
            continue
        v = given[name]
        if t == "file":
            errs.append(f"vstup '{name}' je typu file — ten jde předat jen přes call, ne z CLI ani webhooku")
            continue
        if from_text and t != "string":
            try:
                v = json.loads(v)
            except ValueError:
                pass
        if not _matches(t, v):
            errs.append(f"vstup '{name}' má být {t}, dostal {kind(v)}")
        out[name] = v
    if errs:
        raise ConfigErrors(errs)
    return out


# --- scénář -----------------------------------------------------------------------

def validate(scenario_path, *, transport=None, check_models: bool = True) -> Project:
    """Načte a ověří scénář, config, agenty a skilly. Chyby → ConfigErrors."""
    path = Path(scenario_path).resolve()
    where = path.name
    if not path.is_file():
        raise ConfigErrors([f"{scenario_path}: soubor neexistuje"])
    if path.parent.name != "scenarios":
        raise ConfigErrors([f"{scenario_path}: scénář musí být přímo ve složce workflows/scenarios/ "
                            "(podsložky se nečtou)"])
    wf = path.parent.parent
    errs = []
    for d in ("scenarios", "agents"):
        for sub in sorted(p for p in (wf / d).glob("*") if p.is_dir()):
            errs.append(f"{d}/{sub.name}/: podsložky se nečtou — soubory patří přímo do workflows/{d}/")
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
        except MawError as e:
            raise ConfigErrors([f"{e.cls}: {e.message}"]) from None
        errs += check_models_list(config, chk.model_needs, models)
    if errs:
        raise ConfigErrors(errs)
    return chk.project(path)


def _read_scenario(path: Path, errs: list) -> dict | None:
    """Soubor scénáře: YAML, verze, JSON Schema, jméno = soubor. Chyby do `errs`."""
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
        errs.append(f"{where}: name '{sc.get('name')}' se neshoduje se jménem souboru")
    return sc if len(errs) == n else None


def check_models_list(config: dict, needs: dict, models: list) -> list[str]:
    """Aliasy proti GET /models: id existuje, obrázek umí výstup obrázku, schema umí
    structured_outputs nebo tools (scenario.md §7, §5.5, §5.7)."""
    by_id, errs = {m["id"]: m for m in models}, []
    for alias, need in sorted(needs.items()):
        mid = config["models"][alias]["id"]
        m = by_id.get(mid)
        if not m:
            errs.append(f"config.yaml: models.{alias}.id '{mid}' není v GET /models — překlep? "
                        "(např. claude-haiku-4.5, ne -4-5)")
            continue
        if "image" in need and "image" not in m["output_modalities"]:
            errs.append(f"config.yaml: model '{mid}' (alias {alias}) neumí výstup obrázku")
        if "tools" in need and "tools" not in m["supported_parameters"]:
            errs.append(f"config.yaml: model '{mid}' (alias {alias}) neumí tools — agent s ním nemůže běžet v kroku task")
        if "schema" in need and not {"structured_outputs", "tools"} & set(m["supported_parameters"]):
            errs.append(f"config.yaml: model '{mid}' (alias {alias}) neumí structured_outputs ani tools — "
                        "krok se schema by nešel vynutit")
    return errs


def _strings(obj, path=(), skip=()):
    """(cesta, text) všech textů včetně klíčů; `skip` = vnořené seznamy kroků."""
    if path in skip:
        return
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield path + (k, "#klíč"), k
            yield from _strings(v, path + (k,), skip)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, path + (i,), skip)


def _template_field(p) -> bool:
    return any(len(p) == len(f) and all(a == "*" or a == b for a, b in zip(f, p)) for f in TEMPLATE_FIELDS)


class _Checker:
    def __init__(self, sc: dict, config: dict, wf: Path, where: str, stack: tuple = (), model_needs=None):
        self.sc, self.config, self.wf, self.where = sc, config, wf, where
        self.stack = stack + (sc["name"],)  # 3b: řetěz call od nejvyššího scénáře (cykly, hloubka)
        self.errs: list[str] = []
        self.steps: dict[str, StepInfo] = {}
        self.order: list[StepInfo] = []
        self.agents: dict[str, Agent | None] = {}
        self.callees: dict[str, Project] = {}
        self.model_needs: dict[str, set] = {} if model_needs is None else model_needs
        self.inputs_type = {k: INPUT_TYPES[v["type"]] for k, v in (sc.get("inputs") or {}).items()}
        self.mcp = load_mcp(wf, self.errs)
        own = {name: path for path, name in env_fields(config)}
        for name in secret_names(self.mcp):  # klíč z config.yaml by odešel MCP serveru (např. OPENROUTER_API_KEY)
            if name in own:
                self.errs.append(f"mcp.yaml: proměnná {name} je už v config.yaml ({own[name]}) — "
                                 "MCP server musí mít vlastní tajemství")

    def project(self, path: Path) -> Project:
        return Project(path, self.wf, self.sc, self.config, self.agents, self.steps, self.order, self.callees, self.mcp)

    def err(self, step, fld, msg):
        prefix = f'{self.where}: krok "{step}"' if step else self.where
        self.errs.append(f"{prefix}, {fld}: {msg}" if fld else f"{prefix}: {msg}")

    def run(self):
        for name, sp in (self.sc.get("inputs") or {}).items():
            if "default" in sp and not _matches(sp["type"], sp["default"]):
                self.err(None, f"inputs.{name}.default", f"hodnota neodpovídá type {sp['type']}")
        self.number(self.sc["steps"], frozenset(), frozenset())
        header = {k: v for k, v in self.sc.items() if k != "steps"}
        for p, s in _strings(header):
            if "{{" in s:
                self.err(None, ".".join(map(str, p)), "šablona {{ }} v hlavičce scénáře být nesmí")
        for info in self.order:
            skip = {p for p, _ in nested_lists(info.data)}
            for p, s in _strings(info.data, skip=skip):
                if "{{" in s and not _template_field(p):
                    self.err(info.id, ".".join(map(str, p)).replace(".#klíč", " (klíč)"),
                             "šablona {{ }} tu není povolená — smí být jen v prompt, jev.state, jev.questions "
                             "(instructions, criteria), fail, hodnotách output, call.inputs a dedupe_key")
        self.walk(self.sc["steps"], {}, top=True)
        outs = self.sc.get("outputs") or {}
        if len(self.stack) == 1 and self.config["storage"]["type"] == "r2" and any(o["type"] == "file" for o in outs.values()):
            self.err(None, None, "výstup typu file potřebuje úložiště, ale storage.type: r2 framework zatím neumí "
                                 "— nastav v config.yaml storage.type: local")
        last = self.sc["steps"][-1]
        if self.sc.get("outputs") and step_kind(last) != "output":
            self.err(None, None, "scénář má outputs, ale poslední krok není output")

    # -- první průchod: čísla, unikátní id, podmíněnost --
    def number(self, steps, anc, cond):
        for st in steps:
            sid, k = st["id"], step_kind(st)
            own = frozenset({sid}) if ("when" in st or st.get("on_error") == "continue") else frozenset()
            info = StepInfo(sid, k, len(self.order) + 1, st, cond | own, anc)
            self.order.append(info)
            if sid in self.steps:
                self.err(sid, None, "id není unikátní (platí pro celý soubor včetně větví)")
            else:
                self.steps[sid] = info
            for p, lst in nested_lists(st):
                frame = frozenset({f"{sid}:{'/'.join(p)}"})
                self.number(lst, anc | own | frame, cond | own | (frame if k == "switch" else frozenset()))

    def why(self, x: StepInfo) -> str:
        reasons = []
        for c in sorted(x.cond):
            if c == x.id:
                reasons.append("má when" if "when" in x.data else "má on_error: continue")
            elif ":switch/" in c:
                reasons.append(f"je ve větvi switch '{c.split(':')[0]}'")
            else:
                reasons.append(f"je uvnitř kroku '{c}', který nemusí proběhnout")
        return ", ".join(reasons)

    def resolver(self, scope: dict, r: StepInfo):
        def resolve(key):
            x = self.steps.get(key)
            if x is r:
                raise ExprError(f"krok '{key}' nemůže číst svůj vlastní výstup")
            if x and x.kind in ("parallel", "switch", "fail", "output"):
                raise ExprError(f"krok '{key}' ({x.kind}) nemá výstup — výstupy mají kroky uvnitř")
            if key in scope:
                if not x.cond <= r.anc and "default" not in x.data:
                    raise ExprError(f"krok '{key}' nemusí proběhnout ({self.why(x)}) a nemá default — doplň mu "
                                    "default se všemi poli výstupu (§5.4)")
                return scope[key]
            if x and x.nn > r.nn:
                raise ExprError(f"krok '{key}' je až níž — výraz vidí jen kroky nad sebou")
            if x:
                raise ExprError(f"krok '{key}' je v jiné větvi parallel — nevíme, co doběhne dřív")
            avail = [k for k, v in scope.items() if v is not NOOUT]
            raise ExprError(f"krok '{key}' neexistuje (dostupné: {', '.join(avail) or '—'})")
        return resolve

    def expr_type(self, info, fld, expr, res, want=None):
        try:
            t = infer(expr, self.inputs_type, res)
        except ExprError as e:
            self.err(info.id, fld, str(e))
            return None
        if want and tkind(t) and tkind(t) != want:
            self.err(info.id, fld, f"výraz musí dát {'true/false' if want == 'boolean' else want}, dá {tkind(t)}"
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

    # -- druhý průchod: odkazy, typy, šablony, pravidla kroků --
    def walk(self, steps, scope, top=False):
        added = {}
        for i, st in enumerate(steps):
            info = self.steps.get(st["id"])
            if info is None or info.data is not st:
                continue  # duplicitní id, už nahlášeno
            sid, k = info.id, info.kind
            res = self.resolver(scope, info)
            if "when" in st:
                self.expr_type(info, "when", st["when"], res, want="boolean")
            out = NOOUT
            if k in ("ask", "task"):
                out = getattr(self, k)(info, res)
            elif k == "jev":
                out = self.jev(info, res)
            elif k == "image":
                out = self.image(info, res)
            elif k == "call":
                out = self.call(info, res)
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
                self.err(steps[i + 1].get("id"), None, f"krok je nedosažitelný — nad ním je nepodmíněný fail '{sid}'")
            if "default" in st and isinstance(out, dict):
                self.check_default(info, out)
            info.out = out
            scope[sid] = added[sid] = out
        return added

    def agent(self, name, info) -> Agent | None:
        if name not in self.agents:
            self.agents[name] = load_agent(self.wf, name, self.config, self.errs, f'{self.where}: krok "{info.id}"',
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
                self.err(info.id, "budget_usd", f"{st['budget_usd']} je víc než limits.budget_usd agenta "
                                                f"'{agent.name}' ({lim['budget_usd']}) — krok limity jen snižuje")
            if "timeout" in st and "timeout" in lim and seconds(st["timeout"]) > seconds(lim["timeout"]):
                self.err(info.id, "timeout", f"{st['timeout']} je víc než limits.timeout agenta '{agent.name}' "
                                             f"({lim['timeout']}) — krok limity jen snižuje")
        return shape_type(a["schema"]) if "schema" in a else {"text": "string"}

    def task(self, info, res):
        """Krok task: limity a oprávnění krok ⊆ agent ⊆ mcp.yaml (agent.md Oprávnění, §5.2, §5.8)."""
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
            self.err(info.id, "task.agent", f"agent '{name}' nemá limits.max_turns — task musí mít limit tahů (§5.1)")
        elif t.get("max_turns", 0) > a["limits"]["max_turns"]:
            self.err(info.id, "task.max_turns", f"{t['max_turns']} je víc než limits.max_turns agenta '{name}' "
                                                f"({a['limits']['max_turns']}) — krok limity jen snižuje")
        for srv in t.get("mcp", []):
            if srv not in a.get("mcp", []):
                self.err(info.id, "task.mcp", f"server '{srv}' agent '{name}' nepovoluje (mcp: "
                                              f"{', '.join(a.get('mcp', [])) or '—'}) — krok oprávnění jen zužuje")
        eff = effective_tools(a, t)
        for srv, tools in (t.get("tools") or {}).items():
            if srv not in eff:
                self.err(info.id, f"task.tools.{srv}", f"server '{srv}' krok nepoužívá (task.mcp / mcp agenta)")
                continue
            for tool in tools:
                if tool not in a.get("tools", {}).get(srv, []):
                    self.err(info.id, "task.tools", f"krok chce nástroj {srv}.{tool}, agent '{name}' ho nepovoluje "
                                                    f"(tools.{srv})")
        names = {}
        for srv, tools in eff.items():
            s = self.mcp.get(srv)
            if s and "scenarios" in s and self.sc["name"] not in s["scenarios"]:
                self.err(info.id, None, f"scénář '{self.sc['name']}' nesmí spustit agenta se serverem '{srv}' "
                                        f"(mcp.yaml → servers.{srv}.scenarios: {', '.join(s['scenarios'])})")
            for tool in tools:
                n = api_name(srv, tool)
                if n in names and names[n] != (srv, tool):
                    self.err(info.id, None, f"nástroje {'.'.join(names[n])} a {srv}.{tool} mají po normalizaci "
                                            f"stejné jméno {n} (jen [a-zA-Z0-9_-], max 64 znaků)")
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
            self.err(info.id, "image.model", f"'{im['model']}' není alias v config.yaml "
                                             f"(aliasy: {', '.join(self.config['models'])})")
        else:
            self.need(im["model"], "image")
        self.template(info, "image.prompt", im["prompt"], res)
        return {"file": "file"}

    def call(self, info, res):
        """Krok call (scenario.md call, §5.3): volaný scénář, jeho inputs a outputs."""
        c = info.data["call"]
        given = c.get("inputs") or {}
        types = {k: self.template(info, f"call.inputs.{k}", v, res) if isinstance(v, str) else kind(v)
                 for k, v in given.items()}
        callee = self.callee(c["scenario"], info)
        if callee is None:
            return None
        specs, name = callee.scenario.get("inputs") or {}, c["scenario"]
        if extra := [k for k in given if k not in specs]:
            self.err(info.id, "call.inputs", f"scénář '{name}' nemá vstupy: {', '.join(extra)} "
                                             f"(má: {', '.join(specs) or 'žádné'})")
        if missing := [k for k, sp in specs.items() if sp.get("required") and k not in given]:
            self.err(info.id, "call.inputs", f"chybí povinné vstupy scénáře '{name}': {', '.join(missing)}")
        for k, t in types.items():
            if k in specs and tkind(t) and tkind(t) != INPUT_TYPES[specs[k]["type"]]:
                self.err(info.id, f"call.inputs.{k}", f"vstup má typ {specs[k]['type']}, hodnota je {tkind(t)}")
        return {k: INPUT_TYPES[o["type"]] for k, o in (callee.scenario.get("outputs") or {}).items()}

    def callee(self, name: str, info) -> Project | None:
        """Ověří volaný scénář (rekurzivně); cyklus a hloubka jsou chyba config."""
        path = self.wf / "scenarios" / f"{name}.yaml"
        if not path.is_file():
            self.err(info.id, "call.scenario", f"scénář '{name}' neexistuje (scenarios/{name}.yaml)")
            return None
        if name in self.stack:
            self.err(info.id, "call.scenario", f"cyklus call: {' → '.join(self.stack + (name,))}")
            return None
        depth, limit = len(self.stack), self.config["limits"]["max_call_depth"]
        if depth > limit:
            self.err(info.id, "call.scenario", f"hloubka call {depth} je nad limits.max_call_depth ({limit}): "
                                               f"{' → '.join(self.stack + (name,))}")
            return None
        errs = []
        sc = _read_scenario(path, errs)
        self.errs += errs
        if sc is None:
            return None
        if sc.get("callable") is not True:
            self.err(info.id, "call.scenario", f"scénář '{name}' nemá callable: true — volat ho nejde "
                                               "(chrání schvalování v n8n, §5.2)")
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
            return  # už nahlášeno
        match tree:
            case ast.Attribute(value=ast.Attribute(value=ast.Name(id="steps"), attr=sid), attr=q):
                x = self.steps.get(sid)
                spec = x.data["jev"]["questions"].get(q) if x and x.kind == "jev" else None
                if spec and spec["type"] == "choice":
                    extra = [c for c in sw["cases"] if c not in spec["criteria"]]
                    if extra:
                        self.err(info.id, "switch.cases", f"{', '.join(extra)} není mezi možnostmi criteria "
                                                          f"otázky '{q}' ({', '.join(spec['criteria'])})")

    def check_default(self, info, out: dict):
        d = info.data["default"]
        fields = {k: v for k, v in out.items() if not (info.kind == "jev" and k == "details")}
        missing = [k for k in fields if k not in d]
        extra = [k for k in d if k not in out]
        if missing:
            self.err(info.id, "default", f"musí obsahovat všechna pole výstupu, chybí: {', '.join(missing)}")
        if extra:
            self.err(info.id, "default", f"pole, která krok nevrací: {', '.join(extra)}")
        for k, v in d.items():
            want = tkind(fields.get(k))
            if want and v is not None and kind(v) != want:
                self.err(info.id, f"default.{k}", f"má být {want} nebo null, je {kind(v)}")

    def output(self, info, res, last):
        if not last:
            self.err(info.id, None, "output smí být jen jednou a jen jako poslední krok hlavního seznamu steps")
        outs = self.sc.get("outputs")
        if not outs:
            self.err(info.id, None, "scénář bez outputs nesmí mít krok output — doplň outputs do hlavičky")
            return
        o = info.data["output"]
        if missing := [k for k in outs if k not in o]:
            self.err(info.id, "output", f"chybí výstupy z hlavičky: {', '.join(missing)}")
        if extra := [k for k in o if k not in outs]:
            self.err(info.id, "output", f"výstupy, které hlavička nemá: {', '.join(extra)}")
        for k, v in o.items():
            if k not in outs:
                continue
            want = outs[k]["type"]
            t = tkind(self.template(info, f"output.{k}", v, res) if isinstance(v, str) else kind(v))
            if want == "file" and t and t != "file":
                self.err(info.id, f"output.{k}", "výstup typu file musí být šablona na soubor z kroku image "
                                                 f"(např. {{{{ steps.foto.file }}}}), ne {t}")
            elif want != "file" and t and t != INPUT_TYPES[want]:
                self.err(info.id, f"output.{k}", f"výstup má typ {want}, hodnota je {t}")
