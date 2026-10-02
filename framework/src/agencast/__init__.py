"""AgenCast — framework core (DESIGN D3).

Layers: loader (file reading), validate (static checks), expressions
(expressions and templates), engine (scenario execution), providers (OpenRouter + fake),
record (run record, report.html), mcp_client (MCP servers), task (task step,
dedupe_key), projects (project registry, templates, GUI descriptions), server
(webhook and read API), api (public API for wrappers), cli.
"""
__version__ = "0.18.0"

# Format versions the framework can read (DESIGN §5.9 item 6).
FORMAT_VERSIONS = (1,)

# Error classes defined in scenario.md §6.
ERROR_CLASSES = ("transient", "schema", "content", "budget", "timeout", "config",
                 "expression", "fail", "internal")


class AgencastError(Exception):
    """Error with a class from spec §6.

    `final` = class after exhausting `retry` (e.g. missing cost → `budget`),
    `fatal` = on_error: continue cannot override it (budget/timeout for the entire run).
    """

    def __init__(self, cls: str, message: str, *, step: str | None = None,
                 http_status: int | None = None, retry_after: float | None = None,
                 final: str | None = None, fatal: bool = False):
        assert cls in ERROR_CLASSES, cls
        super().__init__(message)
        self.cls, self.message, self.step = cls, message, step
        self.http_status, self.retry_after, self.final, self.fatal = http_status, retry_after, final, fatal
        self.logged = False  # the `error` event is already in the record

    def __str__(self):
        return f"{self.cls}: {self.message}"


class ConfigErrors(Exception):
    """List of `config` errors from validate (all at once, not just the first)."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors
