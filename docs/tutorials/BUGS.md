# Chyby frameworku nalezené při psaní tutoriálů (maw 0.1.0)

Neopraveno (do `framework/src` tutoriály nesahají). Příkazy se spouští
z kořene repozitáře, `maw` = `uv run --project framework maw`. Fixtury
z `/tmp` jsou v textu u každé položky.

## 1. Falešné varování „nevrátil cenu" po HTTP chybě (střední)

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

```bash
maw validate workflows/scenarios/tutorial-01-nazvy.yaml
```

```
v pořádku: tutorial-01-nazvy (2 kroků)
```

Česky „2 kroky", „4 kroky", ale „9 kroků", „1 krok". `framework/src/maw/cli.py`, `cmd_validate`.

## 6. Zlaté testy nečtou `workflows/config.yaml` (střední, ověřeno čtením kódu)

`framework/tests/conftest.py` má pevný testovací `CONFIG` s aliasy
`chytry`, `rychly`, `gemini-image` a fixtura `wf` ho zapíše místo
skutečného `config.yaml`. Když vlastník přidá do `workflows/config.yaml`
nový alias (např. `levny`) a agent ho použije, `maw validate` projde, ale
`test_workflow_agent_valid` i `test_workflow_scenario_runs_with_fake`
selžou na „model 'levny' není alias v config.yaml".

Nespuštěno — vyžadovalo by změnu `config.yaml`, kterou smí dělat jen
vlastník. Reprodukce pro vlastníka: přidat alias do `config.yaml`,
agenta s ním do `workflows/agents/`, `cd framework && uv run pytest -k
<agent>`. Návrh: testovací config odvodit z `workflows/config.yaml`
(aliasy převzít, `base_url`/limity přepsat na testovací).
