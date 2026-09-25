# Spike (d) MCP klient a skilly v Pythonu — REPORT

Datum měření: 2026-09-25. Host: Linux, Python 3.12.3 (uv 0.11.8), Node v24.18.0.
Klíč OpenRouteru jen z prostředí; ve výsledcích ani v kódu není.
**Útrata: 0,136 USD** z rozpočtu 0,20 USD (`results/_spend.json`, součet `usage.cost`).

## Jak spustit

```bash
cd spikes/mcp-python
uv sync && npm install                        # SDK mcp + servery filesystem/everything lokálně
uv run python q1_client.py                    # otázka 1 (bez sítě a zdarma)
set -a; . ../../.env; set +a                  # klíč OpenRouteru pro otázky 2–4
uv run python q2a_schema_probe.py [--normalize] [--only varianta,…]
uv run python q2b_roundtrip.py --image-mode tool_array|user_followup
uv run python q3_skills.py
uv run python q4_permissions.py
```
`common.py` = parametry serverů, volání OpenRouteru přes `httpx` s hlídáním rozpočtu (0,20 USD),
normalizace schémat, smyčka agenta, dispatch s allowlistem. Každý skript uloží `results/<otázka>.json`.

## Verdikty

| # | Otázka | Verdikt |
|---|---|---|
| 1 | Oficiální SDK `mcp` jako klient (stdio + HTTP) | **funguje**. Výhrada: bez `read_timeout_seconds` se čeká donekonečna; v režimu `auto` handshake s mrtvým serverem trvá navíc pevných 10 s. |
| 2 | MCP schémata → OpenRouter `tools`, úplný kruh | **funguje s výhradou**. Potřeba normalizace (jméno nástroje, `$ref`, `allOf`, `const`, číselný `enum`). Gemini nepřijme obrázek v tool zprávě, obrázek musí jít v následné user zprávě. |
| 3 | Skilly přes `load_skill` + seznam v system promptu | **funguje**. Rozhodnutí 12/12, řízení se skillem 12/12. Výhrada: Haiku obalí výstup vlastním textem, výstup je potřeba vynutit přes `schema`. |
| 4 | Oprávnění (allowlist nástrojů) | **funguje**. Model dostane jen povolené nástroje, nepovolené volání se na server nedostane, krok oprávnění nerozšíří. |

## Tabulka čísel

| Ukazatel | Hodnota | Zdroj |
|---|---|---|
| Start stdio serveru + handshake (lokálně nainstalovaný balíček, `node_modules/.bin`) | **medián 138 ms** (132–143, n=5) | q1 `fs_local_bin` |
| Totéž přes `npx -y` (balíček v cache npm) | **medián 301 ms** (300–311, n=3) | q1 `fs_npx_cached` |
| server-everything stdio: start + handshake | 139 ms; zavření 360 ms (filesystem 15 ms) | q1 |
| Streamable HTTP (server už běží): handshake | 1. spojení 54 ms, dál **~6 ms** | q1 `everything_http` |
| SSE (server už běží): handshake | 1. spojení 32 ms, dál ~5,6 ms | q1 `everything_sse` |
| `tools/list` | ~5 ms (14 nástrojů) | q1 |
| `tools/call` (lokální) | 1–15 ms | q1 |
| Dva stdio servery současně: otevření obou | 259 ms (souběžná volání OK) | q1 `two_servers` |
| Režim `auto` vs. `legacy` u dnešních serverů | bez rozdílu (138 vs. 142 ms) | q1 |
| Zbylé procesy po ukončení (ps, potomci procesu) | **0** ve všech 4 kontrolních bodech | q1 `leftover_*` |
| Schémata: syrová, varianty OK | Haiku 15/16, Gemini 13/16 (n=1 na variantu) | q2a |
| Schémata: po normalizaci | **18/18 na obou modelech** | q2a normalized (+ `_only`) |
| Kruh model→MCP→model, obrázek v tool zprávě | Haiku **3/3**, Gemini **0/3** (HTTP 400) | q2b tool_array |
| Kruh, obrázek v následné user zprávě | Haiku **3/3**, Gemini **3/3** | q2b user_followup |
| Latence kruhu (2 tahy, 2 nástroje) | Haiku medián 2,9–3,1 s; Gemini 1,8 s | q2b |
| Cena kruhu | Haiku 0,0064 USD; Gemini 0,0015 USD | q2b |
| `load_skill`: správné rozhodnutí načíst / nenačíst | **12/12** (Haiku 6/6, Gemini 6/6) | q3 |
| Řízení se skillem (kontrolní znaky z SKILL.md) | 12/12; čistý výstup bez obalu: Haiku 4/6, Gemini 6/6 | q3 |
| Režie popisů nástrojů (`prompt_tokens`, 14 vs. 2 nástroje) | Haiku 2 376 vs. 818; Gemini 1 234 vs. 229 | q4 |

## 1. SDK `mcp` jako klient

**Verze:** `mcp` **2.2.0** (nejnovější na PyPI 2026-09-25), nová hlavní řada v2 s balíčkem `mcp_types`.
Dokumentace: <https://py.sdk.modelcontextprotocol.io/> (v2; migrace z v1 na `/migration/`),
repozitář <https://github.com/modelcontextprotocol/python-sdk>. API jsem ověřil přímo ve zdrojácích
nainstalovaného balíčku (`mcp/client/client.py`, `stdio.py`, `_probe.py`, `session.py`). Servery:
`@modelcontextprotocol/server-filesystem` a `server-everything` **2026.8.31** (npm).

Použité API: `async with Client(server) as c` kde `server` je `StdioServerParameters`, URL (Streamable HTTP)
nebo transport (`sse_client(url)`, `stdio_client(params, errlog=f)`). Potom `c.list_tools()`,
`c.call_tool(name, args, read_timeout_seconds=…)`. Oba servery vyjednaly protokol **2025-11-25**.

- **Chyby nástroje** (všechny přišly jako `CallToolResult.isError = true`, žádná výjimka, session dál žije):
  - chybějící argument: `MCP error -32602: Input validation error: Invalid arguments for tool read_text_file: Invalid input: expected string, received undefined at path`
  - špatný typ: `… expected string, received number at path`
  - cesta mimo povolený kořen: `Access denied - path outside allowed directories: /etc/hostname not in …/sandbox`
  - neznámý nástroj: `MCP error -32602: Tool no_such_tool not found`

  → Pro framework: chyby nástroje nejsou výjimky, runtime musí číst `isError` a vracet text chyby modelu
  (§5.1: je to zpětná vazba pro model, ne selhání kroku).
- **Timeout nástroje:** `call_tool(..., read_timeout_seconds=2)` na 6s operaci vyhodí po 2,00 s
  `mcp.shared.exceptions.MCPError: Request 'tools/call' timed out` (stdio, HTTP i SSE stejně).
  **Session je pak dál použitelná** (další volání OK za 6–16 ms).
- **Server, který neodpoví** (`hang_server.py`):
  - `Client(..., read_timeout_seconds=3, mode="legacy")`: po 3,0 s chyba `MCPError: Request 'initialize' timed out`, zabalená ve **dvou vrstvách `ExceptionGroup`** (anyio task group). Framework ji musí rozbalit, jinak je hláška pro uživatele nečitelná.
  - `mode="auto"` (výchozí): **13,0 s**. SDK nejdřív zkouší `server/discover` (protokol 2026-07-28) s pevným `DISCOVER_TIMEOUT_SECONDS = 10.0` (`mcp/client/session.py`), teprve potom `initialize` s naším timeoutem.
  - Bez `read_timeout_seconds` SDK čeká neomezeně; pojistkou je vnější `anyio.fail_after(4)` → `TimeoutError` po 4,0 s.
- **Ukončení:** stdio transport zavře stdin, počká 2 s, pak SIGTERM a SIGKILL na **celý strom procesů**
  (`mcp/client/stdio.py`, `PROCESS_TERMINATION_TIMEOUT = 2.0`). Ověřeno přes `ps`: po každé fázi
  (14 startů stdio, hang, dva servery, HTTP) **0 potomků, žádné zombie**. Platí i po timeoutu handshaku.
- **Dva servery v jednom procesu:** dva `Client` vedle sebe, souběžná volání přes `anyio` task group
  fungují (fs 12 ms, everything 13 ms a 1s operace paralelně, celkem 1,01 s). SDK má i `ClientSessionGroup`, ten nebyl potřeba.
- **Per běh vs. per krok:** spuštění stdio serveru stojí ~140 ms (lokální balíček) / ~300 ms (`npx -y` z cache)
  a zavření 15–360 ms. U kroků typu `task` s jednotkami sekund na volání modelu je start per krok
  řádově 5 % latence. Na Modalu je studený handshake 0,7 s (spike b), tam by start per krok bolel víc.
- **HTTP/SSE:** `server-everything streamableHttp` a `sse` (lokálně, `PORT=`) fungují; první spojení 32–54 ms,
  další ~6 ms. Chyby a timeout mají stejný tvar jako u stdio.
- **stderr serverů** jde ve výchozím stavu do stderr našeho procesu (u `Client(StdioServerParameters)` se
  to nedá změnit). Zachytit ho jde přes `Client(stdio_client(params, errlog=f))`, ověřeno: 4 řádky stderr v souboru.
- **Prostředí stdio serveru:** SDK předá jen `HOME, LOGNAME, PATH, SHELL, TERM, USER` + to, co je
  výslovně v `StdioServerParameters.env` (ověřeno nástrojem `get-env`). Proměnná nastavená v našem
  procesu (`SPIKE_SECRET_PROBE`) se k serveru **nedostala**, takže `OPENROUTER_API_KEY` serveru neuteče.

## 2. MCP schémata → OpenRouter tools

**Reálná schémata** (27 nástrojů, `results/q1_client.json` → `tools`) obsahují: `$schema` (draft-07, u všech),
`default` (14×), `enum` (5×, jen řetězce), `items`, `minItems`, `minimum`/`maximum`, `format`,
prázdné `properties: {}`, 14/14 filesystem nástrojů má i `outputSchema`. `anyOf`, `$ref` ani
`additionalProperties` se v nich nevyskytly, proto jsou v testu i syntetická schémata (typický výstup Pydanticu/Zodu).

Test: 1 požadavek na (model, varianta), `temperature 0`. Úspěch = HTTP 200 + zavolaný očekávaný nástroj + argumenty
projdou validací `jsonschema` proti **původnímu** schématu.

| Varianta | Haiku syrově | Gemini syrově | Po normalizaci (oba) |
|---|---|---|---|
| reálné filesystem (14) / everything (13) | OK / OK | OK / OK | OK |
| `anyOf` s `null`, `type: [string, null]` | OK | OK | OK |
| `$ref` + `$defs` | OK | **FAIL**: místo objektu poslal řetězec `"vysledek"` | OK (vložení `$ref`) |
| `additionalProperties: false` vnořeně, `additionalProperties` jako mapa | OK | OK | OK |
| `oneOf` + `allOf` (+ `maxLength`) | OK | **FAIL**: `allOf` objekt poslán jako řetězec, `maxLength: 20` porušen | OK |
| `format` (uri, date-time), `pattern` | OK | OK | OK |
| `const` | OK | **FAIL**: jiná hodnota (`test_record` místo `post`) | OK (`const` → `enum`) |
| celočíselný `enum` (`[1,2,3]`) | OK | **FAIL**: argumenty `{}` (vlastnost zmizela) | OK (hodnoty přesunuté do `description`) |
| bez `properties`, `$schema` draft-07 / 2020-12 | OK | OK | OK |
| jméno s tečkou `fs.list_directory` | **HTTP 400** | OK | OK (znaky → `_`) |
| jméno `fs__list_directory`, 70 znaků | OK | OK | OK |

Chyba jména u Claude (vrátili ji Azure i Amazon Bedrock, OpenRouter zkoušel víc providerů za sebou):
`tools.0.custom.name: String should match pattern '^[a-zA-Z0-9_-]{1,128}$'`.

**Potřebná normalizace** (`common.normalize_schema`, `safe_tool_name`):
1. jméno `server__tool`, znaky mimo `[a-zA-Z0-9_-]` → `_`, max 64 znaků, mapa jméno API → (server, nástroj);
2. vložit `$ref` z `$defs`/`definitions` (rekurzivní `$ref` → chyba `config`);
3. sloučit `allOf`, `oneOf` → `anyOf`, `const` → `enum: [x]`;
4. nečíselný (ne-řetězcový) `enum` odstranit a hodnoty dopsat do `description`;
5. kořen vždy `{type: object, properties: {...}}`; `$schema` odstranit (vadilo jen kosmeticky, oba modely ho snesly).

Normalizace nezaručí omezení typu `maxLength`/`pattern` u Gemini. **Argumenty se proto validují na straně klienta
proti původnímu schématu** (`make_dispatch`) a chyba jde modelu zpět jako výsledek nástroje. Server
validuje taky (viz Q1), ale na to se nedá spolehnout u každého serveru.

**Úplný kruh** (`q2b_roundtrip.py`): 14 nástrojů filesystem po normalizaci. Úloha: přečíst `hello.txt` (text)
a `barva.png` (červené PNG přes `read_media_file`, barvu nejde uhodnout z textu) a odpovědět jednou větou.
Oba modely v 1. tahu zavolaly **oba nástroje paralelně**, ve 2. tahu odpověděly. `reasoning_details` se vracejí beze změny.

- Obrázek jako `image_url` (data URL) **uvnitř tool zprávy**: Haiku 3/3 správně „červenou“. Gemini **0/3**:
  HTTP 400 `{"code":400,"message":"Requests ending with a model turn are not supported.","status":"INVALID_ARGUMENT"}` (provider Google).
  Textové pole v tool zprávě Gemini snese (režim B), vadí až obrázek. Dokumentace OpenRouteru k tool calling
  (<https://openrouter.ai/docs/guides/features/tool-calling>) obrázky v tool zprávě nezmiňuje. Jde o naměřené, nedokumentované chování.
- Obrázek **v následné user zprávě** (v tool zprávě jen text „obrázek přiložen v další zprávě“): **Haiku 3/3, Gemini 3/3**.

## 3. Skilly pro API modely

Návrh: `skills/<name>/SKILL.md` s frontmatter `name` + `description`. System prompt obsahuje krátký seznam
(`- jméno: description`) a pravidlo „když je skill relevantní, nejdřív ho načti přes `load_skill`“.
Nástroj `load_skill(name)` má `name` jako `enum` dostupných skillů a vrací celý SKILL.md, neznámé jméno vrátí chybu se seznamem.
Testovací skilly: `ig-caption` (kontrolní znaky: první řádek začíná 🌿, poslední řádek „Uvidíme se u okna.“)
a `hashtag-check` (výstup `VERDIKT: …`).

| Prompt | Haiku (2×) | Gemini (2×) |
|---|---|---|
| caption k dýňovému latté → `ig-caption` | načteno 2/2, znaky 2/2, **obal 2/2** | načteno 2/2, znaky 2/2, čistě |
| kontrola hashtagů → `hashtag-check` | 2/2, `VERDIKT: NEOK` 2/2 | 2/2, 2/2 |
| nerelevantní (pára a mléko) → nenačítat | nenačetl 2/2 | nenačetl 2/2 |

Úspěšnost rozhodnutí **12/12**, řízení se skillem **12/12**, žádné zbytečné ani vícenásobné načtení.
Haiku obalí caption úvodem („Tady je caption…“, `---`) a nabídkou hashtagů. Obsah odpovídá skillu, ale
pro strojové předání dál je potřeba `schema` (kaskáda ze spiku (a)). Cena: Haiku ~0,003 USD, Gemini ~0,0004 USD na úlohu se skillem.
Vzorek je malý (2 opakování) a jde o snadné rozlišení. Hraniční prompty (příbuzné téma, ale ne úkol) netestovány.

## 4. Oprávnění (§5.2)

Návrh (`q4_permissions.py`, `effective()` + `common.make_dispatch`):
- agent definuje **maximum** `{server: [nástroje]}`, krok volitelně zúží; efektivní sada = seznam z kroku, pokud je podmnožinou maxima;
- krok, který rozšiřuje (`write_file`, jiný server, neznámý nástroj), skončí chybou
  `config: krok rozšiřuje oprávnění agenta o fs:['write_file']`, zachytí ji `validate`;
- allowlist **podle jména**, ne denylist, takže nový nástroj, který server přidá (např. po `list_changed`), agent neuvidí;
- do `tools` jdou jen nástroje z efektivní sady (ověřeno: payload = `fs__list_directory`, `fs__read_text_file`);
- dispatch odmítne jméno mimo allowlist dřív, než dojde na server (`Nástroj fs__write_file není pro tohoto agenta povolen.`, soubor nevznikl).

Živý test („zapiš soubor“, zápis nepovolen): Haiku nic nevolal a odpověděl, že nástroj pro zápis nemá. Gemini jen četl
(`fs__read_text_file`), soubor nevznikl u žádného modelu. Oba vypsaly jen povolené nástroje.
Vedlejší přínos: 2 nástroje místo 14 = **−66 % (Haiku) / −81 % (Gemini) `prompt_tokens`** v každém tahu.

Allowlist v klientovi není sandbox: proces serveru má pořád všechny nástroje a svá oprávnění.
Druhá vrstva patří do `mcp.yaml` (argumenty serveru, např. povolený kořen filesystemu, který se ověřil v Q1).

## Nečekané nálezy

1. **SDK v2 + protokol 2026-07-28:** výchozí `mode="auto"` zkouší `server/discover` s **pevným 10s timeoutem**. U dnešních
   serverů (2025-11-25) to nic nestojí, ale mrtvý server se pozná až po 10 s + náš timeout.
2. **Chyba handshaku je ve dvou vrstvách `ExceptionGroup`**, ne přímo `MCPError`.
3. **Gemini přes OpenRouter tiše ignoruje části schématu** (`$ref`, `allOf`, `const`, číselný `enum`): HTTP 200 a špatné
   argumenty. Chyba se neprojeví při odeslání, jen validací argumentů.
4. **Gemini odmítá obrázek v tool zprávě** hláškou o „model turn“, která k příčině nijak nevede.
5. **OpenRouter při 400 kvůli jménu nástroje zkouší další providery** (Azure → Bedrock → …). Chyba je deterministická, jen přibyde latence.
6. server-everything se po zavření stdin ukončuje ~360 ms (filesystem 15 ms). Úklid proběhl pokaždé.
7. Stdio server nezdědí prostředí frameworku (jen 6 bezpečných proměnných). Pro §5.2 dobrá zpráva, ale klíče pro
   MCP servery se musí předat výslovně přes `env` z `mcp.yaml`.

## Co z toho plyne pro Fázi 2 (fakta a doporučení; rozhodnutí je na koordinátorovi)

- **SDK `mcp` 2.x jako klient stačí** (D4 ho už má v sadě): stdio, Streamable HTTP i SSE, čisté ukončení stromu procesů,
  souběžné servery. Doporučení: zamknout `mcp==2.2.*` a přidat konformační test na tvar chyb a timeoutů. v2 je čerstvá řada
  a má vlastní vyjednávání protokolu.
- **Timeouty vždy nastavit:** `read_timeout_seconds` na handshake i `call_tool` + vnější `fail_after` jako pojistka.
  Pro servery z `mcp.yaml` zvážit `mode="legacy"`, dokud nebudou servery 2026-07-28, protože šetří 10 s při mrtvém serveru.
  Rozbalit `ExceptionGroup` do třídy `timeout`/`config` (§5.1).
- **Životnost serveru:** start stdio ~140 ms lokálně / ~300 ms přes `npx -y` → spouštět **per běh** (nebo per krok `task`, když
  krok potřebuje izolaci). Balíčky předinstalovat (sedí s D5: `npx -y` je pomalejší i lokálně).
- **Mapování chyb:** `isError: true` → zpětná vazba modelu (neukončí krok), `MCPError … timed out` → třída `timeout`,
  selhání handshaku → `config`/`transient`.
- **Převod schémat** je malá funkce (~50 řádků): jména `server__tool` s mapou zpět, vložení `$ref`, `allOf`/`oneOf`/`const`,
  ne-řetězcový `enum`. **Validace argumentů na klientovi** proti původnímu schématu je povinná (Gemini).
  Konformační scénář aliasu (§5.5) by měl obsahovat schéma s `$ref`, `const` a číselným `enum`.
- **Obrázky z nástrojů:** jednotně posílat v následné user zprávě (funguje u obou modelů). Obrázek v tool zprávě je
  závislý na modelu. Base64 do záznamu běhu nepatří (§5.7), obrázek z nástroje uložit jako soubor.
- **Skilly:** `load_skill` + seznam `jméno: description` v system promptu funguje na obou levných modelech. Doporučení:
  `enum` jmen v parametru, chyba se seznamem dostupných a výstup kroku vynucovat `schema`, ne skillem.
- **Oprávnění:** allowlist podle jména, efektivní sada = krok ⊆ agent (jinak chyba `validate`), filtrovat `tools` i dispatch.
  Druhá vrstva = argumenty serveru v `mcp.yaml`. Allowlist navíc šetří tokeny (−66 až −81 %).
- **stderr serverů** směrovat do záznamu běhu přes `stdio_client(params, errlog=…)`.

## Soubory

- `q1_client.py`, `hang_server.py` → `results/q1_client.json` (včetně plných schémat nástrojů)
- `q2a_schema_probe.py` → `results/q2a_schema_probe.json` (syrově), `_only.json` (izolace `const`/`enum`),
  `_normalized.json` (celý běh po normalizaci, **před** opravou číselného `enum`), `_normalized_only.json` (po opravě)
- `q2b_roundtrip.py` → `results/q2b_roundtrip_tool_array.json`, `results/q2b_roundtrip_user_followup.json`
- `q3_skills.py`, `skills/*/SKILL.md` → `results/q3_skills.json` (první běh se starou, přísnou kontrolou jsem přepsal; jeho útrata je v `_spend.json`)
- `q4_permissions.py` → `results/q4_permissions.json`
- `common.py`: sdílené funkce; `sandbox/` si skripty vytvoří samy (v `.gitignore`)
