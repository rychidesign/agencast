# Tutoriály `maw`

Sedm dílů od prvního agenta po provoz přes webhook. Každý díl staví na
předchozích, má skutečné výstupy z běhů a končí cvičením s řešením.
Řešení jsou soubory `tutorial-0N-*` ve `workflows/` a fixtury
v `framework/tests/golden/` — jsou to zároveň zlaté testy
(`cd framework && uv run pytest`).

| Díl | Čas | Útrata | Co se naučíš |
|---|---|---|---|
| [1 — První agent a první scénář](01-prvni-agent-a-scenar.md) | 15 min | ~0,0002 USD | agent, scénář s jedním krokem, `validate`, `--dry-run`, `--fake`, složka běhu, první ostrý běh |
| [2 — Navazování kroků](02-navazovani-kroku.md) | 15 min | ~0,0008 USD | `{{ steps.… }}`, `schema`, `set`, `output`, co když model pokazí JSON, hlášky `validate` |
| [3 — Rozhodování](03-rozhodovani.md) | 20 min | ~0,0007 USD | Jev, `when` + `fail`, `switch`, `default`, pravidla výrazů |
| [4 — Paralelně a s obrázkem](04-paralelne-a-obrazek.md) | 20 min | ~0,07 USD | `parallel`, krok `image`, třídy chyb, `budget_usd` a `timeout` |
| [5 — Od hraní k provozu](05-od-hrani-k-provozu.md) | 20 min | 0 USD | výměna modelu v `config.yaml`, zlaté testy, záznam do hloubky, `--callback-url` a podpis |
| [6 — Agent s nástroji](06-agent-s-nastroji.md) | 30 min | ~0,014 USD | krok `task`, tahy a `max_turns`, `mcp.yaml` (vlastník) × agent (autor), skilly a `load_skill`, záznam `tool_call` |
| [7 — Skládání a provoz](07-skladani-a-provoz.md) | 35 min | 0 USD (+ volitelně ~0,001) | `call` a stavebnice, `maw serve`, 401/422/202, `request_key`, callback, `report.html`, `dedupe_key`, co potřebuje n8n |

Díly 1–5 vznikly s `maw` 0.1.0 (výstupy v nich tomu odpovídají), díly 6
a 7 s `maw` 0.2.1. Časy jsou odhad pro první průchod; útrata je za
ostré běhy v dílu (ceny OpenRouteru z 25. 9. 2026).

Další soubory:

- [`callback-prijemac.py`](callback-prijemac.py) — místní přijímač
  callbacku s ověřením podpisu (díl 7).
- [`BUGS.md`](BUGS.md) — chyby frameworku nalezené při psaní tutoriálů.
