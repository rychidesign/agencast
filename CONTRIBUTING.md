# Contributing

Describe bugs and suggestions in GitHub Issues; send changes as pull requests on GitHub.
Describe the problem, the resulting behavior and the checks you ran; do not send keys or `.env`.
Security reports are covered by [SECURITY.md](SECURITY.md).

Documentation, comments, messages, code and all names (identifiers, file names, examples, fixtures) are written in English.
The GUI is English by default with a Czech translation in `ui/src/locales/cs.json`, the only place for Czech text;
every new UI string goes through `t()` and is added to both locale files.
The spec v1 formats are frozen; only backward-compatible extensions per [DESIGN §5.9](docs/DESIGN.md) are allowed.
Guidelines and checks are in [CLAUDE.md](CLAUDE.md). From the clone root:

```bash
(cd framework && uv sync --all-groups && uv run pytest -q)
uv run --project framework python docs/spec/tools/check.py
(cd ui && npm ci && npm run typecheck && npx vitest run && npm run build)
(cd ui && npx playwright install --with-deps chromium && npm run e2e)
```

There is no commitment to accept contributions, provide support, or respond within any deadline.
