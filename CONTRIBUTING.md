# Přispívání / Contributing

Chyby a návrhy můžete popsat v GitHub Issues, změny posílejte jako pull requesty na GitHubu.
Popište problém, výsledné chování a provedené kontroly; neposílejte klíče ani `.env`.
Bezpečnostní hlášení řeší [SECURITY.md](SECURITY.md).

Dokumentace a komentáře jsou česky, názvy v kódu anglicky.
Formáty spec v1 jsou zmražené; přípustná jsou jen zpětně kompatibilní rozšíření podle [DESIGN §5.9](docs/DESIGN.md).
Pokyny a kontroly najdete v [CLAUDE.md](CLAUDE.md). Z kořene klonu:

```bash
(cd framework && uv sync --all-groups && uv run pytest -q)
uv run --project framework python docs/spec/tools/check.py
(cd ui && npm ci && npm run typecheck && npx vitest run && npm run build)
(cd ui && npx playwright install --with-deps chromium && npm run e2e)
```

Přijetí příspěvku, podpora ani termín odpovědi nejsou zaručené.

Send pull requests through GitHub with a problem description and check results.
Documentation and comments are Czech; code identifiers are English. Spec v1 is frozen;
changes must preserve compatibility. See [CLAUDE.md](CLAUDE.md) and the checks above.
There is no commitment to accept contributions, provide support, or respond within any deadline.
