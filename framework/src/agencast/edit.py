"""Editační operace pro GUI (api.md „Editace“, DESIGN „Obálky“): soubor je pravda.

Každá operace přečte soubor, ověří otisk (sha256 obsahu, který klient načetl),
upraví ho, ověří kopii `workflows/` se změnou (`describe_project` = validate
bez kontroly modelů) a teprve pak zapíše atomicky (dočasný soubor +
`os.replace`). Změna nesmí do projektu přidat chybu; chyby, které tam už
byly, ji neblokují — jinak by dva rozbité soubory, které na sebe odkazují,
nešly opravit jeden po druhém.

YAML se upravuje round-trip přes ruamel.yaml (komentáře, pořadí klíčů,
prázdné řádky, uvozovky). ruamel přepisuje mezery ve flow mapách
(`{ a: 1 }` → `{a: 1}`) a zarovnání, proto nezměněné řádky zůstávají doslova
z původního souboru (`_keep_lines`).
"""
import io
import os
import re
import shutil
import tempfile
import threading
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString, SingleQuotedScalarString

from . import ConfigErrors
from .loader import LoadError, load_yaml, nested_lists
from .projects import NAME, describe_project, etag

_N = NAME.pattern
FILES = re.compile(rf"agents/{_N}\.md|scenarios/{_N}\.yaml|skills/{_N}/SKILL\.md|config\.yaml|mcp\.yaml")
FRONTMATTER = re.compile(r"(---\n)(.*?\n)(---\n)(.*)", re.S)  # jako loader.read_frontmatter
HEADER = ("description", "inputs", "outputs", "callable")  # name a version = jméno souboru a formát, steps = operace kroků
CONFIG = ("models", "limits", "storage", "webhook", "callback", "openrouter")  # openrouter jen api_key_env

# ponytail: jeden zámek na všechny zápisy v procesu; ruční úprava souboru mezi čtením a os.replace se nepozná (okno ms)
_lock = threading.Lock()


class Conflict(Exception):
    """Otisk nesedí — soubor mezitím změnil někdo jiný. `etag` = aktuální otisk (None = soubor není)."""

    def __init__(self, etag: str | None):
        super().__init__(etag)
        self.etag = etag


class NotFound(Exception):
    """Neznámý soubor, cesta mimo povolené soubory nebo adresa kroku, která ve scénáři není."""


# --- jádro: otisk → změna → validace kopie → atomický zápis -------------------------

def _path(root: Path, rel: str) -> Path:
    wf = root / "workflows"
    p = wf / rel
    if not FILES.fullmatch(rel) or not p.resolve().is_relative_to(wf.resolve()):
        raise NotFound(f"{rel}: upravit jde jen agents/<jméno>.md, scenarios/<jméno>.yaml, "
                       "skills/<jméno>/SKILL.md, config.yaml a mcp.yaml")
    return p


def _read(p: Path) -> str | None:
    return p.read_bytes().decode() if p.is_file() else None  # bez překladu konců řádků — otisk = bajty souboru


def _write(p: Path, text: str | None):
    if text is None:
        p.unlink(missing_ok=True)
        if p.name == "SKILL.md":
            try:
                p.parent.rmdir()  # jen prázdnou složku; další soubory skillu zůstanou
            except OSError:
                pass
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_bytes(text.encode())
    os.replace(tmp, p)


def _errors(root: Path) -> list[str]:
    """Všechny chyby projektu tak, jak je zná `validate` (config, mcp.yaml, scénáře, agenti, skilly)."""
    try:
        d = describe_project(root)
    except ConfigErrors as e:
        return e.errors
    return list(dict.fromkeys(d["errors"] + [e for k in ("scenarios", "agents", "skills") for x in d[k]
                                             for e in x["errors"]]))


def _errors_with(root: Path, rel: str, text: str | None) -> list[str]:
    """Chyby projektu, kdyby soubor `rel` měl text `text` (None = smazaný); na disku se nic nemění."""
    # ponytail: kopie celé workflows/ při každé změně (ms u běžného projektu); velké skilly → kopírovat jen YAML/MD
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp).resolve()
        shutil.copytree(root / "workflows", t / "workflows")
        _write(t / "workflows" / rel, text)
        return [e.replace(str(t), str(root)) for e in _errors(t)]


def _check(root: Path, rel: str, text: str | None) -> list[str]:
    """Chyby projektu po změně; chyba, která v projektu nebyla → ConfigErrors (nic se nezapíše)."""
    before = _errors(root)
    after = _errors_with(root, rel, text)
    if new := [e for e in after if e not in before]:
        raise ConfigErrors(new)
    return after


def validate_text(root, rel: str | None = None, text: Any = None) -> list[str]:
    """Chyby projektu bez zápisu: jak je na disku, nebo s jedním souborem `rel` nahrazeným textem `text`."""
    root = Path(root).resolve()
    if rel is None:
        return _errors(root)
    _path(root, rel)  # jen povolené soubory ve workflows/, jinak NotFound
    if not isinstance(text, str):
        raise ConfigErrors(["text: má být text"])
    return _errors_with(root, rel, text)


def _save(root, rel: str, tag: str | None, change: Callable[[str | None], str | None], *,
          create: bool = False) -> dict[str, Any]:
    """`change(starý text | None)` → nový text, None = smazat. Vrací `{etag, errors}` (errors = co v projektu zůstává)."""
    root = Path(root).resolve()
    p = _path(root, rel)
    with _lock:
        old = _read(p)
        if old is None and not create:
            raise NotFound(f"{rel}: soubor neexistuje")
        if tag != etag(old):
            raise Conflict(etag(old))
        new = change(old)
        errors = _check(root, rel, new)
        _write(p, new)
    return {"etag": etag(new), "errors": errors}


# --- round-trip YAML ------------------------------------------------------------------

def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # dlouhé prompty se nezalamují
    y.indent(mapping=2, sequence=4, offset=2)  # styl spec: "steps:\n  - id: …"
    return y


def _dump(y: YAML, data) -> str:
    out = io.StringIO()
    y.dump(data, out)
    return out.getvalue()


def _keep_lines(orig: str, before: str, after: str) -> str:
    """Řádky, které se úpravou nezměnily, vezme doslova z `orig` (dump `before` odpovídá `orig` řádek po řádku)."""
    o, b, a = orig.splitlines(True), before.splitlines(True), after.splitlines(True)
    if len(o) != len(b):
        return after
    out = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, b, a, autojunk=False).get_opcodes():
        out += o[i1:i2] if op == "equal" else a[j1:j2]
    text = "".join(out)
    try:  # pojistka: jiné odsazení originálu na hranici změny → celý výstup ruamel
        return text if load_yaml(text, "") == load_yaml(after, "") else after
    except LoadError:
        return after


def yaml_edit(text: str, change: Callable[[Any], None], where: str) -> str:
    """Upraví YAML v `text` funkcí `change(data)` (mění data na místě); bez změny vrací `text` beze změny."""
    y = _yaml()
    try:
        data = y.load(text)
    except YAMLError as e:
        raise ConfigErrors([f"{where}: YAML nejde upravit, oprav ho jako text (files/): {e}"]) from None
    if not isinstance(data, dict):
        raise ConfigErrors([f"{where}: soubor musí být mapa (klíč: hodnota), oprav ho jako text (files/)"])
    before = _dump(y, data)
    change(data)
    return _keep_lines(text, before, _dump(y, data))


def _new(v, old=None):
    """Hodnota z JSON do YAML: víc řádků → blok `|`, šablona `{{ }}` → dvojité uvozovky, jinak styl staré hodnoty."""
    if isinstance(v, str):
        if "\n" in v:
            return LiteralScalarString(v)
        if isinstance(old, (SingleQuotedScalarString, DoubleQuotedScalarString)):
            return type(old)(v)
        return DoubleQuotedScalarString(v) if "{{" in v else v
    if isinstance(v, dict):
        return CommentedMap((k, _new(x)) for k, x in v.items())
    if isinstance(v, list):
        return CommentedSeq(_new(x) for x in v)
    return v


def merge(node, patch: dict[str, Any]):
    """JSON Merge Patch (RFC 7396) do mapy ruamel: null klíč smaže, mapa se slučuje, jiná hodnota nahradí."""
    for k, v in patch.items():
        if v is None:
            node.pop(k, None)
        elif isinstance(v, dict):
            if not isinstance(node.get(k), dict):
                node[k] = CommentedMap()
            merge(node[k], v)
        else:
            node[k] = _new(v, node.get(k))


def _obj(v, what: str) -> dict[str, Any]:
    if not isinstance(v, dict):
        raise ConfigErrors([f"{what}: má být JSON objekt"])
    return v


def _only(patch: dict[str, Any], allowed, what: str):
    if bad := [k for k in patch if k not in allowed]:
        raise ConfigErrors([f"{what}: pole {', '.join(map(repr, bad))} tady měnit nejde (povolená: {', '.join(allowed)})"])


# --- scénář a adresa kroku ------------------------------------------------------------
# Adresa kroku = cesta v dokumentu scénáře: ["steps", 2], ["steps", 2, "parallel", "a", 0],
# ["steps", 4, "switch", "cases", "hravy", 0], ["steps", 4, "switch", "default", 0]. Bez posledního
# indexu ukazuje na seznam kroků (začátek větve). Stejnou vrací GET …/scenarios/<s> v poli `address`.

def _index(seg, lst: list[Any]) -> int:
    i = seg if isinstance(seg, int) and not isinstance(seg, bool) else int(seg) if str(seg).isdigit() else -1
    if not 0 <= i < len(lst):
        raise NotFound(f"adresa kroku: index {seg!r} v seznamu o {len(lst)} krocích není")
    return i


def _key(d, seg):
    k = next((k for k in d if str(k) == str(seg)), None) if isinstance(d, dict) else None
    if k is None:
        raise NotFound(f"adresa kroku: větev {seg!r} není")
    return d[k]


def resolve(data, address) -> tuple[list[Any], int | None]:
    """Adresa → (seznam kroků, index kroku); index None = adresa ukazuje na seznam (začátek větve/případu)."""
    if not isinstance(address, list) or address[:1] != ["steps"] or not isinstance(data, dict):
        raise NotFound(f"adresa kroku {address!r}: má být seznam začínající \"steps\"")
    lst, i, rest = data.get("steps"), None, list(address[1:])
    while rest:
        if not isinstance(lst, list):
            raise NotFound(f"adresa kroku {address!r}: není seznam kroků")
        i = _index(rest.pop(0), lst)
        if not rest:
            break
        st = lst[i] if isinstance(lst[i], dict) else {}
        match rest:
            case ["parallel", b, *more]:
                lst, rest = _key(st.get("parallel"), b), more
            case ["switch", "cases", c, *more]:
                lst, rest = _key((st.get("switch") or {}).get("cases"), c), more
            case ["switch", "default", *more]:
                lst, rest = _key(st.get("switch"), "default"), more
            case _:
                raise NotFound(f"adresa kroku {address!r}: za indexem má být parallel/<větev>, "
                               "switch/cases/<případ> nebo switch/default")
        i = None
    if not isinstance(lst, list):
        raise NotFound(f"adresa kroku {address!r}: není seznam kroků")
    return lst, i


def _step(data, address) -> tuple[list[Any], int]:
    lst, i = resolve(data, address)
    if i is None:
        raise NotFound(f"adresa {address!r} ukazuje na seznam kroků, ne na krok")
    return lst, i


def _drop_empty(steps, target: list[Any]):
    """Větev/případ/default, ze které odešel poslední krok, zmizí (prázdný seznam schéma nepovolí)."""
    for st in steps if isinstance(steps, list) else []:
        for p, lst in nested_lists(st):
            if lst is target and not lst:
                holder = st
                for k in p[:-1]:
                    holder = holder[k]
                del holder[p[-1]]
                return
            _drop_empty(lst, target)


def _scenario(root, name: str, tag, change: Callable[[Any], None]) -> dict[str, Any]:
    rel = f"scenarios/{name}.yaml"
    return _save(root, rel, tag, lambda text: yaml_edit(text or "", change, rel))


def set_header(root, name: str, tag, fields: Any) -> dict[str, Any]:
    """Hlavička scénáře (description, inputs, outputs, callable) jako merge patch."""
    _only(_obj(fields, "fields"), HEADER, "hlavička scénáře")
    return _scenario(root, name, tag, lambda d: merge(d, fields))


def add_step(root, name: str, tag, after, step: Any) -> dict[str, Any]:
    """Vloží krok za krok na adrese `after`, nebo na začátek seznamu, když `after` ukazuje na seznam."""
    _obj(step, "step")

    def change(d):
        lst, i = resolve(d, after)
        lst.insert(0 if i is None else i + 1, _new(step))
    return _scenario(root, name, tag, change)


def update_step(root, name: str, tag, address, fields: Any) -> dict[str, Any]:
    """Pole kroku jako merge patch (null smaže pole; i `id`, `when`, větve `parallel`)."""
    _obj(fields, "fields")

    def change(d):
        lst, i = _step(d, address)
        merge(lst[i], fields)
    return _scenario(root, name, tag, change)


def move_step(root, name: str, tag, address, to) -> dict[str, Any]:
    """Přesune krok za krok `to`, nebo na začátek seznamu `to`."""
    def change(d):
        src, i = _step(d, address)
        if isinstance(to, list) and [str(x) for x in to[:len(address)]] == [str(x) for x in address]:
            if len(to) == len(address):
                return  # za sebe sama = beze změny
            raise ConfigErrors([f"krok {address!r} nejde přesunout do vlastní větve"])
        dst, j = resolve(d, to)
        anchor = None if j is None else dst[j]
        st = src.pop(i)
        dst.insert(0 if anchor is None else next(n for n, x in enumerate(dst) if x is anchor) + 1, st)
        _drop_empty(d["steps"], src)
    return _scenario(root, name, tag, change)


def delete_step(root, name: str, tag, address) -> dict[str, Any]:
    def change(d):
        lst, i = _step(d, address)
        del lst[i]
        _drop_empty(d["steps"], lst)
    return _scenario(root, name, tag, change)


def _used(root, link: str, name: str, what: str):
    """Odmítne smazání, když na `name` vede vazba z describe_project (api.md `links`)."""
    users = [a for a, b in describe_project(Path(root).resolve())["links"][link] if b == name]
    if users:
        raise ConfigErrors([f"{what} '{name}' nejde smazat — používá ho: {', '.join(users)}"])


def delete_scenario(root, name: str, tag) -> dict[str, Any]:
    _used(root, "scenario_scenario", name, "scénář")
    return _save(root, f"scenarios/{name}.yaml", tag, lambda _: None)


# --- agent, skill, config -------------------------------------------------------------

def set_agent(root, name: str, tag, frontmatter: Any = None, body: Any = None) -> dict[str, Any]:
    """Frontmatter jako merge patch, tělo (Markdown) celé; None = beze změny. Nový agent potřebuje obojí."""
    rel = f"agents/{name}.md"
    patch = {} if frontmatter is None else _obj(frontmatter, "frontmatter")
    if body is not None and not isinstance(body, str):
        raise ConfigErrors(["body: má být text"])

    def change(text):
        if text is None:
            if frontmatter is None or body is None:
                raise ConfigErrors([f"{rel}: nový agent potřebuje frontmatter i body"])
            text = f"---\nversion: 1\nname: {name}\n---\n"
        m = FRONTMATTER.match(text)
        if not m:
            raise ConfigErrors([f"{rel}: chybí frontmatter mezi řádky --- (oprav ho jako text přes files/)"])
        fm = m[2] if frontmatter is None else yaml_edit(m[2], lambda d: merge(d, patch), rel)
        return m[1] + fm + m[3] + (m[4] if body is None else body)
    return _save(root, rel, tag, change, create=True)


def delete_agent(root, name: str, tag) -> dict[str, Any]:
    _used(root, "scenario_agent", name, "agent")
    return _save(root, f"agents/{name}.md", tag, lambda _: None)


def set_skill(root, name: str, tag, text: Any) -> dict[str, Any]:
    """Celý SKILL.md (frontmatter + tělo); nový skill založí."""
    return write_file(root, f"skills/{name}/SKILL.md", tag, text)


def delete_skill(root, name: str, tag) -> dict[str, Any]:
    _used(root, "agent_skill", name, "skill")
    return _save(root, f"skills/{name}/SKILL.md", tag, lambda _: None)


def set_config(root, tag, fields: Any) -> dict[str, Any]:
    """config.yaml jako merge patch: models, limits, storage, webhook, callback, openrouter.api_key_env.
    Tajemství se nezadávají — pole *_env jsou jména proměnných (schéma jiný tvar odmítne)."""
    _only(_obj(fields, "fields"), CONFIG, "config.yaml")
    if isinstance(fields.get("openrouter"), dict):
        _only(fields["openrouter"], ("api_key_env",), "config.yaml openrouter")
    return _save(root, "config.yaml", tag, lambda text: yaml_edit(text or "", lambda d: merge(d, fields), "config.yaml"))


# --- surový text (záložní editor GUI) ---------------------------------------------------

def read_file(root, rel: str) -> dict[str, Any]:
    """Text souboru s otiskem a rozparsovaným obsahem (`data`, u .md `frontmatter` a `body`), ať GUI neparsuje samo."""
    p = _path(Path(root).resolve(), rel)
    text = _read(p)
    if text is None:
        raise NotFound(f"{rel}: soubor neexistuje")
    out: dict[str, Any] = {"path": rel, "etag": etag(text), "text": text, "errors": []}
    try:
        if rel.endswith(".md"):
            m = FRONTMATTER.match(text.replace("\r\n", "\n"))
            if not m:
                raise LoadError(f"{rel}: chybí frontmatter mezi řádky ---")
            out |= {"frontmatter": load_yaml(m[2], rel, line_offset=1), "body": m[4]}
        else:
            out["data"] = load_yaml(text, rel)
    except LoadError as e:
        out["errors"] = [str(e)]
    return out


def write_file(root, rel: str, tag, text: Any) -> dict[str, Any]:
    """Celý text souboru; nový soubor (otisk null) jen v povolených cestách."""
    if not isinstance(text, str):
        raise ConfigErrors(["text: má být text"])
    return _save(root, rel, tag, lambda _: text, create=True)
