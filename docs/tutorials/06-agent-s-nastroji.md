# Díl 6 — Agent s nástroji: `task`, MCP server a skilly

**Čas:** asi 30 minut · **Útrata:** jeden ostrý běh za ~0,014 USD
(ostatní s `--fake` nebo bez volání modelu)
**Co budeš umět:** povolit agentovi MCP server (jako vlastník), napsat
agenta s nástroji a skillem (jako autor), spustit krok `task`, přečíst
v záznamu každé volání nástroje a vědět, kde všude tě framework zastaví.

Předpoklad: díly 1–5 a **Node.js** (`npx` spouští MCP server; poprvé si
stáhne balíček, takže potřebuje internet).

> Výstupy jsou skutečné — z běhů 25. 9. 2026 proti `maw` 0.2.1. Příkazy
> spouštěj z kořene repozitáře se zkratkou `agencast` z dílu 1.

---

## Krok 1 — `ask` × `task`

Doteď tvoji agenti jen **odpovídali**: krok `ask` = jedno volání modelu,
text dovnitř, text (nebo JSON) ven. Krok `task` dá agentovi **nástroje**
a nechá ho pracovat ve smyčce:

```
model: „zavolej list_allowed_directories"  → framework nástroj spustí, výsledek vrátí modelu
model: „zavolej write_file(...)"           → spustí, vrátí
model: „hotovo, tady je odpověď"           → konec kroku
```

Každá odpověď modelu, kterou smyčka zpracuje, je jeden **tah**. Tah může
obsahovat i několik volání nástrojů naráz. Opakování po chybě
(`transient`, `schema`) se jako tah nepočítá.

| | `ask` | `task` |
|---|---|---|
| Volání modelu | jedno (+ opakování po chybě) | smyčka, nejvýš `max_turns` tahů |
| Nástroje | žádné | povolené nástroje MCP serverů + `load_skill` |
| Skilly | vložené do promptu **celé** | v promptu jen seznam, tělo si model načte nástrojem |
| Limity | `budget_usd`, `timeout` | `max_turns`, `budget_usd`, `timeout` |
| Konec | odpověď modelu | model odpoví bez volání nástroje |

Nástroje nabízí **MCP server** — samostatný program, se kterým framework
mluví protokolem MCP. My použijeme oficiální
`@modelcontextprotocol/server-filesystem`: umí číst a psát soubory, ale
jen v jedné složce, kterou dostane při startu.

---

## Krok 2 — skill

Skill je znalost, kterou si agent vezme, když ji potřebuje. Tady: jak má
vypadat soubor v archivu.

Vytvoř `workflows/skills/tutorial-zapis/SKILL.md`:

```markdown
---
name: tutorial-zapis
description: Formát zápisu v archivu — použij vždy, když zápis nebo obsah archivu zapisuješ či kontroluješ
---
Archiv má dva soubory, oba přímo v povolené složce:

1. `<den>.md` — zápis jednoho dne (`<den>` je datum ze zadání, např. `2026-09-25.md`):
   - první řádek `# Zápis <den>`,
   - každá věta poznámky na vlastním řádku, který začíná `- `,
   - nic dalšího (žádné prázdné řádky, žádný komentář).
2. `obsah.md` — obsah archivu:
   - první řádek `# Obsah`,
   - pro každý zápis řádek `- <den>: <první věta poznámky>`.
```

- `name` = jméno složky.
- `description` je u `task` **jediné, co model o skillu vidí**, dokud si
  ho nenačte. Proto musí říct, *kdy* skill použít — ne jen „formát
  archivu".

---

## Krok 3 — agent s nástroji (role autora)

`workflows/agents/tutorial-archivar.md`:

```markdown
---
version: 1
name: tutorial-archivar
description: Zapisuje poznámky do archivu v pracovní složce běhu (tutoriál, díl 6)
model: chytry
skills: [tutorial-zapis]
mcp: [filesystem]
tools:
  filesystem: [list_allowed_directories, list_directory, read_text_file, write_file]
limits:
  max_turns: 6
  budget_usd: 0.03
  timeout: 3m
---
Jsi archivář. Máš přístup k jediné složce — zjistíš ji nástrojem
`list_allowed_directories`. Cesty k souborům piš vždy celé (povolená
složka + jméno souboru).

Postup:
1. Zjisti povolenou složku a načti skill `tutorial-zapis`.
2. Zapiš oba soubory podle skillu nástrojem `write_file`.
3. Vypiš složku a každý soubor přečti. Když nesedí se skillem, oprav ho.
4. Teprve pak odpověz: jména zapsaných souborů (bez složky) a počet vět
   v zápisu dne. Nikdy neodpovídej dřív, než soubory opravdu zapíšeš.

Když nástroj vrátí chybu, nezkoušej cesty mimo povolenou složku:
odpověz popisem chyby.
```

Nová pole:

| Pole | Co dělá |
|---|---|
| `skills` | skilly ze `workflows/skills/` |
| `mcp` | ke kterým serverům z `mcp.yaml` se agent smí připojit |
| `tools` | **výslovný seznam** nástrojů pro každý server z `mcp` — co tu není, model neuvidí. Když server v nové verzi přidá nástroj (třeba `delete_file`), agent ho nedostane. |
| `limits.max_turns` | nejvýš tolik tahů v jednom kroku `task`; u agenta s `mcp` povinné |
| `limits.budget_usd` | kolik smí stát **celý krok** — všechny tahy dohromady |

Proč `list_allowed_directories` a „cesty celé": agent předem neví, kde
leží jeho složka (každý běh má jinou). Zeptá se serveru.

---

## Krok 4 — scénář s krokem `task`

`workflows/scenarios/tutorial-06-archiv.yaml`:

```yaml
version: 1
name: tutorial-06-archiv
description: Archivář zapíše poznámku do pracovní složky běhu a přečte ji (tutoriál, díl 6)

inputs:
  den:
    type: string
    required: true
    description: Datum zápisu, např. 2026-09-25
  text:
    type: string
    required: true
    description: Poznámka volným textem

outputs:
  zprava:
    type: string
    description: Co archivář zapsal a zkontroloval (jeho závěrečná odpověď)

steps:
  # 1. Agent s nástroji: sám zjistí složku, načte skill, zapíše dva soubory,
  #    vypíše složku a soubory přečte. Nástroje povoluje mcp.yaml (vlastník)
  #    a agent; krok smí jen zúžit — tady snižuje jen max_turns.
  #    Bez schema: s ním Haiku v maw 0.2.1 často odpoví hned, bez nástrojů
  #    (díl 6, „Pozor na schema u task"; BUGS.md, maw 0.2.1).
  - id: zapis
    task:
      agent: tutorial-archivar
      prompt: |
        Den: {{ inputs.den }}
        Poznámka: {{ inputs.text }}
        Zapiš poznámku do archivu a zkontroluj ji.
      max_turns: 5

  # 2. Výsledek.
  - id: out
    output:
      zprava: "{{ steps.zapis.text }}"
```

`task` má stejná pole jako `ask` (`agent`, `prompt`, volitelně `schema`)
a navíc smí zúžit `max_turns`, `mcp` a `tools`. Bez `schema` je výstup
kroku `steps.zapis.text` — závěrečná odpověď agenta. Proč tu `schema`
schválně není, uvidíš v kroku 7.

Zkontroluj ho:

```bash
agencast validate tutorial-06-archiv
```

```
config: agents/tutorial-archivar.md: server 'filesystem' agentovi 'tutorial-archivar' vlastník nepovolil (mcp.yaml → servers.filesystem.agents: knihovnik)
```

Agent říká „chci filesystem", ale to nestačí.

---

## Krok 5 — `mcp.yaml` (role vlastníka)

Co smí který agent, rozhoduje **vlastník** v `workflows/mcp.yaml`:

```yaml
servers:
  filesystem:
    description: Čtení a zápis v pracovní složce aktuálního běhu
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem@2026.8.31", "{run_dir}/work"]
    agents: [knihovnik]
    tools: [list_allowed_directories, list_directory, read_text_file, write_file]
```

| Pole | Co to znamená |
|---|---|
| `command`, `args` | jak server spustit. `{run_dir}` = složka aktuálního běhu — server tedy vidí jen `runs/<běh>/work`, žádný jiný běh ani zbytek disku. Verze balíčku je pevná. |
| `agents` | kteří agenti smí server použít |
| `tools` | horní hranice nástrojů — agent si z nich smí vybrat, víc ne |
| `scenarios` (tady není) | ze kterých scénářů smí agent s tímto serverem běžet — např. publikace jen ze schvalovacího scénáře |

Přepni se do role vlastníka a přidej agenta do `agents` (jediná změna
v souboru):

```yaml
    agents: [knihovnik, tutorial-archivar]
```

```bash
agencast validate tutorial-06-archiv
```

```
v pořádku: tutorial-06-archiv (2 kroky)
```

**Proč to nejde z agenta:** agenty a scénáře píšou i ostatní — kolega,
nebo jiný agent. Kdyby si agent mohl oprávnění napsat sám do svého
frontmatteru, nebylo by to oprávnění, ale přání. Proto platí tři vrstvy,
každá smí jen **zúžit** tu předchozí:

```
vlastník (mcp.yaml)  →  agent (mcp, tools, limits)  →  krok task (tools, max_turns, …)
```

Krok nikdy nepřidá server ani nástroj a nezvýší limit (to si vyzkoušíš
v kroku 9).

### `--dry-run` ukáže, co server nabízí

```bash
agencast run tutorial-06-archiv -i den=2026-09-25 -i text="Ráno pršelo. Odpoledne jsme dopsali díl 6." --dry-run
```

```
| 1 | zapis | task |  | agent tutorial-archivar → chytry (anthropic/claude-haiku-4.5); nástroje: filesystem: list_allowed_directories, list_directory, read_text_file, write_file; skilly: tutorial-zapis; max_turns 5; text | 0.03 USD, 3m |
| 2 | out | output |  | zprava |  |

## MCP servery

- **filesystem** (Čtení a zápis v pracovní složce aktuálního běhu): nabízí create_directory, directory_tree, edit_file, get_file_info, list_allowed_directories, list_directory, list_directory_with_sizes, move_file, read_file, read_media_file, read_multiple_files, read_text_file, search_files, write_file
```

`--dry-run` server opravdu spustí a zeptá se ho na nástroje — takhle
zjistíš jména pro `tools`, aniž bys četl dokumentaci serveru. Server jich
nabízí 14, vlastník povolil 4, agent chce ty 4. Model uvidí jen je (a
`load_skill`). Limity kroku: `max_turns 5` (agent dovoluje 6), `0.03 USD`
a `3m` z agenta.

---

## Krok 6 — `--fake`: tahy ve fixtuře

U `task` je odpověď modelu **seznam tahů**. Tah je buď volání nástrojů
(`tool_calls`), nebo závěrečná odpověď (`text`, se `schema` `json`).
`framework/tests/golden/tutorial-06-archiv.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-06-archiv. Krok task = seznam tahů:
# každý tah je buď volání nástrojů (tool_calls), nebo finální odpověď (text).
# Jméno nástroje = <server>__<nástroj>; load_skill je nástroj frameworku.
# V testech běží místo server-filesystem falešný server (tests/fake_mcp_server.py),
# cesty jsou relativně k jeho kořeni.
zapis:
  - tool_calls:
      - { name: filesystem__list_allowed_directories, arguments: {} }
      - { name: load_skill, arguments: { name: tutorial-zapis } }
  - tool_calls:
      - name: filesystem__write_file
        arguments: { path: 2026-09-25.md, content: "# Zápis 2026-09-25\n- Ráno pršelo.\n- Odpoledne jsme dopsali díl 6.\n" }
      - name: filesystem__write_file
        arguments: { path: obsah.md, content: "# Obsah\n- 2026-09-25: Ráno pršelo.\n" }
  - tool_calls:
      - { name: filesystem__list_directory, arguments: { path: . } }
      - { name: filesystem__read_text_file, arguments: { path: 2026-09-25.md } }
      - { name: filesystem__read_text_file, arguments: { path: obsah.md } }
  - text: "Zapsáno: 2026-09-25.md a obsah.md. Zápis má 2 věty."
```

Jméno nástroje pro model je `<server>__<nástroj>` (dvě podtržítka) — tak
ho framework pojmenuje, aby se nástroje dvou serverů nepletly.

```bash
agencast run tutorial-06-archiv -i den=2026-09-25 -i text="Ráno pršelo. Odpoledne jsme dopsali díl 6." --fake framework/tests/golden/tutorial-06-archiv.yaml
```

```
běh 20260925-161448-tutorial-06-archiv-3ba8: úspěch · 0,8 s · 0,0004 USD
```

```
| 1 | zapis | task | ✓ | 0,8 s | 0,0004 | chytry → anthropic/claude-haiku-4.5, tahů 4, nástrojů 7 |
…
## Výstup
- zprava: „Zapsáno: 2026-09-25.md a obsah.md. Zápis má 2 věty."
```

Pozor na jednu věc: `--fake` falešně odpovídá **jen za model**. MCP
server je skutečný — `npx` ho spustil a soubory opravdu vznikly:

```bash
ls runs/20260925-161448-tutorial-06-archiv-3ba8/work
```

```
2026-09-25.md  obsah.md
```

Ve zlatých testech (`cd framework && uv run pytest`) místo něj běží
falešný server z `framework/tests/fake_mcp_server.py` — bez Node a bez
sítě, se stejnými nástroji. Fixtura je stejná.

---

## Krok 7 — ostrý běh

```bash
agencast run tutorial-06-archiv -i den=2026-09-25 -i text="Ráno pršelo a vlak měl zpoždění. Odpoledne jsme dopsali šestý díl tutoriálu. Večer jsme ho pustili naostro."
```

```
běh 20260925-161501-tutorial-06-archiv-dfec: úspěch · 9,9 s · 0,0135 USD
```

```
| 1 | zapis | task | ✓ | 9,9 s | 0,0135 | chytry → anthropic/claude-haiku-4.5, tahů 4, nástrojů 7 |
| 2 | out | output | ✓ | 0,0 s | 0 |  |
| | Celkem | | | 9,9 s | 0,0135 |  |
…
## Výstup
- zprava: „Dokonalé! Oba soubory odpovídají skillu:

✅ **2026-09-25.md** — správně: záhlaví `# Zápis 2026-09-25`, tři věty na vlastních řádcích s `-`
✅ **obsah.md** — správně: záhlaví `# Obsah`, jedna řádka s datem a první větou

**Odpověď:**
- **Zapsané soubory:** `2026-09-25.md`, `obsah.md`
- **Počet vět v zápisu dne:** 3"
```

A v pracovní složce:

```
--- work/2026-09-25.md
# Zápis 2026-09-25
- Ráno pršelo a vlak měl zpoždění.
- Odpoledne jsme dopsali šestý díl tutoriálu.
- Večer jsme ho pustili naostro.
--- work/obsah.md
# Obsah
- 2026-09-25: Ráno pršelo a vlak měl zpoždění.
```

Přesně podle skillu. Tahy po řadě (z `events.jsonl`):

```
mcp_server started (0,75 s — spuštění serveru a handshake)
tah 1: list_allowed_directories, load_skill tutorial-zapis    1,8 s   0,0020 USD
tah 2: write_file 2026-09-25.md, write_file obsah.md          2,3 s   0,0037 USD
tah 3: list_directory, read_text_file ×2                      2,1 s   0,0040 USD
tah 4: závěrečná odpověď (finish_reason stop)                 2,8 s   0,0038 USD
mcp_server stopped
```

Nástroje samy trvaly 2–9 ms, čas je v modelu. Tahy jsou čím dál dražší: model
v každém tahu dostává **celou dosavadní konverzaci** včetně výsledků
nástrojů (1 522 → 2 982 vstupních tokenů). Proto `max_turns` a
`budget_usd` — agent, který se zacyklí, by jinak platil čím dál víc.

### Pozor na `schema` u `task`

První verze scénáře měla u kroku `schema` (`soubory: [string]`,
`radku: integer`), jako u `ask` v dílu 2. Tři ostré běhy za sebou
dopadly takhle:

```
| 1 | zapis | task | ✓ | 24,0 s | 0,0046 | chytry → anthropic/claude-haiku-4.5, tahů 2, nástrojů 2 (native_schema) |
…
- soubory:  /home/…/runs/20260925-161001-tutorial-06-archiv-9a8f/work/2026-09-25.md
- radku: 4
```

„Úspěch" — ale složka `work/` **neexistuje**. Model zjistil složku,
načetl skill a ve druhém tahu rovnou odpověděl JSONem, jako by soubor
zapsal. Druhý a třetí pokus (s přísnějšími instrukcemi) dopadly stejně,
třetí dokonce bez jediného nástroje (`tahů 1, nástrojů 0`). Stejný
scénář **bez `schema`** prošel napoprvé.

Co se děje: se `schema` a aliasem na úrovni `native_schema` posílá
framework modelu v **každém** tahu i požadovaný tvar JSON odpovědi —
a Haiku ho bere jako pokyn „odpověz JSONem hned". Framework se přitom
zachoval podle specifikace: model odpověděl bez volání nástroje, tím
smyčka končí. Zapsané je to v `docs/tutorials/BUGS.md` (sekce maw 0.2.1)
i s tím, co pomohlo (alias s `structured_output: tool_wrapper` — to je
rozhodnutí vlastníka v `config.yaml`).

**Od `maw` 0.2.2** framework u `task` požadovaný tvar JSON v tazích
neposílá: se `schema` začíná vždy na úrovni `tool_wrapper` — model
odevzdá výsledek nástrojem `_submit_output`, až bude hotový
(`docs/spec/ISSUES.md`, bod 36). `structured_output` aliasu platí už jen
pro `ask`. Právě tahle varianta v kontrolním běhu (BUGS.md, bod 7)
zapsala oba soubory správně. V poznámce kroku pak uvidíš
`(tool_wrapper)`, případně `(prompt)`, když model výsledek nástrojem
neodevzdal a kaskáda šla o úroveň níž.

Z toho plynou dvě pravidla, která platí i po opravě:

1. **Agentovi s nástroji nevěř, ověř záznam.** Poznáš to v `summary.md`
   (`nástrojů 2`, přitom zápis potřebuje aspoň dva `write_file`) a
   v `events.jsonl` (žádný `tool_call` s `write_file`).
2. U `task` v `maw` 0.2.1 s Haiku dávej přednost textové odpovědi; když
   potřebuješ data, vytáhni je dalším krokem (`ask` se `schema` nad
   `steps.zapis.text`) — tam JSON nic neruší.

---

## Krok 8 — záznam kroku `task`

```
runs/20260925-161501-tutorial-06-archiv-dfec/
  mcp/filesystem.stderr.log     co server vypsal na stderr
  work/                         pracovní složka = to, co server vidí
  steps/01-zapis/
    prompt.md                   system prompt se seznamem skillů
    calls/01.request.json       tah 1 — požadavek na model
    calls/01.response.json      tah 1 — odpověď (volání nástrojů)
    calls/02.tool.json          nástroj list_allowed_directories
    calls/03.tool.json          nástroj load_skill
    calls/04.request.json       tah 2 …
    …
```

Čísla v `calls/` jdou po řadě přes volání modelu i nástrojů.

### `prompt.md` — skilly jako seznam

```
# System prompt

Jsi archivář. Máš přístup k jediné složce — zjistíš ji nástrojem
…
## Skilly

- tutorial-zapis: Formát zápisu v archivu — použij vždy, když zápis nebo obsah archivu zapisuješ či kontroluješ

# Zpráva

Den: 2026-09-25
…
```

Tělo skillu v promptu **není** — jen jméno a `description`. Model k němu
dostal nástroj `load_skill` (z `calls/01.request.json`):

```
{"type": "function", "function": {"name": "load_skill", "description": "Načte celé instrukce skillu ze seznamu Skilly. Když je skill pro úkol relevantní, načti ho dřív, než začneš.", "parameters": {"type": "object", "properties": {"name": {"type": "string", "enum": ["tutorial-zapis"]}}, "required": ["name"], "additionalProperties": false}}}
```

### `tool_call` v `events.jsonl`

Každé volání nástroje je jedna událost. `load_skill` má `server: "_skills"`
— nikdy nejde na MCP server, obslouží ho framework:

```
{"ts":"2026-09-25T16:15:03.685Z","type":"tool_call","step":"zapis","turn":1,"server":"_skills","tool":"load_skill","allowed":true,"invalid_args":false,"is_error":false,"duration_s":0.0,"call_file":"steps/01-zapis/calls/03.tool.json"}
{"ts":"2026-09-25T16:15:06.009Z","type":"tool_call","step":"zapis","turn":2,"server":"filesystem","tool":"write_file","allowed":true,"invalid_args":false,"is_error":false,"duration_s":0.008,"call_file":"steps/01-zapis/calls/05.tool.json"}
```

| Pole | Co říká |
|---|---|
| `turn` | ve kterém tahu model nástroj zavolal |
| `allowed` | `false` = nástroj nebyl povolen, nespustil se |
| `invalid_args` | `true` = argumenty nesedí na schéma nástroje, nespustil se |
| `is_error` | nástroj proběhl, ale vrátil chybu (model ji dostal) |

Argumenty a výsledek jsou v `call_file` (`calls/05.tool.json`):

```
{
  "turn": 2,
  "name": "filesystem__write_file",
  "server": "filesystem",
  "tool": "write_file",
  "arguments": {
    "path": "/home/…/runs/20260925-161501-tutorial-06-archiv-dfec/work/2026-09-25.md",
    "content": "# Zápis 2026-09-25\n- Ráno pršelo a vlak měl zpoždění.\n- Odpoledne jsme dopsali šestý díl tutoriálu.\n- Večer jsme ho pustili naostro.\n"
  },
  "allowed": true,
  "invalid_args": false,
  "is_error": false,
  "result": "Successfully wrote to /home/…/work/2026-09-25.md",
  "files": []
}
```

### `mcp_server` a `mcp/filesystem.stderr.log`

Server startuje **jednou za běh**, při prvním `task`, který ho
potřebuje, a končí s během:

```
{"ts":"2026-09-25T16:15:01.869Z","type":"mcp_server","server":"filesystem","action":"started","duration_s":0.753,"stderr_file":"mcp/filesystem.stderr.log"}
{"ts":"2026-09-25T16:15:11.007Z","type":"mcp_server","server":"filesystem","action":"stopped","stderr_file":"mcp/filesystem.stderr.log"}
```

Co server vypsal, je v `mcp/filesystem.stderr.log` — sem se dívej, když
server nenastartuje:

```
Secure MCP Filesystem Server running on stdio
Client does not support MCP Roots, using allowed directories set from server args: [
  '/home/…/runs/20260925-161501-tutorial-06-archiv-dfec/work'
]
```

Druhý řádek potvrzuje, že server vidí jen `work/` tohoto běhu.

---

## Krok 9 — kde tě framework zastaví

Na zkoušku pracuj v kopii, ať si nerozbiješ své soubory:

```bash
rm -rf /tmp/pokus && mkdir -p /tmp/pokus && cp -r workflows /tmp/pokus/
```

### Před během: `validate`

Krok chce nástroj, který agent nemá — v kopii scénáře přidej ke kroku
`zapis` řádek `tools: { filesystem: [write_file, move_file] }`:

```
config: tutorial-06-archiv.yaml: krok "zapis", task.tools: krok chce nástroj filesystem.move_file, agent 'tutorial-archivar' ho nepovoluje (tools.filesystem)
```

Agent chce nástroj, který nepovolil vlastník — v kopii agenta přidej do
`tools.filesystem` `edit_file`:

```
config: agents/tutorial-archivar.md: nástroje edit_file serveru 'filesystem' vlastník nepovolil (mcp.yaml → servers.filesystem.tools: list_allowed_directories, list_directory, read_text_file, write_file)
```

Krok chce víc tahů, než dovolí agent (`max_turns: 10`):

```
config: tutorial-06-archiv.yaml: krok "zapis", task.max_turns: 10 je víc než limits.max_turns agenta 'tutorial-archivar' (6) — krok limity jen snižuje
```

Agent s `mcp`, ale bez `tools`, resp. bez `limits.max_turns`:

```
config: agents/tutorial-archivar.md: s polem 'mcp' je povinné i 'tools'
config: agents/tutorial-archivar.md: limits: chybí povinné pole 'max_turns'
```

(Po každé zkoušce vrať soubor z `workflows/` zpátky do kopie.)

### Za běhu: fixtury v `/tmp`

Co když model zavolá nástroj, který nemá? Server `move_file` umí, ale
agent ho nepovolil. `/tmp/nepovoleny.yaml`:

```yaml
zapis:
  - tool_calls:
      - { name: filesystem__move_file, arguments: { source: a.md, destination: b.md } }
      - { name: filesystem__write_file, arguments: { path: a.md } }
  - text: "Nic jsem nezapsal."
```

```bash
agencast run /tmp/pokus/workflows/scenarios/tutorial-06-archiv.yaml -i den=2026-09-25 -i text="Ráno pršelo." --fake /tmp/nepovoleny.yaml
```

Běh doběhne (`úspěch`) a v `events.jsonl` jsou oba pokusy:

```
{"type":"tool_call","step":"zapis","turn":1,"server":"filesystem","tool":"move_file","allowed":false,"invalid_args":false,"is_error":false,…}
{"type":"tool_call","step":"zapis","turn":1,"server":"filesystem","tool":"write_file","allowed":true,"invalid_args":true,"is_error":false,…}
```

Model dostal místo výsledku chybu (z `calls/02.tool.json` a
`03.tool.json`):

```
Chyba: nástroj filesystem__move_file není povolen. Povolené: filesystem__list_allowed_directories, filesystem__list_directory, filesystem__read_text_file, filesystem__write_file, load_skill
Chyba: argumenty neprošly schématem nástroje: kořen: chybí povinné pole 'content'
```

Ani jeden nástroj se nespustil. Běh tím neselže — model se může opravit.

Agent, který se točí dokola. `/tmp/dokola.yaml` (poslední odpověď se
opakuje, takže model volá nástroje pořád):

```yaml
zapis:
  - tool_calls:
      - { name: filesystem__list_directory, arguments: { path: . } }
```

```
budget v kroku zapis: max_turns 5 vyčerpán bez finální odpovědi (model dál volá nástroje)
běh 20260925-162243-tutorial-06-archiv-9f91: chyba · 0,8 s · 0,0005 USD
```

Nástroje proběhly ve 4 tazích, pátá odpověď modelu chtěla další — konec,
třída `budget`.

Drahý agent. `/tmp/drahy.yaml` — každý tah stojí 0,02 USD (`cost` umí
jen falešný poskytovatel):

```yaml
zapis:
  - cost: 0.02
    tool_calls:
      - { name: filesystem__list_allowed_directories, arguments: {} }
```

```
budget v kroku zapis: rozpočet kroku 'zapis' vyčerpán (0.0400 z 0.03 USD)
```

a v `summary.md`:

```
## Varování
- rozpočet kroku 'zapis' překročen o 0.0100 USD (krok zapis)
```

Tah 1 stál 0,02 (pod limitem 0,03), tak se spustil tah 2. Ten limit
překročil — dokončí se a platí (varování), ale další už se nespustí.
`budget_usd` je tedy hranice, přes kterou se jde nejvýš o jeden tah.

---

## Krok 10 — tentýž agent v `ask`

Agent s nástroji jde použít i v `ask` — pak nemá nástroje a MCP server
se vůbec nespustí. Skill ale model potřebuje, a `load_skill` volat
nemůže. Proto ho framework vloží **celý**. `/tmp/pokus/workflows/scenarios/tutorial-06-ask.yaml`:

```yaml
version: 1
name: tutorial-06-ask
description: Stejný agent v kroku ask (bez nástrojů)
steps:
  - id: rada
    ask:
      agent: tutorial-archivar
      prompt: "Jak bude vypadat zápis dne 2026-09-25 s poznámkou: Ráno pršelo."
```

```bash
agencast run /tmp/pokus/workflows/scenarios/tutorial-06-ask.yaml --fake
```

`steps/01-rada/prompt.md`:

```
# System prompt

Jsi archivář. Máš přístup k jediné složce — zjistíš ji nástrojem
…
## Skill: tutorial-zapis

Archiv má dva soubory, oba přímo v povolené složce:

1. `<den>.md` — zápis jednoho dne (`<den>` je datum ze zadání, např. `2026-09-25.md`):
…
```

Místo řádku `- tutorial-zapis: …` pod `## Skilly` je tu celé tělo pod
`## Skill: tutorial-zapis`. V `events.jsonl` není žádný `mcp_server`.
(Instrukce o nástrojích tu model dostane taky, jenže nástroje nemá —
agent psaný pro `task` do `ask` patří jen na zkoušku.)
Důsledek: u `ask` platíš za každý skill celý, pokaždé; u `task` jen za
ty, které si model opravdu načte.

---

## Co sis zapamatoval

- `ask` = jedna odpověď; `task` = smyčka tahů s nástroji, nejvýš
  `max_turns`, celé za `budget_usd`.
- Oprávnění: vlastník (`mcp.yaml`: `agents`, `tools`, `scenarios`) →
  agent (`mcp`, `tools`, `limits`) → krok (jen zúžení). Z agenta si
  oprávnění nenapíšeš.
- `--dry-run` spustí server a vypíše, co nabízí.
- Záznam: `tool_call` (`allowed`, `invalid_args`, `is_error`),
  `calls/NN.tool.json`, `mcp_server`, `mcp/<server>.stderr.log`, `work/`.
- Skill u `task` = řádek v promptu + `load_skill` (`server: "_skills"`);
  u `ask` celé tělo.
- Agentovi s nástroji nevěř na slovo — v záznamu je, co opravdu udělal.

---

## Cvičení

Rozděl práci na dva kroky `task` se stejným agentem: `zapis` smí jen
zjistit složku a psát (`list_allowed_directories`, `write_file`),
`kontrola` smí jen číst (`list_allowed_directories`, `list_directory`,
`read_text_file`) a ohlásí, jestli soubory sedí na skill. Scénář ulož
jako `workflows/scenarios/tutorial-06-cviceni.yaml`, napiš fixturu a
ověř, že kontrola opravdu nemá `write_file`.

<details>
<summary>Řešení</summary>

`workflows/scenarios/tutorial-06-cviceni.yaml`:

```yaml
version: 1
name: tutorial-06-cviceni
description: Archivář zapíše poznámku, druhý krok ji jen pro čtení zkontroluje (tutoriál, díl 6 — řešení cvičení)

inputs:
  den:
    type: string
    required: true
    description: Datum zápisu, např. 2026-09-25
  text:
    type: string
    required: true
    description: Poznámka volným textem

outputs:
  zapis:
    type: string
    description: Co hlásí krok zapis
  kontrola:
    type: string
    description: Co hlásí krok kontrola

steps:
  # 1. Zápis: krok zúží nástroje — číst ani vypisovat složku tu není potřeba.
  - id: zapis
    task:
      agent: tutorial-archivar
      prompt: |
        Den: {{ inputs.den }}
        Poznámka: {{ inputs.text }}
        Zapiš poznámku do archivu. Nic nečti ani nekontroluj, to udělá kolega.
      max_turns: 3
      tools:
        filesystem: [list_allowed_directories, write_file]

  # 2. Kontrola jen pro čtení: stejný agent, stejný server (běží jednou za běh),
  #    ale bez write_file — opravit nic nemůže, jen ohlásí.
  - id: kontrola
    task:
      agent: tutorial-archivar
      prompt: |
        Kolega hlásí: {{ steps.zapis.text }}
        Přečti zápis dne {{ inputs.den }} a obsah archivu. NIC nezapisuj ani neopravuj.
        Řekni, kolik vět zápis má a jestli oba soubory odpovídají skillu.
      max_turns: 4
      tools:
        filesystem: [list_allowed_directories, list_directory, read_text_file]

  - id: out
    output:
      zapis: "{{ steps.zapis.text }}"
      kontrola: "{{ steps.kontrola.text }}"
```

`framework/tests/golden/tutorial-06-cviceni.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-06-cviceni (řešení cvičení z dílu 6).
# Dva kroky task, každý má vlastní seznam tahů. Kontrola čte soubory, které
# zapsal krok zapis — MCP server (v testech falešný) běží jednou za běh.
zapis:
  - tool_calls:
      - { name: filesystem__list_allowed_directories, arguments: {} }
      - { name: load_skill, arguments: { name: tutorial-zapis } }
  - tool_calls:
      - name: filesystem__write_file
        arguments: { path: 2026-09-25.md, content: "# Zápis 2026-09-25\n- Ráno pršelo.\n- Odpoledne jsme dopsali díl 6.\n" }
      - name: filesystem__write_file
        arguments: { path: obsah.md, content: "# Obsah\n- 2026-09-25: Ráno pršelo.\n" }
  - text: "Zapsáno: 2026-09-25.md a obsah.md."
kontrola:
  - tool_calls:
      - { name: load_skill, arguments: { name: tutorial-zapis } }
      - { name: filesystem__read_text_file, arguments: { path: 2026-09-25.md } }
      - { name: filesystem__read_text_file, arguments: { path: obsah.md } }
  - text: "Zápis má 2 věty, oba soubory odpovídají skillu."
```

```bash
agencast run tutorial-06-cviceni -i den=2026-09-25 -i text="Ráno pršelo. Odpoledne jsme dopsali díl 6." --fake framework/tests/golden/tutorial-06-cviceni.yaml
```

```
| 1 | zapis | task | ✓ | 0,8 s | 0,0003 | chytry → anthropic/claude-haiku-4.5, tahů 3, nástrojů 4 |
| 2 | kontrola | task | ✓ | 0,0 s | 0,0002 | chytry → anthropic/claude-haiku-4.5, tahů 2, nástrojů 3 |
| 3 | out | output | ✓ | 0,0 s | 0 |  |
| | Celkem | | | 0,8 s | 0,0005 |  |
```

Kontrola trvala 0,0 s i se serverem: ten běží od prvního kroku
(`mcp_server started` je v `events.jsonl` jen jednou, s 0,757 s
na start). Nástroje, které model v kroku `kontrola` dostal
(`steps/02-kontrola/calls/01.request.json`):

```
['filesystem__list_allowed_directories', 'filesystem__list_directory', 'filesystem__read_text_file', 'load_skill']
```

`write_file` tam není — kdyby ho model přesto zavolal, dostal by
„nástroj není povolen" (krok 9).

```bash
cd framework && uv run pytest -k tutorial-06 -v; cd ..
```

```
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-06-archiv] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-06-cviceni] PASSED
```

</details>

---

## Co přijde dál

**[Díl 7 — Skládání a provoz](07-skladani-a-provoz.md):** scénář volá
scénář (`call`), `agencast serve` pro n8n (token, `request_key`, callback
s podpisem), `report.html` a `dedupe_key` pro kroky, které smí proběhnout
jen jednou.
