# AgenCast — pokyny pro přispěvatele a agenty

Dokumentaci a komentáře pište česky, názvy v kódu anglicky.

Nejdřív čtěte `docs/DESIGN.md` a `docs/spec/`. Formáty v1 jsou zmražené;
rozšiřujte je jen zpětně kompatibilně podle DESIGN §5.9.

Důleřité je aby se zachovala architektura že soubory jsou zdroj pravdy a GUI je pouze nadstavba pro zobrazení a editaci.

## Struktura
- `framework/`: Python jádro, CLI a testy.
- `ui/`: webové GUI a jeho testy.
- `examples/showcase/`: samostatný projekt s ukázkami pro fiktivní kavárnu Lumen.
- `examples/tutorial/`: samostatný projekt k českým tutoriálům.
- `docs/`: návrh, specifikace a tutoriály.
- `skills/`: skilly pro kódovací agenty.

Konfigurace projektu (`config.yaml`, `mcp.yaml`, `commands.yaml`) určuje
oprávnění a patří vlastníkovi projektu. Příklady jsou v `examples/`;
vlastní projekty uchovávejte mimo repozitář.

## Kontroly
Z kořene repozitáře:

```bash
cd framework && uv sync --all-groups && uv run pytest -q
```

V dalším terminálu z kořene repozitáře:

```bash
cd ui && npm install && npm run typecheck && npx vitest run && npm run e2e
```

Nikdy necommitujte `.env` ani klíče; hodnoty tajemství nevypisujte ani nelogujte.
Před ostrým voláním použijte `validate --offline`, `--dry-run` a `--fake`.
GUI vystavujte jen v privátní síti. Nevyřešené chyby popište s přesnou hláškou.
