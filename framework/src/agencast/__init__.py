"""AgenCast — jádro frameworku (DESIGN D3).

Vrstvy: loader (čtení souborů), validate (statické kontroly), expressions
(výrazy a šablony), engine (běh scénáře), providers (OpenRouter + falešný),
record (záznam běhu, report.html), mcp_client (MCP servery), task (krok task,
dedupe_key), server (webhook), api (veřejné API pro obálky), cli.
"""
__version__ = "0.3.0"

# Verze formátů, které framework umí číst (DESIGN §5.9 bod 6).
FORMAT_VERSIONS = (1,)

# Třídy chyb podle scenario.md §6.
ERROR_CLASSES = ("transient", "schema", "content", "budget", "timeout", "config",
                 "expression", "fail", "internal")


class AgencastError(Exception):
    """Chyba s třídou ze spec §6.

    `final` = třída po vyčerpání `retry` (např. chybějící cena → `budget`),
    `fatal` = on_error: continue ji nepřebije (rozpočet/čas celého běhu).
    """

    def __init__(self, cls: str, message: str, *, step: str | None = None,
                 http_status: int | None = None, retry_after: float | None = None,
                 final: str | None = None, fatal: bool = False):
        assert cls in ERROR_CLASSES, cls
        super().__init__(message)
        self.cls, self.message, self.step = cls, message, step
        self.http_status, self.retry_after, self.final, self.fatal = http_status, retry_after, final, fatal
        self.logged = False  # událost `error` už je v záznamu

    def __str__(self):
        return f"{self.cls}: {self.message}"


class ConfigErrors(Exception):
    """Seznam chyb `config` z validate (všechny najednou, ne jen první)."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors
