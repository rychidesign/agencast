"""Dokumentace, skilly a příklady z instalovaného balíčku nebo klonu."""
from importlib.resources import files
from pathlib import Path

from . import ConfigErrors


def resource_dir(kind: str) -> Path:
    if kind not in {"skills", "docs", "examples"}:
        raise ConfigErrors([f"neznámý druh zdrojů: {kind}"])
    for path in (Path(str(files("agencast") / kind)), Path(__file__).resolve().parents[3] / kind):
        if path.is_dir():
            return path
    raise ConfigErrors([f"chybí přibalené {kind}; přeinstaluj balíček agencast nebo použij úplný klon repozitáře"])
