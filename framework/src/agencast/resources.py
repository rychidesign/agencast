"""Documentation, skills and examples from the installed package or clone."""
import difflib
import os
from importlib.resources import files
from pathlib import Path

from . import ConfigErrors


def resource_dir(kind: str) -> Path:
    if kind not in {"skills", "docs", "examples"}:
        raise ConfigErrors([f"unknown resource kind: {kind}"])
    for path in (Path(str(files("agencast") / kind)), Path(__file__).resolve().parents[3] / kind):
        if path.is_dir():
            return path
    raise ConfigErrors([f"bundled {kind} missing; reinstall the agencast package or use a full repository clone"])


def docs_index() -> list[str]:
    """Paths of the bundled documentation, as `agencast docs` lists them."""
    root = resource_dir("docs").resolve()
    return ["getting-started.md", *(str(p.relative_to(root)) for section in ("tutorials", "spec")
                                    for p in sorted((root / section).glob("*.md")))]


def _text(p: Path) -> str | None:
    """A regular file's UTF-8 text; None for no file (isfile: a too long name → False) or a binary one (an image)."""
    try:
        return p.read_text(encoding="utf-8") if os.path.isfile(p) else None
    except UnicodeDecodeError:
        return None


BUNDLED = ("getting-started.md", "spec", "tutorials")  # what the wheel bundles (pyproject force-include)


def read_doc(path: str) -> str:
    """Text of a bundled document (`agencast docs show`, the MCP server's `get_guide`): a relative path to a text file
    (Markdown, the JSON schemas, the callback receiver) that stays inside docs/, links resolved; a miss names the
    closest paths. Only what the wheel bundles: a clone's other docs/ (design notes, archive) are no document."""
    root = resource_dir("docs").resolve()
    try:
        p = (root / path).resolve()
    except ValueError:  # a NUL byte: no such document
        p = root
    if Path(path).is_absolute() or not p.is_relative_to(root):
        raise ConfigErrors(["path must be relative and inside docs/"])
    if p.relative_to(root).parts[:1] not in [(b,) for b in BUNDLED] or (text := _text(p)) is None:
        names = sorted(str(f.relative_to(root)) for b in BUNDLED for f in (root / b, *(root / b).rglob("*"))
                       if _text(f) is not None)
        nearest = difflib.get_close_matches(path, names, n=5, cutoff=0)
        raise ConfigErrors([f"document {path} does not exist; closest matches: {', '.join(nearest)}"])
    return text
