"""Editing operations for the GUI (api.md “Editing”, DESIGN “Wrappers”): files are the source of truth.

Each operation reads the file, checks its hash (sha256 of the content loaded by the client),
edits it, validates a copy of `workflows/` with the change (`describe_project` = validate
without model checks) and then writes atomically (temporary file +
`os.replace`). A change must not introduce new project errors; existing errors
do not block it — otherwise two broken files referencing each other
could not be fixed one at a time.

YAML is edited with ruamel.yaml round-trip support (comments, key order,
blank lines, quotes). ruamel rewrites spacing and alignment in flow mappings
(`{ a: 1 }` → `{a: 1}`), so unchanged lines are kept verbatim
from the original file (`_keep_lines`).
"""
import errno
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
from ruamel.yaml.error import CommentMark, YAMLError
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, FoldedScalarString, LiteralScalarString, SingleQuotedScalarString
from ruamel.yaml.tokens import CommentToken

from . import ConfigErrors
from .loader import LoadError, load_yaml, nested_lists
from .projects import NAME, _check_name, describe_project, etag, text_tree
from .validate import MCP_DISABLED, load_config, own_file

_N = NAME.pattern
# No mcp.yaml: which programs and remote servers exist is the owner's decision, made on disk (config.md, DESIGN §5.2).
# The API neither serves nor writes it; the one exception is `_rename`, which follows an agent's new name in `agents:`.
FILES = re.compile(rf"agents/{_N}\.md|scenarios/{_N}\.yaml|skills/{_N}/SKILL\.md|config\.yaml")
FRONTMATTER = re.compile(r"(---\n)(.*?\n)(---\n)(.*)", re.S)  # same as loader.read_frontmatter
HEADER = ("description", "inputs", "outputs", "callable")  # name and version = file name and format; steps = step operations
CONFIG = ("models", "limits", "storage", "webhook", "callback", "openrouter", "runs_dir")
OPENROUTER = ("api_key_env", "jev_model")  # no base_url: the key could be sent elsewhere (config.md)

_lock = threading.Lock()


class Conflict(Exception):
    """Hash mismatch — someone else changed the file. `etag` = current hash (None = no file)."""

    def __init__(self, etag: str | None):
        super().__init__(etag)
        self.etag = etag


class NotFound(Exception):
    """Unknown file, path outside allowed files, or step address absent from the scenario."""


# --- core: hash → change → validate copy → atomic write -------------------------

def _path(root: Path, rel: str, write: bool = False) -> Path:
    wf = root / "workflows"
    p = wf / rel
    if rel == "mcp.yaml":
        raise NotFound("mcp.yaml: only the project owner reads and edits this file, on disk — not through the API")
    # not wf.resolve(): a linked workflows/ is another tree; realpath: Python 3.12's resolve() raises on a link loop
    real, top = Path(os.path.realpath(p)), root.resolve() / "workflows"
    # a link leads only to a file the API serves under its own name: not out of workflows/, and not to mcp.yaml;
    # a write replaces the name itself (`_write`), in a directory that is no link to another one
    if not (FILES.fullmatch(rel) and real.is_relative_to(top) and FILES.fullmatch(real.relative_to(top).as_posix())
            and (not write or Path(os.path.realpath(p.parent)) == (top / rel).parent)):
        raise NotFound(f"{rel}: only these files can be edited: agents/<name>.md, scenarios/<name>.yaml, "
                       "skills/<name>/SKILL.md and config.yaml")
    return p


def _read(p: Path) -> str | None:  # isfile: a name too long for the file system is no file either (Path.is_file raises)
    return p.read_bytes().decode() if os.path.isfile(p) else None  # no newline conversion — hash = file bytes


def _write(p: Path, text: str | None, tag: str | None = None, *, check: bool = False):
    if text is None:
        if check and (current := etag(_read(p))) != tag:
            raise Conflict(current)
        p.unlink(missing_ok=True)
        if p.name == "SKILL.md":
            try:
                p.parent.rmdir()  # only remove empty folders; keep other skill files
            except OSError:
                pass
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.unlink(missing_ok=True)  # whatever is there — a leftover, or a link planted in a directory others write to —
    with open(tmp, "xb") as f:   # is not written through: "x" creates the file and never follows a link
        try:  # the replaced file keeps its mode (an owner's 0600 on a file with keys), set before the content is there
            os.fchmod(f.fileno(), p.stat().st_mode & 0o7777)
        except FileNotFoundError:
            pass
        f.write(text.encode())
    if check and (current := etag(_read(p))) != tag:
        tmp.unlink(missing_ok=True)
        raise Conflict(current)
    os.replace(tmp, p)


def _errors(root: Path, registered: Path | None = None) -> list[str]:
    """All project errors known to `validate` (config, mcp.yaml, scenarios, agents, skills).
    `registered` = the project `root` is a copy of (its registry entry decides about MCP servers)."""
    try:
        d = describe_project(root, registered)
    except ConfigErrors as e:
        return e.errors
    return list(dict.fromkeys(d["errors"] + [e for k in ("scenarios", "agents", "skills") for x in d[k]
                                             for e in x["errors"]]))


def _copy(root: Path, tmp: str) -> Path:
    """A copy of `workflows/` in `tmp` to validate a change in. An entry that cannot be read (a link that leads
    nowhere, no permission) is left out: `_errors` of the project itself names it, so it is no new error. So is a
    link of an agent, skill or scenario that `validate.own_file` refuses: copied, it would be a file of this project.
    `config.yaml` and `mcp.yaml` are the owner's, also as a link to a file shared by several projects."""
    t, wf = Path(tmp).resolve(), root / "workflows"

    def refused(d, names):
        rel, top = Path(d).relative_to(wf), Path(os.path.realpath(wf))
        return [n for n in names if os.path.islink(Path(d) / n) and (rel / n).parts[0] in ("agents", "skills", "scenarios")
                and not (own_file(wf, (rel / n).as_posix()) if os.path.isfile(Path(d) / n)
                         else Path(os.path.realpath(Path(d) / n)).is_relative_to(top))]
    try:
        shutil.copytree(wf, t / "workflows", ignore=refused)
    except shutil.Error:  # raised after everything else was copied
        pass
    return t


def _errors_with(root: Path, rel: str, text: str | None) -> list[str]:
    """Project errors if file `rel` contained `text` (None = deleted); leave the project on disk unchanged."""
    return _errors_with_many(root, {rel: text})


def _added(before, after: list[str]) -> list[str]:
    """Errors a change adds. The error of an untrusted project (`validate`: MCP servers … are disabled) names the
    servers and shows only once its scenario has no other error, so using fewer servers or fixing that other error
    rewords or reveals it: it is not new in a scenario that had an error before."""
    def old(e):
        where = e.split(": ", 1)[0]
        return MCP_DISABLED in e and any(b.startswith((where + ": ", where + ", ")) for b in before)
    return [e for e in after if e not in before and not old(e)]


def _check(root: Path, rel: str, text: str | None) -> list[str]:
    """Project errors after a change; new errors → ConfigErrors (nothing is written)."""
    before = _errors(root)
    after = _errors_with(root, rel, text)
    if new := _added(before, after):
        raise ConfigErrors(new)
    return after


def _errors_with_many(root: Path, changes: dict[str, str | None]) -> list[str]:
    """Project errors after multiple simultaneous changes (None = deleted file). A name too long for the file system
    can hold no file: NotFound, as when it is read."""
    # ponytail: copy all workflows/ on each change (ms for typical projects); large skills → copy only YAML/MD
    with tempfile.TemporaryDirectory() as tmp:
        t = _copy(root, tmp)
        for rel, text in changes.items():
            try:
                _write(t / "workflows" / rel, text)
            except OSError as e:
                if e.errno != errno.ENAMETOOLONG:
                    raise
                raise NotFound(f"{rel}: {e.strerror}") from None
        return [e.replace(str(t), str(root)) for e in _errors(t, root)]


def _check_many(root: Path, changes: dict[str, str | None], old_name: str, new_name: str) -> list[str]:
    """Validate a rename as one change; existing errors with the new path/name do not block it."""
    before = {re.sub(rf"(?<![a-z0-9-]){re.escape(old_name)}(?![a-z0-9-])", new_name, e) for e in _errors(root)}
    after = _errors_with_many(root, changes)
    if new := _added(before, after):
        raise ConfigErrors(new)
    return after


def validate_text(root, rel: str | None = None, text: Any = None) -> list[str]:
    """Project errors without writing: current disk state, or file `rel` replaced with `text`."""
    root = Path(root).resolve()
    if rel is None:
        return _errors(root)
    _path(root, rel)  # only allowed files in workflows/, otherwise NotFound
    if not isinstance(text, str):
        raise ConfigErrors(["text: must be a string"])
    return _errors_with(root, rel, text)


def _save(root, rel: str, tag: str | None, change: Callable[[str | None], str | None], *,
          create: bool = False) -> dict[str, Any]:
    """`change(old text | None)` → new text, None = delete. Return `{etag, errors}` (remaining project errors)."""
    root = Path(root).resolve()
    p = _path(root, rel, True)
    with _lock:
        old = _read(p)
        if old is None and not create:
            raise NotFound(f"{rel}: file does not exist")
        if tag != etag(old):
            raise Conflict(etag(old))
        new = change(old)
        errors = _check(root, rel, new)
        _write(p, new, tag, check=True)
    return {"etag": etag(new), "errors": errors}


def create_path(root, folder: str, name: str) -> str:
    """Path of the file `POST …/scenarios` or `…/agents` creates from its template (projects.py): a valid name, at a
    place a write may reach — not through a linked `scenarios/` or `agents/`, and not a link waiting at the name."""
    _check_name(name, folder[:-1])
    rel = f"{folder}/{name}.{'yaml' if folder == 'scenarios' else 'md'}"
    _path(Path(root).resolve(), rel, True)
    return rel


# --- round-trip YAML ------------------------------------------------------------------

def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # do not wrap long prompts
    y.indent(mapping=2, sequence=4, offset=2)  # spec style: "steps:\n  - id: …"
    return y


def _free_texts(node, col: int = 0):
    """Keep every comment below a `|` or `>` text left of the text: written at the text's column or beyond, it is
    read as a part of it — of a prompt. That is where a comment lands that followed a deeper step before a step
    operation, or one below a blank line in a file indented wider than `_yaml` writes. It hangs on the text itself,
    or above the next entry: a step header that holds the tail of the step above (`_heads`), below another step now.
    `col` = the column of the keys (dashes) of block `node`, at least; each level adds two or more."""
    def left(tokens, col):
        for tok in tokens:
            tok.value = re.sub(rf"(?m)^[ \t]{{{col + 1},}}(?=#)", " " * col, tok.value)
    seq, above = isinstance(node, CommentedSeq), None
    for k, v in enumerate(node) if seq else node.items():
        c, at = node.ca.items.get(k) or [None] * 3, col
        while c[1] and isinstance(above, (CommentedMap, CommentedSeq)) and above and not above.fa.flow_style():
            above, at = above[next(reversed(above)) if isinstance(above, CommentedMap) else len(above) - 1], at + 2
        if c[1] and _own_line(above):  # the entry above ends with a text: left of the key that holds it
            left(c[1], at)
        if isinstance(v, (CommentedMap, CommentedSeq)) and not v.fa.flow_style():
            _free_texts(v, col + 2)
        elif _own_line(v) and c[0 if seq else 2]:
            left([c[0 if seq else 2]], col)
        above = v


def _dump(y: YAML, data) -> str:
    _free_texts(data)
    out = io.StringIO()
    y.dump(data, out)
    return out.getvalue()


def _keep_lines(orig: str, before: str, after: str) -> str:
    """Take unchanged lines verbatim from `orig` (`before` dump matches `orig` line by line)."""
    o, b, a = orig.splitlines(True), before.splitlines(True), after.splitlines(True)
    if len(o) != len(b):
        return after
    out = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, b, a, autojunk=False).get_opcodes():
        out += o[i1:i2] if op == "equal" else a[j1:j2]
    text = "".join(out)
    try:  # safeguard: different original indentation at the edit boundary → use the full ruamel output
        return text if load_yaml(text, "") == load_yaml(after, "") else after
    except LoadError:
        return after


def yaml_edit(text: str, change: Callable[[Any], None], where: str) -> str:
    """Edit YAML in `text` with `change(data)` (in place); return `text` unchanged for a no-op."""
    y = _yaml()
    try:
        data = y.load(text)
    except YAMLError as e:
        raise ConfigErrors([f"{where}: cannot edit YAML; fix it as text (files/): {e}"]) from None
    if not isinstance(data, dict):
        raise ConfigErrors([f"{where}: file must be a mapping (key: value), fix it as text (files/)"])
    before = _dump(y, data)
    change(data)
    return _keep_lines(text, before, _dump(y, data))


def _new(v, old=None):
    """JSON value to YAML: multiple lines → block `|`, template `{{ }}` → double quotes, otherwise keep the old style."""
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
    """Whether all mappings in `node` use flow style `{ … }`. New sibling mappings then use the same style
    (config.yaml `models: {alias: { id: … }}`), keeping file formatting consistent after edits."""
    maps = [x for x in node.values() if isinstance(x, CommentedMap)]
    return bool(maps) and all(x.fa.flow_style() for x in maps)


def _tail(node):
    """(holder, key, comment slot) of the deepest last entry of block `node`: ruamel hangs the blank lines and
    comments that follow the block there. None = an empty or flow node (then they hang on the next sibling)."""
    while isinstance(node, (CommentedMap, CommentedSeq)) and node and not node.fa.flow_style():
        k = next(reversed(node)) if isinstance(node, CommentedMap) else len(node) - 1
        v = node[k]
        if not (isinstance(v, (CommentedMap, CommentedSeq)) and v and not v.fa.flow_style()):
            return node, k, 2 if isinstance(node, CommentedMap) else 0
        node = v
    return None


def _own_line(v) -> bool:
    return isinstance(v, (LiteralScalarString, FoldedScalarString))  # `|` and `>` end their line, a comment token after other values does


def _lines(tokens) -> str:
    """Comment tokens that stand on lines of their own, as the text of those lines."""
    return "".join(t.value if not t.value.strip() else " " * t.start_mark.column + t.value for t in tokens or ())


def _take_tail(node) -> str:
    """Detach the blank lines and comments that follow block `node` (an end-of-line comment stays on its line).
    ruamel hangs them on the last value, or — when that is a flow value — on the end of a block around it."""
    ends, n = "", node
    while isinstance(n, (CommentedMap, CommentedSeq)) and n and not n.fa.flow_style():
        ends, n.ca.end = _lines(n.ca.end) + ends, []  # the innermost block ends first
        n = n[next(reversed(n)) if isinstance(n, CommentedMap) else len(n) - 1]
    t = _tail(node)
    c = t and t[0].ca.items.get(t[1])
    if not (c and c[t[2]]):
        return ends
    tok = c[t[2]]
    # after a `|` or `>` text the token is whole lines, its first one indented only by the token's column
    eol, _, rest = ("", "", _lines([tok])) if _own_line(t[0][t[1]]) else tok.value.partition("\n")
    tok.value, c[t[2]] = eol + "\n", tok if eol else None
    return rest + ends


def _put_tail(node, rest: str):
    """Attach `rest` (from `_take_tail`) behind the last entry `node` has now."""
    t = _tail(node)
    if not (rest and t):
        return
    if not t[0][t[1]] and isinstance(t[0][t[1]], (CommentedMap, CommentedSeq)):
        t[0][t[1]].fa.set_flow_style()  # emptied: written as `{}` — as a flow value, or the comment would precede it
    if isinstance(t[0], CommentedSeq) and t[0].ca.end:  # a step list that keeps its own tail there (`_set_heads`):
        t[0].ca.end.append(CommentToken(rest, CommentMark(0), None))  # below it — the item's comment is written above
        return
    c = t[0].ca.items.setdefault(t[1], [None] * 4)
    if c[t[2]]:
        c[t[2]].value += rest
    else:
        c[t[2]] = CommentToken(rest if _own_line(t[0][t[1]]) else "\n" + rest, CommentMark(0), None)


def merge(node, patch: dict[str, Any]):
    """JSON Merge Patch (RFC 7396) into a ruamel mapping: null deletes, mappings merge, other values replace.
    Delete first so renames (`{"old": null, "new": {…}}`) determine style without the old mapping."""
    tail = _take_tail(node)  # a key appended to a step must not land below the blank line that separates the steps
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
    _put_tail(node, tail)


def _obj(v, what: str) -> dict[str, Any]:
    if not isinstance(v, dict):
        raise ConfigErrors([f"{what}: must be a JSON object"])
    return v


def _only(patch: dict[str, Any], allowed, what: str):
    if bad := [k for k in patch if k not in allowed]:
        raise ConfigErrors([f"{what}: fields {', '.join(map(repr, bad))} cannot be changed here (allowed: {', '.join(allowed)})"])


# --- scenario and step address ------------------------------------------------------------
# Step address = path in the scenario document: ["steps", 2], ["steps", 2, "parallel", "a", 0],
# ["steps", 4, "switch", "cases", "playful", 0], ["steps", 4, "switch", "default", 0]. Without the final
# index, it points to a step list (start of a branch). GET …/scenarios/<s> returns it in `address`.

def _index(seg, lst: list[Any]) -> int:
    i = seg if isinstance(seg, int) and not isinstance(seg, bool) else int(seg) if str(seg).isdigit() else -1
    if not 0 <= i < len(lst):
        raise NotFound(f"step address: index {seg!r} is outside a list of {len(lst)} steps")
    return i


def _key(d, seg):
    k = next((k for k in d if str(k) == str(seg)), None) if isinstance(d, dict) else None
    if k is None:
        raise NotFound(f"step address: branch {seg!r} does not exist")
    return d[k]


def resolve(data, address) -> tuple[list[Any], int | None]:
    """Address → (step list, step index); index None = address points to a list (start of a branch/case)."""
    if not isinstance(address, list) or address[:1] != ["steps"] or not isinstance(data, dict):
        raise NotFound(f"step address {address!r}: must be a list starting with \"steps\"")
    lst, i, rest = data.get("steps"), None, list(address[1:])
    while rest:
        if not isinstance(lst, list):
            raise NotFound(f"step address {address!r}: not a step list")
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
                raise NotFound(f"step address {address!r}: index must be followed by parallel/<branch>, "
                               "switch/cases/<case> or switch/default")
        i = None
    if not isinstance(lst, list):
        raise NotFound(f"step address {address!r}: not a step list")
    return lst, i


def _step(data, address) -> tuple[list[Any], int]:
    lst, i = resolve(data, address)
    if i is None:
        raise NotFound(f"address {address!r} points to a step list, not a step")
    return lst, i


def _holder(d, target: list[Any], key="steps", step=None):
    """(mapping, key, step) holding step list `target`: the scenario and "steps" (no step), or a parallel/switch,
    its branch and the step it is in."""
    if d.get(key) is target:
        return d, key, step
    for st in d.get(key) if isinstance(d.get(key), list) else []:
        for p, _ in nested_lists(st):
            holder = st
            for k in p[:-1]:
                holder = holder[k]
            if hit := _holder(holder, target, p[-1], st):
                return hit
    return None


def _drop_empty(d, target: list[Any], tail: str = ""):
    """Remove a branch/case/default after its last step is removed (the schema disallows empty lists). `tail` =
    what followed its list (the header of the step after the parallel/switch) stays where the list was."""
    holder, key, step = _holder(d, target)
    if target or step is None:
        return
    after = list(holder)[list(holder).index(key) + 1:]
    del holder[key]
    if tail and after:  # above the next branch
        c = holder.ca.items.setdefault(after[0], [None] * 4)
        c[1] = [CommentToken(tail, CommentMark(0), None), *(c[1] or [])]
    else:
        _put_tail(holder or step, tail)


# A step's header = the blank lines and comments directly above it (the examples number and describe their steps
# there): it belongs to the step below. ruamel keeps it in one of several places — after the last value of the step
# above or at the end of a block inside that step (`_take_tail`), in the item's own pre-comment, or, for the first
# step, in the pre-comment of the list (owned by the key that holds it). Step operations detach all of them
# (`_heads`), edit steps and headers side by side and attach them again (`_set_heads`).

def _heads(d, lst) -> list[str]:
    """Detach the header of each step of `lst` and what follows the last step: len(lst) + 1 texts of whole lines."""
    holder, key, _ = _holder(d, lst)
    above, first = holder.ca.items.get(key), lst.ca.comment
    heads = [_lines(above[3] if above and above[3] else first and first[1])]
    if above:
        above[3] = None
    if first:
        first[1] = None
    for i in range(1, len(lst)):
        own = lst.ca.items.get(i)
        heads.append(_take_tail(lst[i - 1]) + _lines(own and own[1]))
        if own:
            own[1] = None
    heads.append((_take_tail(lst[-1]) if lst else "") + _lines(lst.ca.end))
    lst.ca.end = []
    return heads


def _set_heads(d, lst, heads: list[str]):
    """Attach `heads` (from `_heads`, edited along with the steps) to the steps `lst` has now."""
    holder, key, _ = _holder(d, lst)
    for i, text in enumerate(heads[:len(lst)]):
        if text:  # one token of whole lines, written as it is
            tokens = [CommentToken(text, CommentMark(0), None)]
            if i:
                lst.ca.items.setdefault(i, [None] * 4)[1] = tokens
            else:
                holder.ca.items.setdefault(key, [None] * 4)[3] = tokens
    if lst and _tail(lst[-1]):
        _put_tail(lst[-1], heads[-1])
    elif heads[-1]:  # a flow last step or an emptied list: where ruamel keeps it then (`_heads` reads it back) —
        lst.ca.end = [CommentToken(heads[-1], CommentMark(0), None)]  # and writes it only for a list that has
        lst.ca.comment = lst.ca.comment or [None, None]               # a comment slot of its own


def _col(address) -> int:
    """Column of the `- ` of the step list at `address` (a list or one of its steps) as `_yaml` writes it."""
    rest, col = list(address[1:]), 2
    while rest[1:]:
        n = 3 if rest[1:3] == ["switch", "cases"] else 2
        rest, col = rest[1 + n:], col + 2 * n + 2
    return col


def _scenario(root, name: str, tag, change: Callable[[Any], None]) -> dict[str, Any]:
    rel = f"scenarios/{name}.yaml"
    return _save(root, rel, tag, lambda text: yaml_edit(text or "", change, rel))


# In-memory scenario operations shared by individual endpoints and batches (`batch`, `render`).

def _set_header(d, fields):
    _only(_obj(fields, "fields"), HEADER, "scenario header")
    merge(d, fields)


def _add_step(d, step, after=None):
    lst, i = resolve(d, ["steps"] if after is None else after)
    new, heads, at = _new(_obj(step, "step")), _heads(d, lst), 0 if i is None else i + 1
    lst.insert(at, new)
    heads.insert(at, "")  # below the step before it and above the header of the step after it
    _set_heads(d, lst, heads)


def _update_step(d, address, fields):
    lst, i = _step(d, address)
    merge(lst[i], _obj(fields, "fields"))


def _replace_step(d, address, step):
    lst, i = _step(d, address)
    new, heads = _new(_obj(step, "step")), _heads(d, lst)  # its header and the next step's are not part of the step
    lst[i] = new
    _set_heads(d, lst, heads)


def _move_step(d, address, to):
    src, i = _step(d, address)
    if isinstance(to, list) and [str(x) for x in to[:len(address)]] == [str(x) for x in address]:
        if len(to) == len(address):
            return  # moving after itself = no-op
        raise ConfigErrors([f"step {address!r} cannot be moved into its own branch"])
    dst, j = resolve(d, to)
    anchor = None if j is None else dst[j]
    heads = _heads(d, src)
    st, head = src.pop(i), heads.pop(i)  # the header moves with its step; the next step's stays where it is
    _set_heads(d, src, heads)
    tail = heads[-1]
    heads, at = _heads(d, dst), 0 if anchor is None else next(n for n, x in enumerate(dst) if x is anchor) + 1
    dst.insert(at, st)
    # at the indentation of its new list: left deeper, a comment below a `|` text would become a part of that text
    heads.insert(at, re.sub(r"(?m)^[ \t]+(?=\S)|^(?=\S)", " " * _col(to), head))
    _set_heads(d, dst, heads)
    _drop_empty(d, src, tail)


def _delete_step(d, address):
    lst, i = _step(d, address)
    heads = _heads(d, lst)
    del lst[i], heads[i]  # its own header goes with it; the next step keeps its header
    _set_heads(d, lst, heads)
    _drop_empty(d, lst, heads[-1])


TEMPLATE = re.compile(r"\{\{.*?\}\}", re.S)


def _refs_renamed(node, fix: Callable[[str], str], expr: bool = False, parent=None):
    """Apply `fix` to step expressions in place: entire `when`, `switch.value`, `set.*` fields; elsewhere only inside `{{ }}`."""
    if isinstance(node, str):
        return fix(node) if expr else TEMPLATE.sub(lambda m: fix(m[0]), node)
    for k, v in list(node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else []):
        new = _refs_renamed(v, fix, isinstance(node, dict) and (k == "when" or parent == "set" or
                                                                  (parent == "switch" and k == "value")), k)
        if isinstance(v, str) and new != v:
            node[k] = _new(new, v)
    return node


def _rename_step(d, address, new_id, rename_refs=True):
    """New step `id`; with `rename_refs`, rewrite `steps.<old>.` → `steps.<new>.` in all scenario steps."""
    lst, i = _step(d, address)
    if not isinstance(new_id, str) or not isinstance(lst[i], dict):
        raise ConfigErrors(["new_id: must be a string (step id)"])
    old = lst[i].get("id")
    lst[i]["id"] = _new(new_id, old)
    if rename_refs is True and isinstance(old, str) and old != new_id:
        ref = re.compile(rf"(?<![\w.])steps\.{re.escape(old)}(?=\.)")
        _refs_renamed(d.get("steps"), lambda t: ref.sub(lambda _: f"steps.{new_id}", t))


def _add_branch(d, address, name, steps=()):
    """New `parallel` branch / `switch` case; `steps` may be empty and filled by later batch operations."""
    lst, i = _step(d, address)
    st = lst[i] if isinstance(lst[i], dict) else {}
    holder = st.get("parallel") if "parallel" in st else (st.get("switch") or {}).get("cases") if "switch" in st else None
    if not isinstance(holder, dict):
        raise ConfigErrors([f"step {address!r}: branches can only be added to parallel or switch (cases)"])
    if not isinstance(name, str) or not name or any(str(k) == name for k in holder):
        raise ConfigErrors([f"name: {name!r} — must be a string and no branch/case with this name may already exist"])
    if not isinstance(steps, (list, tuple)):
        raise ConfigErrors(["steps: must be a list of steps"])
    if not holder:
        holder.fa.set_block_style()  # see _put_tail
    holder[name] = _new(list(steps))


OPS: dict[str, Callable[..., None]] = {
    "set_header": _set_header, "add_step": _add_step, "update_step": _update_step, "replace_step": _replace_step,
    "move_step": _move_step, "delete_step": _delete_step, "rename_step": _rename_step, "add_branch": _add_branch}


class OpError(ConfigErrors):
    """Batch operation `op` (zero-based) failed; nothing was written."""

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
        match = re.search(r"field ['\"]([^'\"]+)", message)
        if match:
            return match[1]
        match = re.match(r"(?:missing field|unknown field) ([\w.-]+)", message)
        if match:
            return match[1]
        match = re.match(r"([\w.-]+): ", message)
        if match:
            return match[1]
    return None


def _apply(d, ops: Any):
    """Apply batch operations to the same document; each address refers to the state after preceding operations."""
    if not isinstance(ops, list):
        raise ConfigErrors(["ops: must be a list of operations"])
    for n, op in enumerate(ops):
        kind = op.get("op") if isinstance(op, dict) else None
        step = _op_step(d, kind, op) if isinstance(op, dict) else None
        try:
            if not isinstance(kind, str) or kind not in OPS:
                raise ConfigErrors([f"op: unknown operation {kind!r} (allowed: {', '.join(OPS)})"])
            assert isinstance(op, dict)
            fn, args = OPS[kind], {k: v for k, v in op.items() if k != "op"}
            params = list(inspect.signature(fn).parameters.values())[1:]
            missing = [p.name for p in params if p.default is p.empty and p.name not in args]
            unknown = [k for k in args if k not in {p.name for p in params}]
            if missing or unknown:
                raise ConfigErrors([f"missing field {', '.join(missing)}" if missing else
                                    f"unknown field {', '.join(unknown)} (allowed: {', '.join(p.name for p in params)})"])
            fn(d, **args)
        except (ConfigErrors, NotFound) as e:
            errors = e.errors if isinstance(e, ConfigErrors) else [str(e)]
            raise OpError(n, [f"ops[{n}] {kind}: {m}" for m in errors], step, _op_field(errors)) from None


def set_header(root, name: str, tag, fields: Any) -> dict[str, Any]:
    """Scenario header (description, inputs, outputs, callable) as a merge patch."""
    _only(_obj(fields, "fields"), HEADER, "scenario header")
    return _scenario(root, name, tag, lambda d: _set_header(d, fields))


def add_step(root, name: str, tag, after, step: Any) -> dict[str, Any]:
    """Insert a step after the step at `after`, or at the start if `after` points to a list."""
    _obj(step, "step")
    return _scenario(root, name, tag, lambda d: _add_step(d, step, after))


def update_step(root, name: str, tag, address, fields: Any) -> dict[str, Any]:
    """Step fields as a merge patch (null deletes fields; includes `id`, `when`, `parallel` branches)."""
    _obj(fields, "fields")
    return _scenario(root, name, tag, lambda d: _update_step(d, address, fields))


def replace_step(root, name: str, tag, address, step: Any) -> dict[str, Any]:
    """Replace the entire step with `step` (supports null values, unlike merge patch)."""
    _obj(step, "step")
    return _scenario(root, name, tag, lambda d: _replace_step(d, address, step))


def move_step(root, name: str, tag, address, to) -> dict[str, Any]:
    """Move a step after step `to`, or to the start of list `to`."""
    return _scenario(root, name, tag, lambda d: _move_step(d, address, to))


def delete_step(root, name: str, tag, address) -> dict[str, Any]:
    return _scenario(root, name, tag, lambda d: _delete_step(d, address))


def batch(root, name: str, tag, ops: Any) -> dict[str, Any]:
    """Batch of scenario operations: one in-memory copy, one result validation, one write (or none).
    Operation error → `OpError` (`.op` = its index); new error in the result → `ConfigErrors`."""
    return _scenario(root, name, tag, lambda d: _apply(d, ops))


def render(root, name: str, tag, ops: Any) -> dict[str, Any]:
    """Batch without writing: `{text, tree, errors}` — resulting YAML, step tree (as in `GET …/scenarios/<s>`)
    and all project errors with this text. `tag` None = skip hash check."""
    root = Path(root).resolve()
    rel = f"scenarios/{name}.yaml"
    old = _read(_path(root, rel))
    if old is None:
        raise NotFound(f"{rel}: file does not exist")
    if tag is not None and tag != etag(old):
        raise Conflict(etag(old))
    text = yaml_edit(old, lambda d: _apply(d, ops), rel)
    return {"text": text, "tree": text_tree(text, rel), "errors": _errors_with(root, rel, text)}


def render_text(root, name: str, text: Any) -> dict[str, Any]:
    """Scenario tree and errors from draft YAML text, without writing."""
    root, rel = Path(root).resolve(), f"scenarios/{name}.yaml"
    _path(root, rel)
    if not isinstance(text, str):
        raise ConfigErrors(["text: must be a string"])
    return {"tree": text_tree(text, rel), "errors": _errors_with(root, rel, text)}


def _used(root, link: str, name: str, what: str):
    """Reject deletion when `name` has an incoming link in describe_project (api.md `links`)."""
    users = [a for a, b in describe_project(Path(root).resolve())["links"][link] if b == name]
    if users:
        raise ConfigErrors([f"{what} '{name}' cannot be deleted — used by: {', '.join(users)}"])


def _rename_references(node, kind: str, old: str, new: str) -> bool:
    """Rewrite only scenario/agent references, not arbitrary text containing the same name."""
    changed = False
    if isinstance(node, dict):
        if kind == "scenario" and isinstance(node.get("call"), dict) and node["call"].get("scenario") == old:
            node["call"]["scenario"] = new
            changed = True
        if kind == "agent":
            for step_type in ("ask", "task"):
                step = node.get(step_type)
                if isinstance(step, dict) and step.get("agent") == old:
                    step["agent"] = new
                    changed = True
        for value in node.values():
            changed = _rename_references(value, kind, old, new) or changed
    elif isinstance(node, list):
        for value in node:
            changed = _rename_references(value, kind, old, new) or changed
    return changed


def _rename(root, kind: str, name: str, tag, new_name: str) -> dict[str, Any]:
    root = Path(root).resolve()
    ext = "yaml" if kind == "scenario" else "md"
    folder = "scenarios" if kind == "scenario" else "agents"
    old_rel, new_rel = f"{folder}/{name}.{ext}", f"{folder}/{new_name}.{ext}"
    old_path = _path(root, old_rel, True)
    with _lock:
        old_text = _read(old_path)
        if old_text is None:
            raise NotFound(f"{old_rel}: file does not exist")
        if tag != etag(old_text):
            raise Conflict(etag(old_text))
        if not isinstance(new_name, str):
            raise ConfigErrors(["name: must be a string"])
        _check_name(new_name, "scenario" if kind == "scenario" else "agent")
        new_path = _path(root, new_rel, True)
        if new_name == name:
            return {"name": name, "etag": etag(old_text), "changed": [], "errors": _errors(root)}
        if os.path.lexists(new_path):
            raise ConfigErrors([f"{new_path}: already exists — refusing to overwrite"])

        if kind == "scenario":
            new_text = yaml_edit(old_text, lambda data: data.__setitem__("name", new_name), old_rel)
        else:
            match = FRONTMATTER.match(old_text)
            if not match:
                raise ConfigErrors([f"{old_rel}: missing frontmatter between --- lines (fix it as text via files/)"])
            frontmatter = yaml_edit(match[2], lambda data: data.__setitem__("name", new_name), old_rel)
            new_text = match[1] + frontmatter + match[3] + match[4]

        references: dict[str, str] = {}
        bases: dict[str, str] = {}  # the text each reference was computed from
        for path in sorted((root / "workflows" / "scenarios").glob("*.yaml")):
            rel = path.relative_to(root / "workflows").as_posix()
            if rel == old_rel:
                continue
            text = _read(path)
            if text is None:
                continue
            found = False

            def edit_refs(data):
                nonlocal found
                if isinstance(data, dict):
                    found = _rename_references(data, kind, name, new_name)

            try:
                updated = yaml_edit(text, edit_refs, rel)
            except ConfigErrors:  # existing broken files remain errors, but renaming does not rewrite them
                continue
            if found and updated != text:
                references[rel], bases[rel] = updated, text

        if kind == "agent":
            path = root / "workflows" / "mcp.yaml"
            # a linked mcp.yaml is the owner's file elsewhere (one registry for several projects): the write would put
            # a copy in its place, which the owner's later edits — a revoked grant — no longer reach
            text = None if path.is_symlink() else _read(path)
            if text is not None:
                found = False

                def edit_mcp(data):
                    nonlocal found
                    servers = data.get("servers") if isinstance(data, dict) else None
                    for server in servers.values() if isinstance(servers, dict) else ():
                        agents = server.get("agents") if isinstance(server, dict) else None
                        if isinstance(agents, list):
                            for i, agent in enumerate(agents):
                                if agent == name:
                                    agents[i] = new_name
                                    found = True

                # The only write the API makes to the owner's mcp.yaml: the renamed agent keeps its servers. It must
                # change nothing else — the file as the loader reads it is compared with the same substitution.
                try:
                    updated = yaml_edit(text, edit_mcp, "mcp.yaml")
                    expected = load_yaml(text, "mcp.yaml")
                    edit_mcp(expected)
                    same = load_yaml(updated, "mcp.yaml") == expected
                except (ConfigErrors, LoadError):  # a file that cannot be read stays as it is (and stays an error)
                    pass
                else:
                    if found and same and updated != text:
                        references["mcp.yaml"], bases["mcp.yaml"] = updated, text

        changes = {old_rel: None, new_rel: new_text, **references}
        errors = _check_many(root, changes, name, new_name)

        # Write updated files first; create the new path only after the final conflict check.
        if etag(_read(old_path)) != tag:
            raise Conflict(etag(_read(old_path)))
        paths = {rel: root / "workflows" / rel if rel == "mcp.yaml" else _path(root, rel, True)  # mcp.yaml is not in FILES
                 for rel in sorted(references)}
        # Files edited on disk are not under `_lock`: one that changed since it was read (the owner revoking a grant
        # in mcp.yaml while the rename was validated) must not be written back from the old text. Nothing is written
        # yet; a retry with the same fingerprint works from the current files.
        if any(_read(path) != bases[rel] for rel, path in paths.items()):
            raise Conflict(tag)
        for rel, path in paths.items():
            _write(path, references[rel], etag(bases[rel]), check=True)
        if _read(old_path) is None or etag(_read(old_path)) != tag:
            raise Conflict(etag(_read(old_path)))
        if os.path.lexists(new_path):
            raise ConfigErrors([f"{new_path}: already exists — refusing to overwrite"])
        _write(new_path, new_text)
        _write(old_path, None, tag, check=True)

    return {"name": new_name, "etag": etag(new_text), "changed": sorted([new_rel, *references]), "errors": errors}


def rename_scenario(root, name: str, tag, new_name: str) -> dict[str, Any]:
    """Rename a scenario, its YAML name and `call.scenario` references in other scenarios."""
    return _rename(root, "scenario", name, tag, new_name)


def rename_agent(root, name: str, tag, new_name: str) -> dict[str, Any]:
    """Rename an agent, its frontmatter name and references in ask/task and mcp.yaml."""
    return _rename(root, "agent", name, tag, new_name)


def delete_scenario(root, name: str, tag) -> dict[str, Any]:
    _used(root, "scenario_scenario", name, "scenario")
    return _save(root, f"scenarios/{name}.yaml", tag, lambda _: None)


# --- agent, skill, config -------------------------------------------------------------

def set_agent(root, name: str, tag, frontmatter: Any = None, body: Any = None) -> dict[str, Any]:
    """Frontmatter as a merge patch, entire Markdown body; None = unchanged. New agents require both."""
    rel = f"agents/{name}.md"
    patch = {} if frontmatter is None else _obj(frontmatter, "frontmatter")
    if body is not None and not isinstance(body, str):
        raise ConfigErrors(["body: must be a string"])

    def change(text):
        if text is None:
            if frontmatter is None or body is None:
                raise ConfigErrors([f"{rel}: new agent requires both frontmatter and body"])
            text = f"---\nversion: 1\nname: {name}\n---\n"
        m = FRONTMATTER.match(text)
        if not m:
            raise ConfigErrors([f"{rel}: missing frontmatter between --- lines (fix it as text via files/)"])
        fm = m[2] if frontmatter is None else yaml_edit(m[2], lambda d: merge(d, patch), rel)
        return m[1] + fm + m[3] + (m[4] if body is None else body)
    return _save(root, rel, tag, change, create=True)


def delete_agent(root, name: str, tag) -> dict[str, Any]:
    _used(root, "scenario_agent", name, "agent")
    return _save(root, f"agents/{name}.md", tag, lambda _: None)


def set_skill(root, name: str, tag, text: Any) -> dict[str, Any]:
    """Entire SKILL.md (frontmatter + body); create the skill if new."""
    return write_file(root, f"skills/{name}/SKILL.md", tag, text)


def delete_skill(root, name: str, tag) -> dict[str, Any]:
    _used(root, "agent_skill", name, "skill")
    return _save(root, f"skills/{name}/SKILL.md", tag, lambda _: None)


def set_config(root, tag, fields: Any) -> dict[str, Any]:
    """config.yaml as a merge patch: models, limits, storage, webhook, callback, runs_dir, openrouter.api_key_env
    and openrouter.jev_model. No secret values — *_env fields are variable names (enforced by the schema)."""
    _only(_obj(fields, "fields"), CONFIG, "config.yaml")
    if isinstance(fields.get("openrouter"), dict):
        _only(fields["openrouter"], OPENROUTER, "config.yaml openrouter")
    return _save(root, "config.yaml", tag, lambda text: yaml_edit(text or "", lambda d: merge(d, fields), "config.yaml"))


# --- raw text (fallback GUI editor) ---------------------------------------------------

def read_file(root, rel: str) -> dict[str, Any]:
    """File text with hash and parsed content (`data`, or `frontmatter` and `body` for .md), so the GUI need not parse it."""
    p = _path(Path(root).resolve(), rel)
    text = _read(p)
    if text is None:
        raise NotFound(f"{rel}: file does not exist")
    out: dict[str, Any] = {"path": rel, "etag": etag(text), "text": text, "errors": []}
    try:
        if rel.endswith(".md"):
            m = FRONTMATTER.match(text.replace("\r\n", "\n"))
            if not m:
                raise LoadError(f"{rel}: missing frontmatter between --- lines")
            out |= {"frontmatter": load_yaml(m[2], rel, line_offset=1), "body": m[4]}
        else:
            out["data"] = load_yaml(text, rel)
    except LoadError as e:
        out["errors"] = [str(e)]
    if rel == "config.yaml" and not out["errors"]:  # schema and variables as well as syntax (0.7.0)
        load_config(p.parent, out["errors"])
    elif not out["errors"]:  # 0.8.0: validation errors as for a file in GET /projects/<p>
        out["errors"] = _file_errors(Path(root).resolve(), rel)
    return out


def _file_errors(root: Path, rel: str) -> list[str]:
    """Scenario, agent or skill `errors` from `describe_project`; config.yaml errors if that file is broken."""
    try:
        d = describe_project(root)
    except ConfigErrors as e:
        return e.errors
    kind, name = rel.split("/")[:2]
    return next((x["errors"] for x in d[kind] if x["name"] == name.removesuffix(".yaml").removesuffix(".md")), [])


def file_etag(root, rel: str) -> str:
    """File hash only (`HEAD …/files/<path>`, `?etag_only=1`) — without parsing or validation."""
    text = _read(_path(Path(root).resolve(), rel))
    if text is None:
        raise NotFound(f"{rel}: file does not exist")
    return etag(text) or ""


def write_file(root, rel: str, tag, text: Any) -> dict[str, Any]:
    """Entire file text; new files (null hash) only at allowed paths."""
    if not isinstance(text, str):
        raise ConfigErrors(["text: must be a string"])
    return _save(root, rel, tag, lambda _: text, create=True)
