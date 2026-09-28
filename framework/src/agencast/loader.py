"""Čtení souborů: YAML 1.2 core, frontmatter, `.env`, JSON Schema ze spec.

Schémata se čtou z `docs/spec/schema/` — spec je jediný zdroj pravdy,
framework je neduplikuje (DESIGN §5.6).
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
    """SafeLoader bez resolverů YAML 1.1: booleany jen true/false, `yes`/`on`
    a `4:5` a datum jsou text, duplicitní klíč je chyba s řádkem (spec B6)."""
    line_offset = 0  # řádky před YAML v souboru (frontmatter .md), ať „poprvé na řádku N“ sedí se souborem

    def construct_mapping(self, node, deep=False):
        seen = {}
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, (str, int, float, bool)) and key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicitní klíč '{key}' (poprvé na řádku {seen[key]})", key_node.start_mark)
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


class LoadError(Exception):
    """Soubor nejde přečíst (třída `config`)."""


def load_yaml(text: str, where: str, line_offset: int = 0):
    loader = Yaml12Loader(text)
    loader.line_offset = line_offset
    try:
        return loader.get_single_data()
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = f", řádek {mark.line + 1 + line_offset}" if mark else ""
        problem = getattr(e, "problem", None) or str(e)
        if not isinstance(e, yaml.constructor.ConstructorError):  # syntaxe; duplicitní klíč má vlastní hlášku
            problem = ("YAML nejde přečíst — hodnota s {, [, ': ' nebo ' #' patří do uvozovek "
                       f"(scenario.md §5 „Pozor na YAML“)\n  {problem}")
        raise LoadError(f"{where}{line}: {problem}") from None
    finally:
        loader.dispose()


def read_yaml(path: Path, where: str | None = None):
    return load_yaml(path.read_text(encoding="utf-8"), where or str(path))


def read_frontmatter(path: Path, where: str):
    """(frontmatter, tělo) souboru Markdown s YAML mezi řádky `---`."""
    m = re.match(r"---\n(.*?)\n---\n(.*)", path.read_text(encoding="utf-8").replace("\r\n", "\n"), re.S)
    if not m:
        raise LoadError(f"{where}: chybí frontmatter mezi řádky ---")
    return load_yaml(m.group(1), where, line_offset=1), m.group(2)


def load_dotenv(path: Path):
    """Doplní proměnné z `.env` (existující v prostředí mají přednost). Snese CRLF (DESIGN §7 bod 8)."""
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
    """Trvání `<číslo>s|m|h` v sekundách."""
    return int(duration[:-1]) * {"s": 1, "m": 60, "h": 3600}[duration[-1]]


def version_error(data, where: str) -> str | None:
    """Neznámou verzi framework odmítne, nikdy ji nečte po svém (§5.9 bod 6)."""
    if not isinstance(data, dict):
        return f"{where}: soubor musí být mapa (klíč: hodnota)"
    if "version" not in data:
        return f"{where}: chybí pole version (zatím jen version: 1)"
    v = data["version"]
    if isinstance(v, bool) or v not in FORMAT_VERSIONS:
        return f"{where}: neznámá verze formátu {v!r} — framework umí version: {', '.join(map(str, FORMAT_VERSIONS))}"
    return None


# --- JSON Schema --------------------------------------------------------------

@cache
def schema(kind: str) -> dict:
    return json.loads((SPEC_SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8"))


@cache
def _validator(kind: str, ref: str | None = None) -> Draft202012Validator:
    s = schema(kind)
    if ref:  # jen jedna definice, např. ask_step (přesnější hlášky než oneOf přes všechny kroky)
        s = {"$schema": s["$schema"], "$defs": s["$defs"], "$ref": f"#/$defs/{ref}"}
    return Draft202012Validator(s)


def path_str(parts) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out


def _jkind(v) -> str:
    return {dict: "mapa", list: "seznam", str: "text", bool: "true/false", int: "číslo",
            float: "číslo", type(None): "null"}.get(type(v), type(v).__name__)


def describe_error(e) -> str:
    """Česká hláška bez vypsání hodnoty (u `*_env` by to mohl být klíč)."""
    v, val, inst = e.validator, e.validator_value, e.instance
    match v:
        case "required":
            return "chybí povinné pole " + ", ".join(f"'{k}'" for k in val if k not in inst)
        case "additionalProperties":
            known = e.schema.get("properties", {})
            return "neznámé pole " + ", ".join(f"'{k}'" for k in inst if k not in known) + " (překlep?)"
        case "type":
            want = val if isinstance(val, str) else " nebo ".join(val)
            return f"má být {want}, je {_jkind(inst)}"
        case "const":
            return f"má být {json.dumps(val, ensure_ascii=False)}"
        case "enum":
            return "povolené hodnoty: " + ", ".join(json.dumps(x, ensure_ascii=False) for x in val)
        case "pattern":
            if "propertyNames" in e.relative_schema_path:
                return f"jméno '{inst}' neodpovídá tvaru {val}"
            return f"hodnota neodpovídá tvaru {val}"
        case "minItems" | "minProperties":
            return f"musí mít aspoň {val} položk{'u' if val == 1 else 'y'}"
        case "maxItems":
            return f"smí mít nejvýš {val} položku"
        case "minLength":
            return "nesmí být prázdné"
        case "minimum":
            return f"musí být aspoň {val}"
        case "exclusiveMinimum":
            return f"musí být větší než {val}"
        case "uniqueItems":
            return "položky se opakují"
        case "not":
            return f"'{inst}' je vyhrazené slovo" if isinstance(inst, str) else "nepovolená hodnota"
        case "dependentRequired":
            if "mcp" in inst and "tools" not in inst and isinstance(inst["mcp"], list):  # BUGS 9
                return ("s polem 'mcp' je povinné i 'tools' — výslovný seznam nástrojů pro každý server: tools: { "
                        + ", ".join(f"{s}: [nástroj, …]" for s in inst["mcp"])
                        + " }; co servery nabízejí, vypíše plan.md z agencast run <scénář> --dry-run")
            return "s polem " + " / ".join(f"'{k}' je povinné i {', '.join(map(repr, r))}"
                                          for k, r in val.items() if k in inst)
        case "oneOf":
            return _one_of(e)
    return e.message


def _one_of(e) -> str:
    branches, inst = e.validator_value, e.instance
    if sorted(tuple(b.get("required", ())) for b in branches) == [("default",), ("required",)]:
        return "vstup má mít buď required: true, nebo default (ne obojí ani nic)"
    types = [b.get("properties", {}).get("type", {}).get("const") for b in branches]
    if isinstance(inst, dict) and all(types):  # otázka Jev: chyby větve podle type
        if inst.get("type") not in types:
            return f"type musí být jedno z: {', '.join(types)}"
        i = types.index(inst["type"])
        return "; ".join(f"{path_str(c.relative_path) + ': ' if c.relative_path else ''}{describe_error(c)}"
                         for c in e.context if c.schema_path and c.schema_path[0] == i)
    if e.schema.get("description", "").startswith("Zkrácený"):
        return "tvar schema: string, number, integer, boolean, [typ] nebo mapa pole: typ"
    return "hodnota neodpovídá žádné povolené podobě"


def _yaml_line(data, path) -> int | None:
    """YAML řádek klíče/cesty v ruamel round-trip stromu."""
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
    """Chyby proti JSON Schema ze spec; `skip` = cesty, které se kontrolují zvlášť."""
    out, line_data = [], None
    if source is not None:
        try:
            from ruamel.yaml import YAML
            line_data = YAML(typ="rt").load(source)
        except Exception:
            pass  # syntaxi už zkontroloval PyYAML; bez pozic zůstane původní hláška
    def at(p) -> str:
        line = _yaml_line(line_data, p) if line_data is not None else None
        return f"{where}, řádek {line}: " if line else f"{where}: "

    for e in sorted(_validator(kind, ref).iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        p = tuple(e.absolute_path)
        if any(p[:len(s)] == s and len(p) > len(s) for s in skip):
            continue
        if e.validator == "additionalProperties" and isinstance(e.instance, dict):
            known = e.schema.get("properties", {})
            if extra := [k for k in e.instance if k not in known]:
                out += [f"{at(p + (key,))}{path_str(p + (key,))}: neznámé pole '{key}' (překlep?)" for key in extra]
                continue
        out.append(f"{at(p)}{path_str(p) + ': ' if p else ''}{describe_error(e)}")
    return out


def step_kind(step) -> str | None:
    kinds = [k for k in STEP_KINDS if isinstance(step, dict) and k in step]
    return kinds[0] if len(kinds) == 1 else None


def nested_lists(step) -> list[tuple[tuple, list]]:
    """Seznamy kroků uvnitř `parallel`/`switch`: (cesta v kroku, seznam)."""
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
    """Scénář: hlavička proti celému schématu, každý krok zvlášť proti schématu svého typu."""
    errs = schema_errors("scenario", data, where, skip=[("steps",)])

    def steps(lst, path, in_branch):
        for i, st in enumerate(lst):
            label = f"{where}: krok {st.get('id')!r}" if isinstance(st, dict) and "id" in st \
                else f"{where}: {path_str(path + (i,))}"
            kind = step_kind(st)
            if kind is None:
                have = [k for k in STEP_KINDS if isinstance(st, dict) and k in st]
                errs.append(f"{label}: krok musí mít právě jeden typ ({', '.join(STEP_KINDS)}), má: "
                            f"{', '.join(have) or 'žádný'}")
                continue
            if in_branch and kind == "output":
                errs.append(f"{label}: output nesmí být uvnitř větve parallel/switch")
                continue
            nested = nested_lists(st)
            errs.extend(schema_errors("scenario", st, label, ref=f"{kind}_step", skip=[p for p, _ in nested]))
            for p, lst2 in nested:
                steps(lst2, path + (i,) + p, True)

    if isinstance(data.get("steps"), list):
        steps(data["steps"], ("steps",), False)
    return errs
