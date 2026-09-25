# framework — jádro `maw` (multiagent-workflows)

Verze 0.1.0, Python 3.12 + uv. Formáty podle `docs/spec/` (v1), návrh
v `docs/DESIGN.md`. Jméno příkazu `maw` je jen v `pyproject.toml`
(`[project.scripts]`) — přejmenování = jeden řádek.

## Použití (z kořene repozitáře)

```
uv run --project framework maw validate workflows/scenarios/ig-post.yaml
uv run --project framework maw run workflows/scenarios/ig-post.yaml -i tema="nová káva" --dry-run
uv run --project framework maw run workflows/scenarios/ig-post.yaml -i tema="nová káva" --fake framework/tests/golden/ig-post.yaml
uv run --project framework maw run workflows/scenarios/ig-post.yaml -i tema="nová káva"
uv run --project framework maw runs list
uv run --project framework maw runs show <run_id>
```

- Konfigurace `workflows/config.yaml` (vzor `config.example.yaml`). Klíče
  jen z prostředí nebo z `.env` v kořeni repozitáře.
- `--fake` = falešný poskytovatel bez sítě; volitelný YAML se
  skriptovanými odpověďmi podle kroků (popis v `src/maw/fake.py`).
- `--callback-url https://…` pošle po běhu výsledek podepsaný HMAC
  (`callback.secret_env`).
- Záznamy běhů jsou v `runs/` (v `.gitignore`), soubory z `output`
  v `outputs/` (`storage.type: local`).
- Návratový kód: 0 úspěch, 1 běh skončil chybou, 2 chyba `config`
  (validate, vstupy, prostředí).

## Testy

```
cd framework && uv run pytest
```

Konformační sada (DESIGN §5.6, §5.9): výrazy (58 případů ze spiku (c)
upravených podle spec + pravidla spec), loader, validate, engine (třídy
chyb, retry, kaskáda, parallel, switch, rozpočet, timeout, callback,
maskování) a zlaté scénáře — každý soubor ve `workflows/` a každá ukázka
v `docs/spec/`. Nový scénář ve `workflows/scenarios/` se testuje sám;
skriptované odpovědi pro něj patří do `tests/golden/<jméno>.yaml`.

## Struktura (vrstvy DESIGN D3)

| Soubor | Vrstva |
|---|---|
| `loader.py` | čtení souborů: YAML 1.2 core, frontmatter, `.env`, JSON Schema ze spec |
| `validate.py` | statické kontroly (scenario.md §7), vstupy |
| `expressions.py` | výrazy a šablony (scenario.md §5) |
| `engine.py` | běh: kroky, retry, timeout, rozpočet, callback |
| `providers.py` | OpenRouter chat / Jev / obrázek, třídy chyb, kaskáda |
| `fake.py` | falešný poskytovatel (`httpx.MockTransport`) |
| `record.py` | záznam běhu, summary.md, plan.md |
| `cli.py` | příkaz `maw` |

Zatím ne (Fáze 3, `validate` je odmítne chybou `config`): `task`
(MCP, `load_skill`, `dedupe_key`), `call`, webhook server, Modal,
`report.html`, úložiště R2. Nejasnosti spec: `docs/spec/ISSUES.md`.

## Ostrý běh (Fáze 2, 2026-09-25)

`maw run workflows/scenarios/ig-post.yaml` proti OpenRouteru, aliasy
`chytry` = `anthropic/claude-haiku-4.5`, `rychly` =
`google/gemini-3.5-flash-lite` (`tool_wrapper`), `gemini-image` =
`google/gemini-3.1-flash-image`. `maw validate` proti `GET /models` prošel.

| Běh | Téma | Výsledek | Čas | Cena |
|---|---|---|---|---|
| `runs/20260925-145904-ig-post-81e5` | ranní káva s přáteli | `fail` v kroku `stop`: on_brand = 0,68 | 6,2 s | 0,0013 USD |
| `runs/20260925-145923-ig-post-d686` | nové tričko THTD z bio bavlny | `fail` v kroku `stop`: on_brand = 0,63 | 2,8 s | 0,0013 USD |

Útrata Fáze 2 celkem **0,0026 USD**. Oba běhy doběhly přesně podle
scénáře: `copy` (Claude Haiku přes Amazon Bedrock, `native_schema`,
2,6–5,8 s, 0,0012 USD) → `kontrola` (Jev `typesafe/jev-1.13-20260917`,
0,27–0,41 s, 0,000016 USD) → záměrný `fail` pod prahem 0,7. Záznam
(summary, events, request/response bez klíče) je kompletní.

**Práh 0,7 je pro text od Haiku přísný; scénář se choval správně.** Jev
text copywritera (Claude Haiku 4.5) dvakrát ohodnotil pod prahem (0,68
a 0,63), takže běh skončil záměrným `fail` dřív, než došel k fotce. Obsah
textu a práh jsou ve vrstvě uživatele (agent `copywriter`,
`ig-post.yaml`), ne ve frameworku. Třetí běh `ig-post` jsem podle zadání
(nejvýš 2 pokusy) nespouštěl.

Zbylé kroky ověřil se souhlasem koordinátora **jeden** ostrý běh
dočasného scénáře `live-image` (mimo `workflows/`, nekomitovaný):
`ask` s agentem `photographer` + `image` s `aspect_ratio: "4:5"`.

| Běh | Krok | Výsledek | Čas | Cena |
|---|---|---|---|---|
| `runs/20260925-150206-live-image-7210` (úspěch, celkem 11,0 s, 0,0676 USD) | `foto_prompt` | `google/gemini-3.5-flash-lite` přes `tool_wrapper`: `finish_reason: tool_calls` (nativně `STOP`), `_submit_output` napoprvé platný | 1,5 s | 0,0003 USD |
| | `foto` | `google/gemini-3.1-flash-image`, `image_config.aspect_ratio: "4:5"` → PNG **928×1152** (1,83 MB), poměr 0,806 proti 0,8 = odchylka 0,7 % → **4:5 platí** (kontrola spec D10, tolerance 2 %) | 9,5 s | 0,0672 USD |

Záznam: base64 ani `reasoning_details` v `calls/*.json` nejsou (jen
`<soubor: steps/02-foto/image.png, 1834634 B>`), obrázek je ve složce
kroku a zkopírovaný do `outputs/<run_id>-<32 hex>/image.png`.

**Útrata Fáze 2 celkem 0,0702 USD** (2× `ig-post` 0,0026 + `live-image`
0,0676; `GET /models` zdarma).
