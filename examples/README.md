# AgenCast examples

Each folder is a standalone project with its own `workflows/`, runs and outputs.
- `showcase/`: a post for Lumen, a fictional small coffee roastery and café; images, `call` and an MCP book catalog.
- `tutorial/`: solutions and exercises for the [tutorials](../docs/tutorials/).

From the repository root, after installing AgenCast:
```bash
agencast --project examples/showcase validate ig-post --offline
agencast --project examples/showcase run ig-post -i topic="new coffee" --fake examples/showcase/fake/ig-post.yaml
agencast --project examples/tutorial validate tutorial-07-composition --offline
```

`--fake` replaces only model calls: no model cost and no OpenRouter key.
A `task` step still starts the real MCP servers from `mcp.yaml`; the sample
`filesystem` server uses `npx`, needs Node.js and downloads the package on first run.
`--callback-url` sends a real callback (and needs its signing secret).
Only scenarios without `task` (including called scenarios)
and without `--callback-url` are guaranteed to stay offline, for example `ig-post`.

For live runs, copy `.env.example` to `.env` in the project and fill in the key.
`tone-check.yaml` is in both projects: tutorial 7 uses it to show scenario composition; keep the copies identical.
The Instagram MCP server in showcase uses a sample address; publishing requires your own server and configuration.
Keep your own content and keys outside the repository; the example configuration is for learning.
