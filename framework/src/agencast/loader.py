"""File loading: YAML 1.2 core, frontmatter, `.env`, JSON Schema from the spec.

Schemas are read from `docs/spec/schema/` — the spec is the single source of truth;
the framework does not duplicate them (DESIGN §5.6).
"""
import json
import os
import re
from functools import cache
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from . import FORMAT_VERSIONS
from .resources import resource_dir

SPEC_SCHEMAS = resource_dir("docs") / "spec" / "schema"
STEP_KINDS = ("ask", "task", "jev", "image", "parallel", "switch", "call", "set", "fail", "output")


class Yaml12Loader(yaml.SafeLoader):
    """SafeLoader without YAML 1.1 resolvers: only true/false are booleans; `yes`/`on`,
    `4:5` and dates are strings; duplicate keys raise an error with a line number (spec B6)."""
    line_offset = 0  # lines before YAML (.md frontmatter), so 'first on line N' matches the file

    def construct_mapping(self, node, deep=False):
        seen = {}
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, (str, int, float, bool)) and key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key '{key}' (first on line {seen[key]})", key_node.start_mark)
            seen[key] = key_node.start_mark.line + 1 + self.line_offset
        return super().construct_mapping(node, deep)


Yaml12Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in rs if tag == "tag:yaml.org,2002:null"]
    for ch, rs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for _tag, _rx, _first in [
    ("tag:yaml.org,2002:bool", r"^(?:true|True|TRUE|false|False|FALSE)$", "tTfF"),
    ("tag:yaml.org,2002:int", r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$", "-+0123456789"),
    ("tag:yaml.org,2002:float",
     r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$",
     "-+0123456789."),
]:
    Yaml12Loader.add_implicit_resolver(_tag, re.compile(_rx), list(_first))


def _int12(loader, node):
    v = loader.construct_scalar(node)
    return int(v[2:], {"0x": 16, "0o": 8}[v[:2]]) if v[:2] in ("0x", "0o") else int(v, 10)


Yaml12Loader.add_constructor("tag:yaml.org,2002:int", _int12)


ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*")  # as in the schemas: a name outside it may be a pasted key


class LoadError(Exception):
    """The file cannot be read (error class `config`)."""


def load_yaml(text: str, where: str, line_offset: int = 0):
    loader = Yaml12Loader(text)
    loader.line_offset = line_offset
    try:
        return loader.get_single_data()
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = f", line {mark.line + 1 + line_offset}" if mark else ""
        problem = getattr(e, "problem", None) or str(e)
        if not isinstance(e, yaml.constructor.ConstructorError):  # syntax; duplicate keys have their own message
            problem = ("cannot read YAML — a value containing {, [, ': ' or ' #' must be quoted "
                       f"(scenario.md §5 'YAML pitfalls')\n  {problem}")
        raise LoadError(f"{where}{line}: {problem}") from None
    finally:
        loader.dispose()


def read_text(path: Path, where: str) -> str:
    """Text of a project file; one that cannot be read (permissions, not UTF-8) is a `config` error, not a traceback."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise LoadError(f"{where}: cannot read the file ({getattr(e, 'strerror', None) or 'not UTF-8 text'})") from None


def read_yaml(path: Path, where: str | None = None):
    return load_yaml(read_text(path, where or str(path)), where or str(path))


def read_frontmatter(path: Path, where: str):
    """(frontmatter, body) of a Markdown file with YAML between `---` lines."""
    m = re.match(r"---\n(.*?)\n---\n(.*)", read_text(path, where).replace("\r\n", "\n"), re.S)
    if not m:
        raise LoadError(f"{where}: missing frontmatter between --- lines")
    return load_yaml(m.group(1), where, line_offset=1), m.group(2)


def load_dotenv(path: Path):
    """Load variables from `.env` (existing environment variables take precedence). Accept CRLF (DESIGN §7 item 8)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if sep:
            os.environ.setdefault(key.strip(), value)


def seconds(duration: str) -> int:
    """Duration `<number>s|m|h` in seconds."""
    return int(duration[:-1]) * {"s": 1, "m": 60, "h": 3600}[duration[-1]]


def version_error(data, where: str) -> str | None:
    """Reject unknown versions instead of guessing how to interpret them (§5.9 item 6)."""
    if not isinstance(data, dict):
        return f"{where}: file must be a mapping (key: value)"
    if "version" not in data:
        return f"{where}: missing field version (currently only version: 1)"
    v = data["version"]
    if isinstance(v, bool) or v not in FORMAT_VERSIONS:
        return f"{where}: unknown format version {v!r} — the framework supports version: {', '.join(map(str, FORMAT_VERSIONS))}"
    return None


# --- JSON Schema --------------------------------------------------------------

@cache
def schema(kind: str) -> dict:
    return json.loads((SPEC_SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8"))


@cache
def _validator(kind: str, ref: str | None = None) -> Draft202012Validator:
    s = schema(kind)
    if ref:  # a single definition, e.g. ask_step (clearer messages than oneOf across all step types)
        s = {"$schema": s["$schema"], "$defs": s["$defs"], "$ref": f"#/$defs/{ref}"}
    return Draft202012Validator(s)


def path_str(parts) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out


def _jkind(v) -> str:
    return {dict: "mapping", list: "list", str: "string", bool: "true/false", int: "number",
            float: "number", type(None): "null"}.get(type(v), type(v).__name__)


def describe_error(e) -> str:
    """An English message without the value (a `*_env` field could contain a secret key)."""
    v, val, inst = e.validator, e.validator_value, e.instance
    match v:
        case "required":
            return "missing required field " + ", ".join(f"'{k}'" for k in val if k not in inst)
        case "additionalProperties":
            known = e.schema.get("properties", {})
            return "unknown field " + ", ".join(f"'{k}'" for k in inst if k not in known) + " (typo?)"
        case "type":
            want = val if isinstance(val, str) else " or ".join(val)
            return f"expected {want}, got {_jkind(inst)}"
        case "const":
            return f"expected {json.dumps(val, ensure_ascii=False)}"
        case "enum":
            return "allowed values: " + ", ".join(json.dumps(x, ensure_ascii=False) for x in val)
        case "pattern":
            if "propertyNames" in e.relative_schema_path:
                if list(e.absolute_path)[-1:] == ["env"]:  # mcp.yaml: a pasted `NAME=key` or the key itself as the name
                    return f"variable name does not match pattern {val} (expected NAME_FOR_SERVER: NAME_ON_HOST)"
                return f"name '{inst}' does not match pattern {val}"
            p = [str(x) for x in e.absolute_path]  # `*_env` field or a value in mcp.yaml `env`: likely a pasted key
            env = " — expected the NAME of an environment variable, not its value" \
                if p and (p[-1].endswith("_env") or p[-2:-1] == ["env"]) else ""
            return f"value does not match pattern {val}{env}"
        case "minItems" | "minProperties":
            return f"must contain at least {val} item{'' if val == 1 else 's'}"
        case "maxItems":
            return f"must contain at most {val} item{'' if val == 1 else 's'}"
        case "minLength":
            return "must not be empty"
        case "minimum":
            return f"must be at least {val}"
        case "exclusiveMinimum":
            return f"must be greater than {val}"
        case "uniqueItems":
            return "duplicate items"
        case "not":
            if isinstance(inst, str) and isinstance(val, dict) and "enum" in val \
                    and list(e.absolute_path)[-1:] == ["env"]:  # mcp.yaml env: names the server process must keep
                return f"variable '{inst}' must not be set for a server (not allowed: {', '.join(val['enum'])})"
            return f"'{inst}' is a reserved word" if isinstance(inst, str) else "disallowed value"
        case "dependentRequired":
            if "mcp" in inst and "tools" not in inst and isinstance(inst["mcp"], list):  # BUGS 9
                return ("field 'mcp' requires 'tools' — an explicit list of tools for each server: tools: { "
                        + ", ".join(f"{s}: [tool, …]" for s in inst["mcp"])
                        + " }; plan.md from agencast run <scenario> --dry-run lists the tools offered by each server")
            return "field " + " / ".join(f"'{k}' also requires {', '.join(map(repr, r))}"
                                          for k, r in val.items() if k in inst)
        case "oneOf":
            return _one_of(e)
    return e.message


def _one_of(e) -> str:
    branches, inst = e.validator_value, e.instance
    if sorted(tuple(b.get("required", ())) for b in branches) == [("default",), ("required",)]:
        return "input must have either required: true or default (exactly one)"
    types = [b.get("properties", {}).get("type", {}).get("const") for b in branches]
    if isinstance(inst, dict) and all(types):  # Jev question: branch errors selected by type
        if inst.get("type") not in types:
            return f"type must be one of: {', '.join(types)}"
        i = types.index(inst["type"])
        return "; ".join(f"{path_str(c.relative_path) + ': ' if c.relative_path else ''}{describe_error(c)}"
                         for c in e.context if c.schema_path and c.schema_path[0] == i)
    if e.schema.get("description", "").startswith("Shorthand schema"):
        return "schema format: string, number, integer, boolean, [type] or a field: type mapping"
    if (keys := _form_keys(e)) and sum(k in inst for k in keys) != 1:  # with one, schema_errors reports that form
        return "server must have either command or url (exactly one)"
    return "value does not match any allowed form"


def _form_keys(e) -> list[str]:
    """mcp.yaml server = oneOf of a `command` (stdio) and a `url` (remote) form: the key of each form;
    [] for any other error."""
    if e.validator != "oneOf" or not isinstance(e.instance, dict):
        return []
    keys = [next((k for k in ("command", "url") if k in b.get("required", ())), None) for b in e.validator_value]
    return keys if all(keys) else []


def _form_errors(errors):
    """A server with exactly one of command/url: the errors of that form, each with its own field and line,
    instead of one 'does not match any allowed form' for the whole server."""
    for e in errors:
        used = [i for i, k in enumerate(_form_keys(e)) if k in e.instance]
        if len(used) == 1:
            yield from (c for c in e.context if c.schema_path[0] == used[0])
        else:
            yield e


def _yaml_line(data, path) -> int | None:
    """YAML line of a key/path in a ruamel round-trip tree."""
    node, line = data, None
    for key in path:
        try:
            lc = getattr(node, "lc", None)
            if lc is None:
                return line
            pos = lc.key(key) if isinstance(node, dict) else lc.item(key)
            if pos:
                line = pos[0] + 1
            node = node[key]
        except (AttributeError, IndexError, KeyError, TypeError):
            return line
    return line


def schema_errors(kind: str, data, where: str, ref: str | None = None, skip=(), source: str | None = None) -> list[str]:
    """Errors against the spec's JSON Schema; `skip` = paths checked separately."""
    out, line_data = [], None
    if source is not None:
        try:
            from ruamel.yaml import YAML
            line_data = YAML(typ="rt").load(source)
        except Exception:
            pass  # PyYAML already checked syntax; keep the original message without positions
    def at(p) -> str:
        line = _yaml_line(line_data, p) if line_data is not None else None
        return f"{where}, line {line}: " if line else f"{where}: "

    for e in sorted(_form_errors(_validator(kind, ref).iter_errors(data)),
                    key=lambda e: list(map(str, e.absolute_path))):
        p = tuple(e.absolute_path)
        if any(p[:len(s)] == s and len(p) > len(s) for s in skip):
            continue
        if len(p) >= 2 and p[-2] == "env" and not ENV_NAME.fullmatch(str(p[-1])):
            continue  # the path would quote the bad name (a pasted key); the name itself is reported, unquoted
        if e.validator == "additionalProperties" and isinstance(e.instance, dict):
            known = e.schema.get("properties", {})
            if extra := [k for k in e.instance if k not in known]:
                # a field of the other server form (env with url, transport with command) is not a typo
                other = dict(zip(_form_keys(e.parent), e.parent.validator_value)) if e.parent is not None else {}
                for key in extra:
                    only = next((k for k, b in other.items() if key in b.get("properties", {})), None)
                    out.append(f"{at(p + (key,))}{path_str(p + (key,))}: " + (
                        f"field '{key}' is only allowed with {only}" if only else f"unknown field '{key}' (typo?)"))
                continue
        out.append(f"{at(p)}{path_str(p) + ': ' if p else ''}{describe_error(e)}")
    return out


def step_kind(step) -> str | None:
    kinds = [k for k in STEP_KINDS if isinstance(step, dict) and k in step]
    return kinds[0] if len(kinds) == 1 else None


def nested_lists(step) -> list[tuple[tuple, list]]:
    """Step lists inside `parallel`/`switch`: (path within the step, list)."""
    match step_kind(step):
        case "parallel" if isinstance(step["parallel"], dict):
            return [(("parallel", b), v) for b, v in step["parallel"].items() if isinstance(v, list)]
        case "switch" if isinstance(step["switch"], dict):
            sw = step["switch"]
            out = [(("switch", "cases", c), v) for c, v in (sw.get("cases") or {}).items() if isinstance(v, list)]
            if isinstance(sw.get("default"), list):
                out.append((("switch", "default"), sw["default"]))
            return out
    return []


def scenario_schema_errors(data: dict, where: str) -> list[str]:
    """Scenario: validate the header against the full schema and each step against its type's schema."""
    errs = schema_errors("scenario", data, where, skip=[("steps",)])

    def steps(lst, path, in_branch):
        for i, st in enumerate(lst):
            label = f"{where}: step {st.get('id')!r}" if isinstance(st, dict) and "id" in st \
                else f"{where}: {path_str(path + (i,))}"
            kind = step_kind(st)
            if kind is None:
                have = [k for k in STEP_KINDS if isinstance(st, dict) and k in st]
                errs.append(f"{label}: step must have exactly one type ({', '.join(STEP_KINDS)}), has: "
                            f"{', '.join(have) or 'none'}")
                continue
            if in_branch and kind == "output":
                errs.append(f"{label}: output must not be inside a parallel/switch branch")
                continue
            nested = nested_lists(st)
            errs.extend(schema_errors("scenario", st, label, ref=f"{kind}_step", skip=[p for p, _ in nested]))
            for p, lst2 in nested:
                steps(lst2, path + (i,) + p, True)

    if isinstance(data.get("steps"), list):
        steps(data["steps"], ("steps",), False)
    return errs
