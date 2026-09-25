# Formát agenta — specifikace v1

Agent je jeden soubor `workflows/agents/<name>.md`: nahoře konfigurace
(YAML frontmatter mezi dvěma řádky `---`), pod ní instrukce v Markdownu
(DESIGN D1a). Scénář agenta volá jménem v kroku `ask` nebo `task`.

Strojová podoba: [`schema/agent.schema.json`](schema/agent.schema.json).
Ukázky: `workflows/agents/copywriter.md`, `photographer.md`, `publisher.md`.

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
| `skills` | ne | Seznam skillů ze `workflows/skills/<name>/SKILL.md`. Jejich text se přidá do system promptu (viz níže). | Žádné skilly. | `skills: [ig-pravidla]` |
| `mcp` | ne | Seznam MCP serverů z `mcp.yaml`, ke kterým se agent smí připojit. Používá je jen krok `task`. | Agent nemá žádné nástroje. | `mcp: [instagram]` |
| `tools` | ne | Zúžení nástrojů: pro server z `mcp` seznam nástrojů, které agent smí volat. Server, který v `tools` není, dává **všechny** své nástroje (`validate --dry-run` je vypíše, aby to bylo vidět). | Všechny nástroje serverů z `mcp`. | `tools: { instagram: [publish_media] }` |
| `limits` | ano | Horní hranice pro jedno použití agenta v kroku. Krok je smí jen snížit. | Chyba `config`. | viz níže |
| `limits.max_turns` | ano | Kolik volání modelu smí proběhnout v jednom kroku `task` (§5.1 bod 6). U `ask` se nepoužije — `ask` je vždy jedno volání (plus opakování při chybě). | Chyba `config`. | `max_turns: 6` |
| `limits.budget_usd` | ano | Kolik USD smí stát jeden krok s tímto agentem (všechna volání včetně opakování). | Chyba `config`. | `budget_usd: 0.20` |
| `limits.timeout` | ne | Nejdelší doba jednoho kroku s tímto agentem. Formát `<číslo>s`, `m` nebo `h`. | Výchozí podle typu kroku (`ask` 2m, `task` 15m) — **návrh**. | `timeout: 5m` |

Jiná pole frontmatter nepovoluje — překlep (`modle:`) je chyba `config`,
ne tiše ignorované pole.

## Tělo = instrukce

Všechno pod druhým `---` je instrukce agenta v Markdownu. Musí být
neprázdné. `{{ }}` se v těle **nevyhodnocují** — agent je stálý popis role;
hodnoty z konkrétního běhu mu předává krok přes `prompt`.

### Jak vznikne system prompt (**návrh**)

Framework skládá system prompt vždy stejně a nic dalšího do něj nepřidává:

1. tělo agenta,
2. pro každý skill v pořadí ze `skills`: řádek `## Skill: <name>` a text
   `SKILL.md` bez jeho frontmatteru.

Zpráva uživatele (`user`) je `prompt` z kroku. Přesně to, co model dostal,
je v záznamu běhu v `steps/<nn>-<id>/prompt.md` (viz
[run-record.md](run-record.md)).

Když krok žádá JSON (`schema`) a model nezvládne nativní schéma ani
nástroj-obal, framework v poslední úrovni kaskády (§5.5) připojí na konec
system promptu popis požadovaného JSON. I to je vidět v `prompt.md`.

Skilly se ve v1 vkládají celé (ne „na vyžádání"). Když budou dlouhé, přidá
se načítání na vyžádání jako změna frameworku, formát agenta se nemění.

## `ask` vs. `task` — co se s agentem stane

| | `ask` | `task` |
|---|---|---|
| Volání modelu | jedno (plus opakování při chybě `transient`/`schema`) | smyčka model ↔ nástroje, nejvýš `max_turns` volání |
| System prompt | tělo + skilly | tělo + skilly |
| MCP servery a nástroje | **nepoužijí se** (nepřipojují se) | připojí se servery z `mcp`, model vidí jen povolené nástroje |
| Limity | `budget_usd`, `timeout` | `max_turns`, `budget_usd`, `timeout` |
| Konec | odpověď modelu | model odpoví bez volání nástroje |

## Agent = maximum oprávnění, krok jen zužuje (§5.2)

Agent říká, co je **nejvýš** dovoleno. Krok `task` může:

- vybrat podmnožinu `mcp` a `tools`,
- snížit `max_turns`, `budget_usd`, `timeout`.

Krok nikdy nemůže přidat server, nástroj ani zvýšit limit. Pokus o to je
chyba `config` při `validate`, např.:

```
config: krok "publikace" chce nástroj instagram.delete_media,
agent "publisher" ho nepovoluje (tools.instagram)
```

Výsledný limit kroku je vždy nejmenší z: limit agenta, limit kroku, zbytek
rozpočtu a času celého běhu (`config.yaml` → `limits`).

Když model v `task` zavolá nástroj, který povolený není, framework ho
nespustí, vrátí modelu chybu „nástroj není povolen" a zapíše to do záznamu
(`tool_call` s `allowed: false`). Běh tím neselže.

## Co v agentovi nesmí být

- Tajné klíče, tokeny, hesla — ani v instrukcích. Klíče existují jen
  v `config.yaml` / `mcp.yaml` jako odkaz na proměnnou prostředí (§5.2).
- Konkrétní id modelu (`anthropic/claude-haiku-4.5`) — jen alias.
