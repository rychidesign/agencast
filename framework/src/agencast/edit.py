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
import inspect
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
from .mcp_client import load_mcp
from .projects import NAME, describe_project, etag, text_tree
from .validate import load_config

_N = NAME.pattern
FILES = re.compile(rf"agents/{_N}\.md|scenarios/{_N}\.yaml|skills/{_N}/SKILL\.md|config\.yaml|mcp\.yaml")
FRONTMATTER = re.compile(r"(---\n)(.*?\n)(---\n)(.*)", re.S)  # jako loader.read_frontmatter
HEADER = ("description", "inputs", "outputs", "callable")  # name a version = jméno souboru a formát, steps = operace kroků
CONFIG = ("models", "limits", "storage", "webhook", "callback", "openrouter", "runs_dir")
OPENROUTER = ("api_key_env", "jev_model")  # base_url ne: jinam by odešel klíč (config.md)

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


def _write(p: Path, text: str | None, tag: str | None = None, *, check: bool = False):
    if text is None:
        if check and (current := etag(_read(p))) != tag:
            raise Conflict(current)
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
    if check and (current := etag(_read(p))) != tag:
        tmp.unlink(missing_ok=True)
        raise Conflict(current)
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
        _write(p, new, tag, check=True)
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


def _flow_siblings(node) -> bool:
    """Jsou všechny mapy v `node` v řádkovém stylu `{ … }`? Nová sourozenecká mapa pak dostane stejný styl
    (config.yaml `models: {alias: { id: … }}`), ať soubor po úpravě vypadá jednotně."""
    maps = [x for x in node.values() if isinstance(x, CommentedMap)]
    return bool(maps) and all(x.fa.flow_style() for x in maps)


def merge(node, patch: dict[str, Any]):
    """JSON Merge Patch (RFC 7396) do mapy ruamel: null klíč smaže, mapa se slučuje, jiná hodnota nahradí.
    Mazání jde první, ať přejmenování (`{"stary": null, "novy": {…}}`) posuzuje styl už bez staré mapy."""
    for k, v in sorted(patch.items(), key=lambda kv: kv[1] is not None):
        if v is None:
            node.pop(k, None)
        elif isinstance(v, dict):
            if not isinstance(node.get(k), dict):
                flow = _flow_siblings(node)
                node[k] = CommentedMap()
                if flow:
                    node[k].fa.set_flow_style()
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


# Operace nad dokumentem scénáře v paměti: jednotlivé endpointy i dávka (`batch`, `render`) volají tytéž.

def _set_header(d, fields):
    _only(_obj(fields, "fields"), HEADER, "hlavička scénáře")
    merge(d, fields)


def _add_step(d, step, after=None):
    lst, i = resolve(d, ["steps"] if after is None else after)
    lst.insert(0 if i is None else i + 1, _new(_obj(step, "step")))


def _update_step(d, address, fields):
    lst, i = _step(d, address)
    merge(lst[i], _obj(fields, "fields"))


def _replace_step(d, address, step):
    lst, i = _step(d, address)
    lst[i] = _new(_obj(step, "step"))


def _move_step(d, address, to):
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


def _delete_step(d, address):
    lst, i = _step(d, address)
    del lst[i]
    _drop_empty(d["steps"], lst)


TEMPLATE = re.compile(r"\{\{.*?\}\}", re.S)


def _refs_renamed(node, fix: Callable[[str], str], expr: bool = False, parent=None):
    """Přepíše `fix` výrazy v krocích na místě: celé pole `when`, `switch.value`, `set.*`, jinde jen uvnitř `{{ }}`."""
    if isinstance(node, str):
        return fix(node) if expr else TEMPLATE.sub(lambda m: fix(m[0]), node)
    for k, v in list(node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else []):
        new = _refs_renamed(v, fix, isinstance(node, dict) and (k == "when" or parent == "set" or
                                                                  (parent == "switch" and k == "value")), k)
        if isinstance(v, str) and new != v:
            node[k] = _new(new, v)
    return node


def _rename_step(d, address, new_id, rename_refs=True):
    """Nové `id` kroku; s `rename_refs` přepíše `steps.<staré>.` → `steps.<nové>.` ve všech krocích scénáře."""
    lst, i = _step(d, address)
    if not isinstance(new_id, str) or not isinstance(lst[i], dict):
        raise ConfigErrors(["new_id: má být text (id kroku)"])
    old = lst[i].get("id")
    lst[i]["id"] = _new(new_id, old)
    if rename_refs is True and isinstance(old, str) and old != new_id:
        ref = re.compile(rf"(?<![\w.])steps\.{re.escape(old)}(?=\.)")
        _refs_renamed(d.get("steps"), lambda t: ref.sub(lambda _: f"steps.{new_id}", t))


def _add_branch(d, address, name, steps=()):
    """Nová větev kroku `parallel` / nový případ `switch`; `steps` smí být prázdné, doplní je další operace dávky."""
    lst, i = _step(d, address)
    st = lst[i] if isinstance(lst[i], dict) else {}
    holder = st.get("parallel") if "parallel" in st else (st.get("switch") or {}).get("cases") if "switch" in st else None
    if not isinstance(holder, dict):
        raise ConfigErrors([f"krok {address!r}: větev jde přidat jen do parallel nebo switch (cases)"])
    if not isinstance(name, str) or not name or any(str(k) == name for k in holder):
        raise ConfigErrors([f"name: {name!r} — má být text a větev/případ tohoto jména ještě nesmí být"])
    if not isinstance(steps, (list, tuple)):
        raise ConfigErrors(["steps: má být seznam kroků"])
    holder[name] = _new(list(steps))


OPS: dict[str, Callable[..., None]] = {
    "set_header": _set_header, "add_step": _add_step, "update_step": _update_step, "replace_step": _replace_step,
    "move_step": _move_step, "delete_step": _delete_step, "rename_step": _rename_step, "add_branch": _add_branch}


class OpError(ConfigErrors):
    """Operace dávky číslo `op` (od 0) nešla provést; nic se nezapsalo."""

    def __init__(self, op: int, errors: list[str], step: str | None = None, field: str | None = None):
        super().__init__(errors)
        self.op, self.step, self.field = op, step, field


def _op_step(d, kind, op) -> str | None:
    if kind == "add_step":
        step = op.get("step")
        return step.get("id") if isinstance(step, dict) and isinstance(step.get("id"), str) else None
    try:
        address = op.get("address")
        if isinstance(address, list):
            steps, index = _step(d, address)
            step = steps[index]
            return step.get("id") if isinstance(step, dict) and isinstance(step.get("id"), str) else None
    except (ConfigErrors, NotFound):
        pass
    return None


def _op_field(errors: list[str]) -> str | None:
    for message in errors:
        match = re.search(r"pole ['\"]([^'\"]+)", message)
        if match:
            return match[1]
        match = re.match(r"(?:chybí pole|neznámé pole) ([\w.-]+)", message)
        if match:
            return match[1]
        match = re.match(r"([\w.-]+): ", message)
        if match:
            return match[1]
    return None


def _apply(d, ops: Any):
    """Operace dávky po jedné nad týmž dokumentem; adresy každé platí pro stav po předchozích."""
    if not isinstance(ops, list):
        raise ConfigErrors(["ops: má být seznam operací"])
    for n, op in enumerate(ops):
        kind = op.get("op") if isinstance(op, dict) else None
        step = _op_step(d, kind, op) if isinstance(op, dict) else None
        try:
            if not isinstance(kind, str) or kind not in OPS:
                raise ConfigErrors([f"op: {kind!r} neznám (povolené: {', '.join(OPS)})"])
            assert isinstance(op, dict)
            fn, args = OPS[kind], {k: v for k, v in op.items() if k != "op"}
            params = list(inspect.signature(fn).parameters.values())[1:]
            missing = [p.name for p in params if p.default is p.empty and p.name not in args]
            unknown = [k for k in args if k not in {p.name for p in params}]
            if missing or unknown:
                raise ConfigErrors([f"chybí pole {', '.join(missing)}" if missing else
                                    f"neznámé pole {', '.join(unknown)} (povolená: {', '.join(p.name for p in params)})"])
            fn(d, **args)
        except (ConfigErrors, NotFound) as e:
            errors = e.errors if isinstance(e, ConfigErrors) else [str(e)]
            raise OpError(n, [f"ops[{n}] {kind}: {m}" for m in errors], step, _op_field(errors)) from None


def set_header(root, name: str, tag, fields: Any) -> dict[str, Any]:
    """Hlavička scénáře (description, inputs, outputs, callable) jako merge patch."""
    _only(_obj(fields, "fields"), HEADER, "hlavička scénáře")
    return _scenario(root, name, tag, lambda d: _set_header(d, fields))


def add_step(root, name: str, tag, after, step: Any) -> dict[str, Any]:
    """Vloží krok za krok na adrese `after`, nebo na začátek seznamu, když `after` ukazuje na seznam."""
    _obj(step, "step")
    return _scenario(root, name, tag, lambda d: _add_step(d, step, after))


def update_step(root, name: str, tag, address, fields: Any) -> dict[str, Any]:
    """Pole kroku jako merge patch (null smaže pole; i `id`, `when`, větve `parallel`)."""
    _obj(fields, "fields")
    return _scenario(root, name, tag, lambda d: _update_step(d, address, fields))


def replace_step(root, name: str, tag, address, step: Any) -> dict[str, Any]:
    """Celý krok nahradí `step` (na rozdíl od merge patch umí hodnotu null)."""
    _obj(step, "step")
    return _scenario(root, name, tag, lambda d: _replace_step(d, address, step))


def move_step(root, name: str, tag, address, to) -> dict[str, Any]:
    """Přesune krok za krok `to`, nebo na začátek seznamu `to`."""
    return _scenario(root, name, tag, lambda d: _move_step(d, address, to))


def delete_step(root, name: str, tag, address) -> dict[str, Any]:
    return _scenario(root, name, tag, lambda d: _delete_step(d, address))


def batch(root, name: str, tag, ops: Any) -> dict[str, Any]:
    """Dávka operací nad scénářem: jedna kopie v paměti, jedna validace výsledku, jeden zápis (nebo nic).
    Chyba operace → `OpError` (`.op` = její index); výsledek s novou chybou → `ConfigErrors`."""
    return _scenario(root, name, tag, lambda d: _apply(d, ops))


def render(root, name: str, tag, ops: Any) -> dict[str, Any]:
    """Dávka bez zápisu: `{text, tree, errors}` — výsledný YAML, strom kroků (jako `GET …/scenarios/<s>`)
    a všechny chyby projektu s tímto textem. `tag` None = otisk se nekontroluje."""
    root = Path(root).resolve()
    rel = f"scenarios/{name}.yaml"
    old = _read(_path(root, rel))
    if old is None:
        raise NotFound(f"{rel}: soubor neexistuje")
    if tag is not None and tag != etag(old):
        raise Conflict(etag(old))
    text = yaml_edit(old, lambda d: _apply(d, ops), rel)
    return {"text": text, "tree": text_tree(text, rel), "errors": _errors_with(root, rel, text)}


def render_text(root, name: str, text: Any) -> dict[str, Any]:
    """Strom a chyby scénáře z rozpracovaného YAML textu bez zápisu."""
    root, rel = Path(root).resolve(), f"scenarios/{name}.yaml"
    _path(root, rel)
    if not isinstance(text, str):
        raise ConfigErrors(["text: má být text"])
    return {"tree": text_tree(text, rel), "errors": _errors_with(root, rel, text)}


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
    """config.yaml jako merge patch: models, limits, storage, webhook, callback, runs_dir, openrouter.api_key_env
    a openrouter.jev_model. Tajemství se nezadávají — pole *_env jsou jména proměnných (schéma jiný tvar odmítne)."""
    _only(_obj(fields, "fields"), CONFIG, "config.yaml")
    if isinstance(fields.get("openrouter"), dict):
        _only(fields["openrouter"], OPENROUTER, "config.yaml openrouter")
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
    if rel in ("config.yaml", "mcp.yaml") and not out["errors"]:  # i schéma a proměnné, nejen syntaxe (0.7.0)
        (load_config if rel == "config.yaml" else load_mcp)(p.parent, out["errors"])
    elif not out["errors"]:  # 0.8.0: chyby validate jako u souboru v GET /projects/<p>
        out["errors"] = _file_errors(Path(root).resolve(), rel)
    return out


def _file_errors(root: Path, rel: str) -> list[str]:
    """`errors` scénáře, agenta nebo skillu z `describe_project`; s rozbitým config.yaml jeho chyby."""
    try:
        d = describe_project(root)
    except ConfigErrors as e:
        return e.errors
    kind, name = rel.split("/")[:2]
    return next((x["errors"] for x in d[kind] if x["name"] == name.removesuffix(".yaml").removesuffix(".md")), [])


def file_etag(root, rel: str) -> str:
    """Jen otisk souboru (`HEAD …/files/<cesta>`, `?etag_only=1`) — bez parsování a validace."""
    text = _read(_path(Path(root).resolve(), rel))
    if text is None:
        raise NotFound(f"{rel}: soubor neexistuje")
    return etag(text) or ""


def write_file(root, rel: str, tag, text: Any) -> dict[str, Any]:
    """Celý text souboru; nový soubor (otisk null) jen v povolených cestách."""
    if not isinstance(text, str):
        raise ConfigErrors(["text: má být text"])
    return _save(root, rel, tag, lambda _: text, create=True)
