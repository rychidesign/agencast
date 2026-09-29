"""Documentation, skills and examples from the installed package or clone."""
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
