# Formát agenta — specifikace v1

Agent je jeden soubor `workflows/agents/<name>.md`: nahoře konfigurace
(YAML frontmatter mezi dvěma řádky `---`), pod ní instrukce v Markdownu
(DESIGN D1a). Scénář agenta volá jménem v kroku `ask` nebo `task`.

Strojová podoba: [`schema/agent.schema.json`](schema/agent.schema.json).
Ukázky: `workflows/agents/copywriter.md`, `photographer.md`, `publisher.md`.

Frontmatter se čte jako **YAML 1.2 core** (booleany jen `true`/`false`,
duplicitní klíč = chyba `config` s číslem řádku; viz
[scenario.md](scenario.md)). Čtou se jen soubory přímo ve
`workflows/agents/`; podsložky se ignorují (hodí se třeba na archiv).

Značení v textu: **návrh** = DESIGN.md to neřeší, jde o navržené výchozí
chování ke schválení.

## Celý příklad

```markdown
---
version: 1
name: publisher
description: Publikuje schválený příspěvek na Instagram
model: chytry
skills: [ig-pravidla]
mcp: [instagram]
tools:
  instagram: [create_media, publish_media]
limits:
  max_turns: 6
  budget_usd: 0.20
  timeout: 5m
---
Jsi správce Instagramu značky THTD. Dostaneš hotový text a URL obrázku…
```

## Pole frontmatteru

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `version` | ano | Verze formátu agenta. Framework podle ní pozná, jak soubor číst (R7). Zatím jen `1`. | `validate` skončí chybou `config`. | `version: 1` |
| `name` | ano | Jméno, kterým agenta volá scénář. Musí se shodovat s názvem souboru bez `.md`. Malá písmena, číslice, pomlčka. | Chyba `config`. Nesoulad se jménem souboru také. | `name: copywriter` |
| `description` | ano | Jedna věta pro člověka: k čemu agent je. Do promptu se **neposílá**. | Chyba `config`. | `description: Copywriter pro IG značky THTD` |
| `model` | ano | **Alias** modelu z `config.yaml` (§5.5), nikdy konkrétní id modelu. | Chyba `config`. Neznámý alias také. | `model: chytry` |
| `skills` | ne | Seznam skillů ze `workflows/skills/<name>/SKILL.md` ([skill.md](skill.md)). Jak se dostanou k modelu, viz níže. | Žádné skilly. | `skills: [ig-pravidla]` |
| `mcp` | ne | Seznam MCP serverů z `mcp.yaml`, ke kterým se agent smí připojit. Používá je jen krok `task`. Server musí mít tohoto agenta ve svém `agents` v `mcp.yaml` (určuje vlastník). | Agent nemá žádné nástroje. | `mcp: [instagram]` |
| `tools` | u každého serveru z `mcp` | **Výslovný seznam** nástrojů, které agent smí volat, pro **každý** server z `mcp` (DESIGN §5.8: allowlist podle jména — nový nástroj, který server přidá, agent neuvidí). Klíče `tools` = přesně servery z `mcp`. Nástroj musí být i v `tools` serveru v `mcp.yaml`, pokud ho vlastník omezil. | Server z `mcp` bez záznamu v `tools` je chyba `config`; `validate --dry-run` vypíše, co server nabízí. Klíč `tools` pro server mimo `mcp` je také chyba. | `tools: { instagram: [publish_media] }` |
| `limits` | ano | Horní hranice pro jedno použití agenta v kroku. Krok je smí jen snížit. | Chyba `config`. | viz níže |
| `limits.max_turns` | když má agent `mcp` | Kolik tahů smí proběhnout v jednom kroku `task` (§5.1 bod 6). Tah = odpověď modelu, kterou smyčka zpracovala; opakování po chybě se nepočítá. U `ask` nemá význam — `ask` je vždy jedno volání. | Agent s `mcp` bez `max_turns` = chyba `config`. Agent bez `mcp` použitý v `task` bez `max_turns` = chyba `config`. | `max_turns: 6` |
| `limits.budget_usd` | ano | Kolik USD smí stát jeden krok s tímto agentem (všechna volání včetně opakování). | Chyba `config`. | `budget_usd: 0.20` |
| `limits.timeout` | ne | Nejdelší doba jednoho kroku s tímto agentem. Formát `<číslo>s`, `m` nebo `h`. | Výchozí podle typu kroku (`ask` 2m, `task` 15m) — **návrh**. | `timeout: 5m` |

Jiná pole frontmatter nepovoluje — překlep (`modle:`) je chyba `config`,
ne tiše ignorované pole.

Seznam scénářů, které smí agenta použít, v agentovi **není**: agenty píší
i ostatní, proto tato omezení drží vlastník v `mcp.yaml` (`agents`,
`scenarios`, `tools` u serveru — [config.md](config.md), DESIGN §5.2).

## Tělo = instrukce

Všechno pod druhým `---` je instrukce agenta v Markdownu. Musí být
neprázdné. `{{ }}` se v těle **nevyhodnocují** — agent je stálý popis role;
hodnoty z konkrétního běhu mu předává krok přes `prompt`.

### Jak vznikne system prompt

Framework skládá system prompt vždy stejně a nic dalšího do něj nepřidává.

**U `task`** (DESIGN §5.8):

1. tělo agenta,
2. oddíl `## Skilly` s řádkem `- <name>: <description>` pro každý skill.

Model dostane nástroj `load_skill(name)`, kde `name` je výčet (`enum`)
skillů agenta. Nástroj vrátí tělo `SKILL.md`. Neznámé jméno vrátí chybu se
seznamem dostupných skillů. Volání `load_skill` se počítá jako tah a
v záznamu je `tool_call` se `server: "_skills"`. `load_skill` se nikdy
neposílá na MCP server.

**U `ask`** (jedno volání, bez nástrojů — D1b): `load_skill` použít nejde,
proto se skilly vkládají **celé**:

1. tělo agenta,
2. pro každý skill v pořadí ze `skills`: řádek `## Skill: <name>` a tělo
   `SKILL.md` bez frontmatteru.

(Alternativa „skilly u `ask` zakázat" je OPEN-QUESTIONS 11.)

Zpráva uživatele (`user`) je `prompt` z kroku. Přesně to, co model dostal,
je v záznamu běhu v `steps/<nn>-<id>/prompt.md` (viz
[run-record.md](run-record.md)).

Když krok žádá JSON (`schema`) a kaskáda (§5.5) je na úrovni `prompt`,
framework připojí na konec system promptu popis požadovaného JSON. I to je
vidět v `prompt.md`. Výstup kroku vynucuje `schema`, ne skill.

## `ask` vs. `task` — co se s agentem stane

| | `ask` | `task` |
|---|---|---|
| Volání modelu | jedno (plus opakování při chybě `transient`/`schema`) | smyčka model ↔ nástroje, nejvýš `max_turns` tahů |
| System prompt | tělo + celé skilly | tělo + seznam skillů |
| Nástroje | **žádné** (MCP se nepřipojuje) | povolené nástroje MCP, `load_skill` (má-li skilly), `_submit_output` (kaskáda) |
| Limity | `budget_usd`, `timeout` | `max_turns`, `budget_usd`, `timeout` |
| Konec | odpověď modelu | model odpoví bez volání nástroje, nebo zavolá `_submit_output` |

## Oprávnění: vlastník → agent → krok (§5.2, §5.8)

Tři vrstvy, každá smí jen zúžit tu předchozí:

1. **Vlastník** v `mcp.yaml` určuje u serveru, kteří agenti ho smí použít
   (`agents`), které scénáře smí spustit agenta s tímto serverem
   (`scenarios`) a horní seznam nástrojů (`tools`).
2. **Agent** říká, co je pro něj **nejvýš** dovoleno (`mcp`, `tools`,
   `limits`).
3. **Krok `task`** může vybrat podmnožinu `mcp` a `tools` a snížit
   `max_turns`, `budget_usd`, `timeout`.

Krok nikdy nemůže přidat server, nástroj ani zvýšit limit. Pokus o to je
chyba `config` při `validate`, např.:

```
config: krok "publikace" chce nástroj instagram.delete_media,
agent "publisher" ho nepovoluje (tools.instagram)
```

Výsledný limit kroku je vždy nejmenší z: limit agenta, limit kroku, zbytek
rozpočtu a času celého běhu (`config.yaml` → `limits`). Do `tools` pro
model jdou jen povolené nástroje (DESIGN §5.8).

Za běhu:

- Když model zavolá nástroj, který povolený není, framework ho nespustí,
  vrátí modelu chybu „nástroj není povolen" a zapíše to do záznamu
  (`tool_call` s `allowed: false`). Běh tím neselže.
- **Argumenty od modelu se před voláním validují** proti schématu nástroje,
  které poslal server (původnímu, ne zjednodušenému pro poskytovatele —
  Gemini části schématu tiše ignoruje, DESIGN §5.8). Když nesedí, nástroj
  se nespustí a model dostane chybu validace jako výsledek nástroje (tah se
  počítá; v záznamu `invalid_args: true`).

## Co v agentovi nesmí být

- Tajné klíče, tokeny, hesla — ani v instrukcích. Klíče existují jen
  v `config.yaml` / `mcp.yaml` jako odkaz na proměnnou prostředí (§5.2).
- Konkrétní id modelu (`anthropic/claude-haiku-4.5`) — jen alias.
