# AgenCast — guidelines for contributors and agents

Documentation, comments, messages and code are written in English, and so are all
names: identifiers, file names, examples, fixtures, test data and model aliases.
The GUI is English by default with a Czech translation in `ui/src/locales/cs.json`,
the only place where Czech text lives: every new UI string goes through `t()` and
must be added to both `ui/src/locales/en.json` and `cs.json` (`i18n.test.ts` checks
that the keys match).

Read `docs/DESIGN.md` and `docs/spec/` first. The v1 formats are frozen;
extend them only in a backward-compatible way per DESIGN §5.9.

It is important to preserve the architecture in which files are the source of truth and the GUI is only a layer for viewing and editing.

## Structure
- `framework/`: Python core, CLI and tests.
- `ui/`: web GUI and its tests.
- `examples/showcase/`: standalone project with examples for the fictional Lumen café.
- `examples/tutorial/`: standalone project for the tutorials.
- `docs/`: design, specification and tutorials.
- `skills/`: skills for coding agents.

Project configuration (`config.yaml`, `mcp.yaml`, `commands.yaml`) determines
permissions and belongs to the project owner. Examples are in `examples/`;
keep your own projects outside the repository.

## Checks
From the repository root:

```bash
cd framework && uv sync --all-groups && uv run pytest -q
```

In another terminal, from the repository root:

```bash
cd ui && npm install && npm run typecheck && npx vitest run && npm run e2e
```

Never commit `.env` or keys; never print or log secret values.
Before a live call, use `validate --offline`, `--dry-run` and `--fake`.
Expose the GUI only on a private network. Describe unresolved errors with the exact message.
