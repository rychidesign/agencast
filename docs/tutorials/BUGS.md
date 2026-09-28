# Chyby frameworku nalezené při psaní tutoriálů (maw 0.1.0)

Do 0.2.5 se balík a příkaz jmenovaly `maw`; starší záznamy tu to jméno nechávají.

Všech šest je opraveno v maw 0.2.1 (větev `fix-tutorial-bugs`, viz
`../../framework/CHANGELOG.md`); u každé položky je commit s opravou a testem.
Níže zůstává původní popis. Příkazy se spouští
z projektu `examples/tutorial`, `maw` = `uv run --project ../../framework maw`. Fixtury
z `/tmp` jsou v textu u každé položky.

## 1. Falešné varování „nevrátil cenu" po HTTP chybě (střední)

**Opraveno v 0.2.1 (commit 7dd0d00).** Varování jen u úspěšné odpovědi bez `usage.cost`; test `test_http_error_without_usage_no_cost_warning` (429 i 400).

Volání, které skončí HTTP chybou (429, 400), nemá `usage` — a nic nestojí.
Framework přesto zapíše varování, jako by chyběla cena u úspěšné
odpovědi. Naživo vrací OpenRouter u 429 také tělo bez `usage`, takže se
varování objeví i v ostrých bězích po každém přetížení.

Reprodukce — `/tmp/pretizeni.yaml`:

```yaml
navrh:
  - status: 429
    error: "Rate limit exceeded"
  - json:
      nazvy: ["Ovesňák", "Mrazík Oves", "Zmrzlá Pláň"]
```

```bash
maw run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="zmrzlina" --fake /tmp/pretizeni.yaml
```

Očekáváno: běh `úspěch`, varování žádná (opakování po `transient` je
normální). Skutečnost (`summary.md`):

```
## Varování
- krok navrh: poskytovatel nevrátil cenu (usage.cost) — rozpočet nejde hlídat přesně
```

Stejně po HTTP 400 (fixtura `navrh: [{status: 400, error: "Invalid request"}]`).
Spec (scenario.md §6 Rozpočet, run-record.md `usage`) mluví o chybějící
ceně u odpovědi, ne u chybového statusu.

## 2. Druhá hláška prozrazuje vnitřek Pythonu (drobné)

**Opraveno v 0.2.1 (commit d5bf1bb).** Jen první hláška, nově se stříškou; test `test_template_in_expression_one_error`.

`{{ }}` ve výrazu (`set`, `when`) dá dvě hlášky; druhá mluví o AST uzlu
Pythonu, kterému začátečník nerozumí:

```bash
# v tutorial-02-nazev-a-slogan.yaml v kroku souhrn: pocet: "{{ steps.navrh.nazvy }}"
maw validate workflows/scenarios/tutorial-02-nazev-a-slogan.yaml
```

```
config: tutorial-02-nazev-a-slogan.yaml: krok "souhrn", set.pocet: šablona {{ }} tu není povolená — smí být jen v prompt, jev.state, jev.questions (instructions, criteria), fail, hodnotách output, call.inputs a dedupe_key
config: tutorial-02-nazev-a-slogan.yaml: krok "souhrn", set.pocet: konstrukce 'Set' není ve výrazech povolená
  {{ steps.navrh.nazvy }}
  ^
```

Očekáváno: jen první hláška (se stříškou). `{` se v Pythonu čte jako
množina (`Set`), proto ta druhá.

## 3. Hláška u id modelu v agentovi neříká „alias" (drobné)

**Opraveno v 0.2.1 (commit b1dcbc1).** Hláška o aliasu místo regexu, schéma beze změny; test `test_agent_model_id_instead_of_alias`.

```bash
# v workflows/agents/tutorial-pojmenovavac.md: model: anthropic/claude-haiku-4.5
maw validate workflows/scenarios/tutorial-01-nazvy.yaml
```

```
config: agents/tutorial-pojmenovavac.md: model: hodnota neodpovídá tvaru ^[a-z][a-z0-9-]*$
```

Očekáváno (agent.md: „Konkrétní id modelu — jen alias"): hláška jako
u neznámého aliasu, např. `model 'anthropic/claude-haiku-4.5' není alias
v config.yaml (aliasy: chytry, rychly, gemini-image)`. Pro začátečníka
je regex nesrozumitelný a toto je nejčastější chyba nového agenta.

## 4. Chyba YAML anglicky a bez rady (drobné)

**Opraveno v 0.2.1 (commit 2447fd4).** Česká věta s radou a řádkem, hláška parseru na druhém řádku; test `test_yaml_syntax_error_czech_hint`.

```bash
# v tutorial-03-rozhodovani.yaml: when: {{ steps.kontrola.zapamatovatelny }} < 0.5
maw validate workflows/scenarios/tutorial-03-rozhodovani.yaml
```

```
config: tutorial-03-rozhodovani.yaml, řádek 56: expected <block end>, but found '<scalar>'
```

Číslo řádku je v pořádku; zbytek je surová hláška parseru. Stejně
`mapping values are not allowed here` u `description` s `: ` uvnitř.
Návrh: přidat českou radu („hodnota s `{`, `[`, `: ` nebo ` #` patří do
uvozovek", scenario.md §5 „Pozor na YAML").

## 5. Tvar „(2 kroků)" ve `validate` (kosmetické)

**Opraveno v 0.2.1 (commit 1c28c4d; výstupy v tutoriálech 31b1d5e).** 1 krok, 2–4 kroky, 5+ kroků — i `serve` („ve frontě 2 běhy") a poznámka kroku `call` v `summary.md`; test `test_step_count_czech_plural`.

```bash
maw validate workflows/scenarios/tutorial-01-nazvy.yaml
```

```
v pořádku: tutorial-01-nazvy (2 kroků)
```

Česky „2 kroky", „4 kroky", ale „9 kroků", „1 krok". `../../framework/src/maw/cli.py`, `cmd_validate`.

## 6. Zlaté testy nečtou `workflows/config.yaml` (střední, ověřeno čtením kódu)

**Opraveno v 0.2.1 (commit f04a099).** Testovací config přebírá aliasy ze skutečného `config.yaml`; test `test_owner_alias_reaches_golden_tests` (dočasný alias `levny` jen v testu).

`../../framework/tests/conftest.py` má pevný testovací `CONFIG` s aliasy
`chytry`, `rychly`, `gemini-image` a fixtura `wf` ho zapíše místo
skutečného `config.yaml`. Když vlastník přidá do `workflows/config.yaml`
nový alias (např. `levny`) a agent ho použije, `maw validate` projde, ale
`test_workflow_agent_valid` i `test_workflow_scenario_runs_with_fake`
selžou na „model 'levny' není alias v config.yaml".

Nespuštěno — vyžadovalo by změnu `config.yaml`, kterou smí dělat jen
vlastník. Reprodukce pro vlastníka: přidat alias do `config.yaml`,
agenta s ním do `workflows/agents/`, `cd ../../framework && uv run pytest -k
<agent>`. Návrh: testovací config odvodit z `workflows/config.yaml`
(aliasy převzít, `base_url`/limity přepsat na testovací).

---

# maw 0.2.1 — nálezy z dílů 6 a 7

Zjištěno 2026-09-25 při psaní dílů 6 a 7 proti `maw` 0.2.1 (větev
`tutorials-6-7`). `../../framework/src` beze změny; číslování navazuje.
`maw` = `uv run --project ../../framework maw`, příkazy z projektu `examples/tutorial`.

Všechny tři body jsou opraveny v maw 0.2.2 (větev `fix-0.2.2`, viz
`../../framework/CHANGELOG.md`); u každé položky je commit s opravou a testem.

## 7. `task` se `schema` a `native_schema`: Haiku ukončí smyčku bez nástrojů (střední)

**Opraveno v 0.2.2 (commit 26e0d29).** Rozhodnutí koordinátora: v `task` se strukturovaný výstup vždy vynucuje `_submit_output` (úroveň `tool_wrapper`), `response_format` se neposílá; alias `structured_output` platí jen pro `ask`; výklad ISSUES 36. Test `test_schema_always_tool_wrapper_and_cascade_to_prompt`. Ostře neověřeno (žádné ostré běhy) — opírá se o kontrolní běh s `tool_wrapper` v tabulce níže.

Se `schema` u kroku `task` a aliasem na úrovni `native_schema` (`chytry`
= `anthropic/claude-haiku-4.5`) posílá framework `response_format`
(`json_schema`, `strict`) v **každém** tahu spolu s `tools`
(`task.py` → `task_body`). Haiku pak často místo volání nástrojů rovnou
odpoví JSONem podle schématu — s vymyšleným obsahem. Smyčka skončí
„úspěchem" (spec: odpověď bez volání nástroje = konec), vedlejší účinek
se nestane a nic to nehlásí.

Tři ostré běhy scénáře `tutorial-06-archiv` ve verzi se
`schema: {soubory: [string], radku: integer}` (agent `tutorial-archivar`):

| Běh | Instrukce | Výsledek | Cena |
|---|---|---|---|
| `runs/20260925-161001-tutorial-06-archiv-9a8f` | první verze agenta | tah 1 `load_skill` + `list_allowed_directories` (poskytovatel Anthropic), tah 2 JSON (`stop`, Amazon Bedrock); `work/` neexistuje, výstup `soubory: [" /…/work/2026-09-25.md"], radku: 4` | 0,0046 USD |
| `runs/20260925-161101-tutorial-06-archiv-fee2` | agent s číslovaným postupem „nikdy neodpovídej dřív, než zapíšeš" | tah 1 `list_allowed_directories`, tah 2 JSON `soubory: ["2026-09-25.txt"]`; nic nezapsáno | 0,0040 USD |
| `runs/20260925-161129-tutorial-06-archiv-67a6` | navíc postup v `prompt` kroku | tah 1 rovnou JSON (0 nástrojů, 1 818 výstupních tokenů na 58 znaků, 75,8 s) | 0,0108 USD |

Kontrola v kopii projektu (`/tmp/exp`, soubory vlastníka ve
`workflows/` nezměněny), stejný vstup:

| Varianta | Výsledek | Cena |
|---|---|---|
| stejný scénář **bez `schema`** | 5 tahů, 7 nástrojů, oba soubory správně | 0,0171 USD |
| se `schema`, alias `chytry` s `structured_output: tool_wrapper` | 5 tahů, 8 nástrojů, oba soubory správně; závěrečný tah vrátil text místo `_submit_output` → chyba `schema` → kaskáda na `prompt`, 2. pokus platný | 0,0215 USD |

`ukazka-task` (knihovník, stejný mechanismus) ve Fázi 3a prošel, takže
jde o pravděpodobnost, ne o jistotu — ale 3 ze 3 je dost na to, aby na
to začátečník narazil. Tutoriál proto u `task` `schema` nepoužívá
a vysvětluje proč (díl 6, „Pozor na schema u task").

Reprodukce (~0,005 USD): do kroku `zapis` v kopii
`tutorial-06-archiv.yaml` přidat `schema: {soubory: [string], radku:
integer}` a `output` na tato pole, `maw run … -i den=2026-09-25 -i
text="Ráno pršelo a vlak měl zpoždění. Odpoledne jsme dopsali šestý díl
tutoriálu. Večer jsme ho pustili naostro."`, v `summary.md` sledovat
`nástrojů N` a existenci `work/`.

Možnosti (rozhodnutí pro koordinátora/vlastníka, ne pro tutoriál):
u `task` začínat kaskádu na `tool_wrapper` (závěr přes `_submit_output`,
v tazích bez `response_format`); nebo `response_format` v `task`
neposílat a schéma vynutit až kontrolou závěrečné odpovědi; nebo jen
doporučení vlastníkovi (`structured_output: tool_wrapper` u aliasu pro
agenty s nástroji — mění ale i `ask`). Spec (scenario.md, kaskáda) tuto
kombinaci neřeší.

## 8. `--fake` zapisuje do stejného `runs/_dedupe/` jako ostré běhy (vysoká)

**Opraveno v 0.2.2 (commit cf5c31d).** Falešný běh má vlastní `<runs>/_dedupe-fake/`, režimy se nečtou křížem; `run_started.fake`, řádek „Falešný běh" v `summary.md` a `report.html`. Test `test_dedupe_fake_and_live_do_not_share_state` (falešný → ostrý → falešný nad stejným `runs/`). Staré falešné záznamy v `_dedupe/` z 0.2.1 oprava nesmaže.

Falešný běh kroku s `dedupe_key` vytvoří `_dedupe/<sha>.json` se
`state: succeeded` a **falešným** výstupem. Následující ostrý běh se
stejným klíčem krok přeskočí a vrátí falešný výstup jako skutečný —
`succeeded`, 0 volání modelu, v callbacku ani v `summary.md` není znát,
že výstup pochází z falešného běhu. U publikace (`ig-publish`) by to
znamenalo: po zkoušce s `--fake` se příspěvek naostro nikdy nezveřejní
a n8n dostane vymyšlený `post_url`.

```bash
maw serve --fake fake/tutorial-07-archiv.yaml     # nebo maw run … --fake
# POST /runs: {"scenario": "tutorial-07-archiv", "inputs": {"den": "2026-09-25", "text": "…"}, …}
maw run tutorial-07-archiv -i den=2026-09-25 -i text="Ostrý zápis."   # bez --fake
```

```
běh 20260925-161909-tutorial-07-archiv-1c51: úspěch · 0,0 s · 0,0000 USD
…
{"type":"step_skipped","step":"zapis","kind":"task","reason_code":"dedupe","reason":"dedupe_key 'archiv-2026-09-25': krok už proběhl v běhu 20260925-161842-tutorial-07-archiv-5637","default_used":false}
- zprava: „Zapsáno: 2026-09-25.md a obsah.md. Zápis má 2 věty."
```

(Běh `…-5637` byl falešný přes `maw serve --fake`; ověřeno v kopii
projektu `/tmp/t7`.) Očekáváno: falešný běh ostrý dedupe neovlivní
(vlastní `_dedupe`, nebo záznam s příznakem `fake` a ostrý běh ho
ignoruje). Spec (scenario.md §3 dedupe) falešný běh nezmiňuje.
Tutoriál na to upozorňuje (díl 7, krok 8).

## 9. Drobnosti (kosmetické)

**Opraveno v 0.2.2 (commit 0459c67).** Testy `test_agent_without_tools_list_and_without_max_turns` a `test_422_all_errors_at_once`.

- `validate` u agenta s `mcp` bez `tools` hlásí jen
  `config: agents/tutorial-archivar.md: s polem 'mcp' je povinné i 'tools'`.
  agent.md slibuje, že nabízené nástroje vypíše `validate --dry-run`;
  hláška by mohla jmenovat server a poradit `--dry-run`.
- `POST /runs` s neznámým polem **a** špatným typem vstupu vrátí 422 jen
  s první skupinou chyb (`neznámé pole 'priorita' …`); chyba vstupu
  (`vstup 'produkt' má být string, dostal number`) přijde až na druhý
  pokus. Spec to nevyžaduje, n8n by ale ušetřilo kolo.
