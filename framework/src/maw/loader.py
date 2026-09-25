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

# ponytail: schémata se čtou z repozitáře vedle frameworku; nasazení bez repa (Modal) je přibalí do image
SPEC_SCHEMAS = Path(__file__).resolve().parents[3] / "docs" / "spec" / "schema"
STEP_KINDS = ("ask", "task", "jev", "image", "parallel", "switch", "call", "set", "fail", "output")


class Yaml12Loader(yaml.SafeLoader):
    """SafeLoader bez resolverů YAML 1.1: booleany jen true/false, `yes`/`on`
    a `4:5` a datum jsou text, duplicitní klíč je chyba s řádkem (spec B6)."""

    def construct_mapping(self, node, deep=False):
        seen = {}
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, (str, int, float, bool)) and key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicitní klíč '{key}' (poprvé na řádku {seen[key]})", key_node.start_mark)
            seen[key] = key_node.start_mark.line + 1
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
    try:
        return yaml.load(text, Loader=Yaml12Loader)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = f", řádek {mark.line + 1 + line_offset}" if mark else ""
        problem = getattr(e, "problem", None) or str(e)
        raise LoadError(f"{where}{line}: {problem}") from None


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


def schema_errors(kind: str, data, where: str, ref: str | None = None, skip=()) -> list[str]:
    """Chyby proti JSON Schema ze spec; `skip` = cesty, které se kontrolují zvlášť."""
    out = []
    for e in sorted(_validator(kind, ref).iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        p = tuple(e.absolute_path)
        if any(p[:len(s)] == s and len(p) > len(s) for s in skip):
            continue
        out.append(f"{where}: {path_str(p) + ': ' if p else ''}{describe_error(e)}")
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
