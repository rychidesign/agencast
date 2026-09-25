# Nezávislá kontrola specifikace v1

Datum: 2026-09-25. Recenzent: worker `task_2de99b7af9e5` (specifikaci nepsal).
Kontrolováno proti `DESIGN.md` z **hlavního checkoutu**
(`~/workspace/multiagent-workflows/docs/DESIGN.md`, v0.2 s §5.8 a fakty ze
spiků (c) a (d)). Citace `DESIGN.md:<řádek>` se vztahují k tomuto souboru.
Kopie `docs/DESIGN.md` v této větvi §5.8 nemá; odtud pochází většina
rozporů ve skillech, nástrojích a MCP (B1, B2, D16–D19).

Souhrn: **6 BLOKUJÍCÍCH, 23 DŮLEŽITÝCH, 12 DROBNÝCH**.

## Jak ověřeno

- Ukázky proti schématům (`uvx check-jsonschema` 0.38.2): `ig-post.yaml`,
  frontmatter tří agentů, `config.example.yaml`, `mcp.example.yaml` → vše `ok`.
- 27 záměrně chybných scénářů + 3 agenti + 4 `mcp.yaml` + 2 `config.yaml`
  (v `/tmp/rv`, do repozitáře nepatří). Schéma **pustí**, i když to text
  zakazuje nebo nedefinuje: duplicitní `id` (to řeší `validate`, v pořádku),
  `schema: string` a `schema: [string]` u `ask`, `outputs: {}`, `retry: 1000`,
  `tools` pro server, který není v `mcp`, `env: {LD_PRELOAD: …}` v `mcp.yaml`,
  `base_url: http://evil.example.com`, stejná proměnná pro token webhooku,
  tajemství callbacku i klíč OpenRouteru.
- Stejné soubory načtené **PyYAML** (knihovna z D4) + `jsonschema` — výsledky
  se od `check-jsonschema` (ruamel, YAML 1.2) liší, viz B6.

---

## BLOKUJÍCÍ

### B1. Skilly se podle spec vkládají celé, DESIGN chce seznam + `load_skill`
- **Kde:** `agent.md:41`, `agent.md:58-75` vs. `DESIGN.md:347-350`; `DESIGN.md:61-63` (D1b).
- **Co:** Spec skládá system prompt jako „tělo + celý text každého SKILL.md“
  a načítání na vyžádání odkládá na později. Podle §5.8 nese system prompt jen
  `jméno: description` a tělo se načte nástrojem `load_skill(name)`. Formát
  `SKILL.md` (`name` + `description` ve frontmatteru) spec nedefinuje a
  schéma pro něj chybí. Navíc `ask` podle D1b nemá smyčku nástrojů, takže
  `load_skill` v něm fungovat nemůže, a spec neříká, co pak.
- **Proč:** Porušuje závazný §5.8. Chování `ask` se skilly by se v kódu
  rozhodlo náhodně.
- **Návrh:** Do `agent.md` napsat: „U `task` obsahuje system prompt tělo
  agenta a oddíl `## Skilly` s řádky `- <name>: <description>`. Model dostane
  nástroj `load_skill(name)`, kde `name` je `enum` skillů agenta. Neznámé
  jméno vrátí chybu se seznamem. Volání se počítá jako tah a v záznamu je
  `tool_call` se `server: "_skills"`. U `ask` se skilly vkládají celé (ask nemá
  nástroje).“ Poslední větu přidat do OPEN-QUESTIONS jako otázku 11
  (alternativa: `ask` se skilly zakázat). Přidat `docs/spec/skill.md` a
  `schema/skill.schema.json`: frontmatter `name` (= jméno složky, kebab),
  `description` (povinné), nic jiného; tělo neprázdné.

### B2. Server v `mcp` bez `tools` = všechny nástroje, což odporuje allowlistu podle jména
- **Kde:** `agent.md:43`, `OPEN-QUESTIONS.md:38-43`, `agent.schema.json:15-25` vs. `DESIGN.md:351-354`.
- **Co:** Spec (a doporučení k otázce 6) dává serveru bez záznamu v `tools`
  všechny nástroje. §5.8 chce allowlist podle jména. Spike (d) ho zdůvodňuje
  tím, že „nový nástroj, který server přidá (`list_changed`), agent neuvidí“
  (`spike-mcp-python:spikes/mcp-python/REPORT.md:171`). Při výchozím „všechny“
  agent nový nástroj uvidí, třeba `delete_media` po aktualizaci serveru.
- **Proč:** Porušuje DESIGN §5.8. Otázka 6 byla položena, než §5.8 vznikl.
- **Návrh:** V `agent.md:43` psát: „Každý server z `mcp` musí mít v `tools`
  výslovný seznam nástrojů. Server bez záznamu je chyba `config`.
  `validate --dry-run` vypíše nástroje, které server nabízí, aby šel seznam
  napsat.“ Do `agent.schema.json` přidat `dependentRequired: {"mcp": ["tools"]}`.
  `validate` kontroluje, že klíče `tools` = `mcp`. Otázku 6 označit jako
  vyřešenou podle §5.8.

### B3. Kaskáda strukturovaného výstupu je v rozporu s pravidlem úspěchu kroku
- **Kde:** `scenario.md:207`, `scenario.md:221-223`, `scenario.md:253-254`, `scenario.md:702` vs. `DESIGN.md:279-284`, `DESIGN.md:136-138`.
- **Co:** `ask` je úspěšný jen při `finish_reason: stop` a `task` končí, když
  model odpoví bez volání nástroje. Na úrovni L2 (nástroj jako obal) je ale
  správná odpověď právě volání nástroje (`finish_reason: tool_calls`). `ask`
  na L2 by tedy vždy selhal a `task` by volání obalu poslal do dispatch
  (a ten by ho odmítl jako nepovolený nástroj). Spec také neříká, **kdy**
  framework přejde z L1 na L2/L3: předem podle aliasu, nebo po chybě `schema`?
  A spotřebuje přechod pokus z `retry`?
- **Proč:** Kaskádu vyžaduje DESIGN (D3, §5.5). Podle textu spec ji nejde
  naprogramovat.
- **Návrh:** Do `scenario.md` (za `:223`) doplnit: „Úroveň kaskády začíná na
  `models.<alias>.structured_output` z `config.yaml` (`native_schema` |
  `tool_wrapper` | `prompt`, výchozí `native_schema`; nastavuje ji konformační
  scénář). Po chybě `schema` jde další pokus o úroveň níž. Pokus se počítá do
  `retry`. Na úrovni `tool_wrapper` je úspěch volání nástroje `_submit_output`
  s argumenty, které odpovídají `schema` (`finish_reason: tool_calls`). U `task`
  toto volání ukončí smyčku. `_submit_output` se nikdy nedispatchuje na MCP a
  nepodléhá allowlistu.“ Přidat pole `structured_output` do `config.md` a
  `config.schema.json`.

### B4. `dedupe.jsonl` je soubor sdílený mezi běhy
- **Kde:** `scenario.md:180-182` vs. `DESIGN.md:115-117` (D2).
- **Co:** D2: „běhy si nesdílí soubory (kromě `state` a úložiště výstupů)“,
  aby šly paralelní běhy. Spec zavádí jeden `<runs>/dedupe.jsonl` pro všechny
  běhy. Modal Volume je na posledním `commit()` (`DESIGN.md:184`), takže dva
  souběžné zápisy se ztratí.
- **Proč:** Porušuje D2. Zároveň jde o funkci „jednou a dost“ pro publikaci,
  kde ztracený zápis znamená dvojí příspěvek.
- **Návrh:** Přidat do OPEN-QUESTIONS otázku „dedupe je sdílený stav, výjimka
  z D2 jako `state`“ a ve spec psát: „Každý klíč je samostatný soubor
  `<runs>/_dedupe/<sha256(scenario + '/' + step_id + '/' + klíč)>.json`,
  vytvořený atomicky (vytvoř, jen když neexistuje). Obsah: stav
  (`started` | `succeeded`), `run_id`, výstup.“ Stav `started` viz D7.

### B5. Chybí smlouva webhooku: požadavek, odpověď, token, idempotence, pozice ve frontě
- **Kde:** `config.md:126-135`, `scenario.md:89-90`, `run-record.md:104` vs. `DESIGN.md:118-120`, `DESIGN.md:171-179`, `DESIGN.md:247-249`.
- **Co:** Spec definuje callback, ale ne požadavek na spuštění: chybí URL,
  hlavička s tokenem, tělo (`scenario`, `inputs`, `callback_url`,
  `request_key`) i odpověď (`run_id`, pozice ve frontě podle D2). Chybí také,
  co udělá opakovaný `request_key` (§5.2), a kdy se validuje. `scenario.md:89-90`
  vrací chybu vstupů „hned“, D2 ale chce callback **vždy**. Když `validate`
  proběhne až po vyzvednutí z fronty na Modalu, spec neurčuje, jestli
  callback přijde.
- **Proč:** n8n se podle spec nedá napojit. D2 i §5.2 zůstávají
  nesplněné.
- **Návrh:** Nový oddíl `run-record.md#webhook` (nebo `webhook.md`):
  „`POST /runs`, hlavička `Authorization: Bearer <token z webhook.token_env>`,
  tělo `{scenario, inputs, callback_url (jen https), request_key?}`.
  Synchronně: 401 = token; 422 = neznámý scénář, vstupy nesedí na `inputs`
  nebo neprošel `validate`. Pak nevzniká `run_id` ani callback. Jinak 202
  `{run_id, queue_position}`, kde `queue_position` počítá framework
  (D5: Modal ho nedává) a smí být `null`. Opakovaný `request_key` vrátí 200
  s původním `run_id` a nový běh nevznikne. Od přidělení `run_id` se callback
  posílá vždy, i když `validate` selže až po vyzvednutí z fronty.“

### B6. PyYAML (D4) tiše mění význam scénáře, ověření přes check-jsonschema to skrylo
- **Kde:** `scenario.md:62-63` („překlep je chyba“), `scenario.md:316`, `scenario.md:391-393`; `CHANGELOG.md:97-98`; `DESIGN.md:161` (pyyaml), `DESIGN.md:219` (§5.1).
- **Co:** Naměřeno (`yaml.safe_load`, PyYAML):
  `a: 4:5` → `245`; `on: x` a `yes: y` v jedné mapě → `{True: 'y'}` (hodnota
  `on` tiše zmizela); duplicitní `when:` v kroku → platí poslední, bez chyby
  (ruamel v check-jsonschema hlásí `DuplicateKeyError`). `cases: {yes: …}`
  projde schématem (`cases` nemá `propertyNames`), klíč je `True` a ta větev
  nikdy nesedí na `value`, takže běh tiše skončí v `default`. Spec to řeší jen
  radou „piš v uvozovkách“.
- **Proč:** Spec slibuje, že překlep je chyba, a §5.1 říká „nic neselže
  potichu“. Schémata byla ověřena jiným parserem, než jaký použije framework.
- **Návrh:** Do `scenario.md` §1 (a obdobně do `agent.md`, `config.md`)
  doplnit: „Soubory se čtou jako YAML 1.2 core schema: `true`/`false` jsou
  jediné booleany (`yes`, `no`, `on`, `off` jsou text), `4:5` je text,
  duplicitní klíč v mapě je chyba `config` s číslem řádku.“ Pro implementaci
  (PyYAML zůstává) napsat vlastní `SafeLoader` bez resolverů YAML 1.1 bool a
  sexagesimal a s kontrolou duplicit. Do `scenario.schema.json:277-281`
  přidat `"propertyNames": {"type": "string"}`. Změnit `CHANGELOG.md:97-98`:
  ověření musí proběhnout stejným loaderem, jaký používá framework.

---

## DŮLEŽITÉ

### D1. MCP server z `mcp.yaml` smí použít kdokoli, kdo napíše agenta
- **Kde:** `config.md:141`, `agent.md:87-95` vs. `DESIGN.md:212-213`, `DESIGN.md:130-132`.
- **Co:** Agenty podle DESIGN §4 píší „ostatní lidé a agenti“. Kdokoli tedy
  založí agenta s `mcp: [instagram]` a publikuje. Vlastník v `mcp.yaml`
  určuje jen to, že server existuje, ne kdo ho smí použít.
  Pravidlo „agent = maximum“ chrání jen před autorem scénáře, ne před autorem
  agenta.
- **Návrh:** Do `mcp.yaml` přidat povinné `agents: [publisher]` (kteří agenti
  smí server použít) a volitelné `tools: [...]` (horní allowlist vlastníka).
  `validate`: agent se serverem mimo `agents` nebo s nástrojem mimo `tools`
  serveru = chyba `config`.

### D2. `call` a `task` s agentem `publisher` obejdou schvalování člověkem
- **Kde:** `scenario.md:400-432`, `ig-post.yaml:3` vs. `DESIGN.md:123-124`.
- **Co:** Schvalování je v n8n mezi částmi workflow. Nic ale nebrání scénáři
  z části 1 zavolat scénář části 2 (`call: {scenario: ig-publish}`) nebo
  rovnou `task` s agentem `publisher`. Příspěvek by se pak zveřejnil bez
  schválení.
- **Návrh:** Do hlavičky scénáře přidat `callable: false|true`, výchozí
  `false`: `call` smí jen na scénář s `callable: true`. Do agenta přidat
  `scenarios: [ig-publish]`, tedy seznam scénářů, které agenta s vedlejším
  účinkem smí použít; chybí-li, smí kdokoli. `validate` obojí kontroluje.

### D3. Hodnota `file` může vzniknout z textu, může být `null` a nahrání může selhat
- **Kde:** `scenario.md:103-108`, `scenario.md:151`, `scenario.md:480-486`, `config.md:106`.
- **Co:** (a) `output` připouští „pevné hodnoty“. Pro výstup typu `file` tak
  jde napsat `image: "~/.env"` nebo `../../x` a spec neříká, že to
  je chyba, takže soubor mimo složku běhu by šel do veřejného úložiště.
  (b) `default: { file: null }` (příklad na `:151`) → `output.image` je
  `null`: nahraje se něco, vrátí `null`, nebo chyba? (c) Selhání nahrání
  obrázku do R2 nemá třídu ani stav běhu (`report_url` chování má,
  `outputs` ne).
- **Návrh:** Do `scenario.md` §5 Typy: „`file` vzniká jen z kroku `image`
  (a z obrázků nástrojů, D18). Z textu ho vytvořit nejde. Text v místě
  `file` je chyba `validate`. Cesta je vždy uvnitř složky běhu a framework to
  před nahráním ověří (`realpath`).“ K `outputs`: „`file: null` z výslovného
  `default` jde do callbacku jako `null`.“ K nahrání: „Selhání nahrání souboru
  z `output` = `transient` s opakováním, pak běh `failed`, třída `transient`,
  krok `output`.“

### D4. Filesystem server v ukázce vidí složky všech běhů
- **Kde:** `mcp.example.yaml:6-9`, `config.md:149-152` vs. `DESIGN.md:115-117`, `DESIGN.md:355`.
- **Co:** Popis „ve složce běhu“, ale kořen je `/runs`, tedy všechny běhy
  včetně `_dedupe`, `inputs.json` a `callback.json` cizích běhů, a to i pro
  zápis. §5.8 staví na kořeni filesystemu jako druhé vrstvě oprávnění. Spec
  ale nemá způsob, jak do `args` dát složku **aktuálního** běhu.
- **Návrh:** Do `config.md` (`args`) doplnit: „Jediná povolená náhrada v
  `args` je `{run_dir}` (absolutní cesta složky aktuálního běhu), jiné `{…}`
  jsou chyba `config`.“ V ukázce psát `args: ["@modelcontextprotocol/server-filesystem", "{run_dir}/work"]`.

### D5. Veřejný `report.html` na uhodnutelné adrese
- **Kde:** `run-record.md:43-44`, `config.md:104-108` vs. `DESIGN.md:128-129`.
- **Co:** Klíč v úložišti je `<run_id>/…` a `run_id` je čas + jméno scénáře +
  4 hex znaky (65 536 možností). Bucket je veřejný (kvůli Instagramu), takže
  `report.html` se všemi prompty, odpověďmi a výsledky nástrojů jde najít
  zkoušením. Totéž platí pro neschválené obrázky.
- **Návrh:** `config.md:106` změnit na: „Klíč = `<run_id>-<32 hex náhodných
  znaků>/<jméno>.<přípona>`. Náhodná část vzniká při startu běhu a je jen
  v callbacku a v záznamu.“ (Alternativa: `report.html` do neveřejného
  prefixu a v callbacku předpodepsaná URL.)

### D6. Tajné hodnoty se mohou dostat do záznamu přes výsledek nástroje
- **Kde:** `run-record.md:57-66` vs. `DESIGN.md:240-242`; spike (d) `REPORT.md:94-96` (nástroj `get-env` vrací prostředí serveru).
- **Co:** MCP server dostane klíč přes `env` a jeho nástroj ho může vrátit
  (debug, chybová hláška). Hodnota pak skončí v kontextu modelu,
  v `calls/NN.tool.json` a ve veřejném `report.html`. Spec zakazuje jen
  hlavičky požadavků.
- **Návrh:** Do `run-record.md` §„Co do záznamu nikdy nepatří“ doplnit: „Před
  zápisem každého souboru záznamu a callbacku framework nahradí každý výskyt
  hodnoty kterékoli proměnné z polí `*_env` a `env` (délka ≥ 8 znaků) textem
  `<tajné: JMENO>` a zapíše varování.“

### D7. `dedupe_key` nechrání, když krok selže až po vedlejším účinku, a klíče se míchají mezi scénáři
- **Kde:** `scenario.md:166` vs. `DESIGN.md:248-249`.
- **Co:** Záznam vzniká jen po **úspěšném** kroku. Když `publish_media`
  proběhne a krok pak selže (rozpočet, timeout, `schema` finální odpovědi),
  n8n běh zopakuje a příspěvek vyjde dvakrát. Klíč také není vázaný na
  scénář a krok, takže stejný text klíče v jiném scénáři vrátí cizí výstup
  jiného tvaru.
- **Návrh:** „Záznam `started` vzniká před prvním voláním nástroje kroku.
  Když při dalším běhu existuje `started` bez `succeeded`, krok se nespustí:
  chyba třídy `config` se zprávou ‚krok mohl proběhnout jen částečně, ověř
  ručně a smaž <soubor>‘. Klíč se ukládá spolu se jménem scénáře a `id`
  kroku.“

### D8. Rozpočet: poslední volání, souběžné větve a chybějící cena
- **Kde:** `scenario.md:162`, `scenario.md:705-706`, `run-record.md:93-94`, `config.md:118-119` vs. `DESIGN.md:311-313`.
- **Co:** (a) Kontrola po volání znamená, že volání, které rozpočet
  překročí, už proběhlo. Je krok, který tímto voláním dostal platnou
  odpověď, `succeeded`, nebo `budget`? (b) Větve `parallel` kontrolují
  rozpočet souběžně, takže překročení může být až N volání. (c) Chybějící
  `usage.cost` dá jen varování, rozpočet pak neplatí, a přitom
  `config.md:118` tvrdí, že „běh bez stropu útraty neexistuje“. Bod 4 na
  `:705` je formulovaný jako podmínka úspěchu, ale je to jen varování.
  (d) §5.7 chce počítat obrázky zvlášť i do **časového** limitu. Spec má jen
  `run_image_budget_usd`.
- **Návrh:** „Před každým voláním: když útrata ≥ rozpočet, volání se
  nespustí → `budget`. Volání, které rozpočet překročí, se dokončí a jeho
  výsledek platí (varování ‚rozpočet překročen o X USD‘). Ve `parallel` platí
  totéž, překročení je nejvýš o jedno volání na větev. Chybějící `cost` =
  opakovat jako `transient`; po vyčerpání `retry` třída `budget` se zprávou
  ‚cena neznámá‘.“ Bod 4 na `:705` přesunout mimo seznam podmínek.
  Přidat `run_finished.image_duration_s`, nebo v changelogu uvést, že
  časový limit obrázků zvlášť ve v1 není.

### D9. Počítají se opakování do `max_turns`?
- **Kde:** `scenario.md:163`, `scenario.md:248`, `agent.md:45`, `agent.md:81`.
- **Co:** `max_turns` = „nejvýš tolik volání modelu“. `retry` platí „pro každé
  volání ve smyčce zvlášť“. Při `max_turns: 4` a `retry: 2` může být 4
  nebo 12 volání.
- **Návrh:** „`max_turns` počítá tahy (odpovědi modelu, které smyčka
  zpracovala). Opakování jednoho tahu po `transient`/`schema` se do
  `max_turns` nepočítá, jen do `budget_usd`.“

### D10. `image` bez obrázku: `transient`, nebo `content`? A tiše ignorovaný `aspect_ratio`
- **Kde:** `scenario.md:681` vs. `scenario.md:683`; `scenario.md:316`, `scenario.md:325-329` vs. `DESIGN.md:313-314`, `DESIGN.md:417-418`.
- **Co:** HTTP 200 bez obsahu a bez odmítnutí je `transient`, ale „`image`
  bez obrázku“ je `content`. Pro 200 bez `images`, bez `refusal` a
  s `finish_reason: stop` platí obojí. Tvar odmítnutí nikdo nenaměřil
  (DESIGN §7 bod 7). U `aspect_ratio` chybí, co se stane, když ho zvolený
  endpoint ignoruje (spike ho u chat completions neověřil). Obrázek pak
  tiše vyjde 1408×768.
- **Návrh:** „`image` bez obrázku: když je `refusal` neprázdné nebo
  `finish_reason: content_filter` → `content`. Jinak `transient` a po
  vyčerpání `retry` `content` se zprávou ‚model nevrátil obrázek‘.“ Dále:
  „Po uložení framework porovná poměr stran z hlavičky souboru s
  `aspect_ratio`. Odchylka > 2 % = chyba `config` (‚model nepodporuje
  aspect_ratio‘).“

### D11. `parallel`: zrušení běžícího kroku, `budget_usd` a `timeout` na `parallel`/`call`
- **Kde:** `scenario.md:171-175`, `scenario.md:361-362`, `run-record.md:122` vs. `DESIGN.md:229`.
- **Co:** Zrušený krok, který už běžel, má `step_started`, ale spec pro něj
  zná jen `step_skipped` s `cancelled`. Nevíme, jestli se jeho cena počítá a
  jestli má `step_finished`. Tabulka povoluje `budget_usd`/`timeout` na
  `parallel` a `call`, ale význam je popsaný jen pro kroky s modelem.
  Nejasné je i to, co dostanou kroky, na které běh nedošel (za selháním,
  uvnitř přeskočeného `parallel`), vzhledem k §5.1 bod 5.
- **Návrh:** „Rozběhnutý krok zrušený kvůli jiné větvi dostane
  `step_finished` se `status: cancelled` a cenou dosavadních volání.
  Nerozběhnutý dostane `step_skipped` s `cancelled`. `budget_usd`/`timeout`
  na `parallel` a `call` = součet všech kroků uvnitř / doba od startu do
  konce posledního. Kroky uvnitř přeskočeného `parallel`/`switch` dostanou
  každý `step_skipped` se stejným důvodem. Kroky za selháním běhu se
  nezapisují, summary uvádí ‚běh skončil v kroku X‘.“

### D12. Musí být `default` úplný?
- **Kde:** `scenario.md:165` (příklad `default: { on_brand: 0 }`), `scenario.md:294`.
- **Co:** „Tvar musí odpovídat výstupu kroku.“ Nevíme, jestli částečný
  `default` stačí, když se čte jen `on_brand`, a jestli `jev` default musí
  mít i `details`. Když ne, `steps.x.details.on_brand` po přeskočení skončí
  runtime chybou.
- **Návrh:** „`default` musí obsahovat všechna pole výstupu kroku (u `jev`
  všechny otázky; `details` se doplní jako `{}` automaticky). Chybějící pole
  = chyba `validate`.“

### D13. `switch`/`when` nad `null` a nad špatným typem; platí `on_error` na chybu podmínky?
- **Kde:** `scenario.md:160`, `scenario.md:387`, `scenario.md:598`, `scenario.md:631`.
- **Co:** `value` „musí být `string`“, ale spec neříká, co se stane za běhu
  s `null` (typicky `default: { druh: null }` u `jev`): chyba `expression`,
  nebo větev `default`? Stejně nejasné je, jestli `on_error: continue` kroku
  pokrývá i chybu jeho vlastního `when`.
- **Návrh:** „`switch` s `value` `null` nebo jiného typu než `string` =
  chyba `expression` (ne větev `default`). Když je typ známý předem, chyba
  `validate`. Chyba ve `when` kroku je chybou kroku a `on_error` ji
  pokrývá.“ Volitelně: `validate` ověří, že klíče `cases` ⊆ klíče `criteria`,
  když `value` je `choice` z `jev`.

### D14. Není úplný seznam polí, kde se vyhodnocují šablony
- **Kde:** `scenario.md:494-500`.
- **Co:** „Všude jinde, kde je hodnota“ + výčet. Chybí
  `jev.questions.<q>.instructions`, `criteria`, `image.aspect_ratio`,
  `task.max_turns`, klíče `cases`. Autor netuší, jestli
  `instructions: "Sedí to na {{ inputs.znacka }}?"` vloží hodnotu, nebo
  pošle doslovný text.
- **Návrh:** Nahradit uzavřeným seznamem: „Šablona se vyhodnocuje **jen**
  v: `ask.prompt`, `task.prompt`, `image.prompt`, `jev.state`,
  `jev.questions.*.instructions`, `jev.questions.*.criteria` (hodnoty),
  `fail`, hodnotách `output`, `call.inputs`, `dedupe_key`. `{{` kdekoli jinde
  = chyba `validate`.“

### D15. Výrazy: `*` nad textem obchází limit délky, `in` napříč typy
- **Kde:** `scenario.md:553-556`, `scenario.md:620-624`; spike (c) `REPORT.md:27` (`"a"*10**9` → 1 GB za 0,33 s), `REPORT.md:201-202`.
- **Co:** Spec vyjmenuje aritmetiku `+ - * / %` a výslovně povolí jen
  `+` pro texty. Nevíme, jestli `"a" * 999999999` (24 znaků, projde limitem
  2000) je chyba. `3 in ["3"]`: je to porovnání napříč typy (chyba), nebo
  `false`? `in` nad objektem (klíč) prototyp umí, spec ho nezmiňuje.
- **Návrh:** „`*`, `/`, `%`, `-` jen číslo s číslem. `+` číslo+číslo,
  text+text, seznam+seznam. Výsledný text nebo seznam delší než 100 000
  znaků/prvků = chyba `expression`. `x in y`: `y` je seznam (prvky musí mít
  typ `x`, jinak chyba), text (`x` text) nebo objekt (`x` text = klíč).“

### D16. MCP: timeouty, `mode="legacy"`, chyby handshaku, `stderr` a start serveru ve spec chybí
- **Kde:** `config.md:139-171`, `mcp.schema.json:14-41`, `scenario.md:255-256`, `run-record.md` (žádná událost MCP) vs. `DESIGN.md:325-335`, `DESIGN.md:357`.
- **Co:** §5.8 chce timeouty „vždy výslovně“ (handshake i `call_tool`),
  `mode="legacy"`, `timed out` = třída `timeout`, selhání handshaku =
  `config`/`transient` a `stderr` serverů v záznamu. Spec nemá pole pro
  timeout ani událost pro start/stderr. Říká jen, že chyba nástroje jde
  modelu, což pro timeout neplatí. Nevíme ani, jestli server startuje per
  běh (§5.8), nebo per krok (`agent.md:83` „připojí se“). Pro `parallel` to
  znamená buď sdílený, nebo oddělený stav serveru.
- **Návrh:** Do `mcp.yaml` přidat `timeouts: {handshake: 10s, call: 60s}`
  (volitelné, s těmito výchozími hodnotami). Do `scenario.md:255` doplnit:
  „`isError` → modelu, krok pokračuje. Timeout volání nástroje → krok selže,
  třída `timeout` (nástroj mohl proběhnout, viz D7). Selhání handshaku →
  `transient` (síť, 5xx) nebo `config` (proces neběží, 401).“ Do
  `run-record.md` přidat událost `mcp_server` (`server`, `action:
  started|stopped|failed`, `duration_s`, `stderr_file:
  mcp/<server>.stderr.log`) a větu „stdio servery startují jednou za běh při
  prvním `task`, který je potřebuje, a sdílí je i větve `parallel`“.

### D17. Validace argumentů na klientovi a normalizace jmen nástrojů ve spec chybí
- **Kde:** `agent.md:105-107`, `run-record.md:152-161` vs. `DESIGN.md:336-343`.
- **Co:** §5.8 dělá validaci argumentů proti **původnímu** schématu povinnou
  (Gemini posílá tiše špatné argumenty). Spec ji nezmiňuje a `tool_call` pro
  ni nemá stav. Jméno `server__tool` má po normalizaci nejvýš 64 znaků
  `[a-zA-Z0-9_-]`, takže dva nástroje mohou dostat stejné jméno a spec
  neříká, co pak.
- **Návrh:** Do `agent.md` za `:107` doplnit: „Argumenty od modelu se před
  voláním validují proti schématu nástroje ze serveru. Když nesedí, nástroj
  se nespustí a model dostane chybu validace jako výsledek nástroje (tah se
  počítá).“ V `tool_call` doplnit `invalid_args: true`. Do `validate`
  doplnit: „dva povolené nástroje se stejným jménem po normalizaci = chyba
  `config`“.

### D18. Obrázky z nástrojů, `reasoning_details` a base64 v `request.json`
- **Kde:** `run-record.md:22-24`, `run-record.md:49-51`, `run-record.md:59-65` vs. `DESIGN.md:285-286`, `DESIGN.md:309-310`, `DESIGN.md:344-346`.
- **Co:** Spec nahrazuje base64 a `reasoning_details` jen v `response.json`.
  `request.json` („jen tělo“) dalšího tahu ale obsahuje (a) vrácené
  `reasoning_details` (~1,4 MB) a (b) obrázek z nástroje, který §5.8 posílá
  jako data URL v následné user zprávě. Totéž platí pro `calls/NN.tool.json`.
  Spec neurčuje, kam se obrázek z nástroje uloží, ani že jde v user zprávě,
  ne v tool zprávě.
- **Návrh:** „Nahrazení base64 a `reasoning_details` platí pro **všechny**
  soubory v `calls/` včetně `request.json` a `NN.tool.json`. Obrázek
  z výsledku nástroje se uloží jako `steps/<nn>-<id>/tool-<NN>-<k>.png`. Do
  modelu jde v user zprávě hned za tool zprávou. V tool zprávě je jen text
  ‚obrázek v další zprávě: tool-<NN>-<k>.png‘.“

### D19. Prostředí stdio serveru: spec slibuje něco, co SDK nedělá
- **Kde:** `config.md:167` vs. `DESIGN.md:355-357`; spike (d) `REPORT.md:94-96`.
- **Co:** Spec: server dostane „nic jiného než tyto proměnné a `PATH`“.
  Oficiální SDK (D4) přidá vždy `HOME, LOGNAME, PATH, SHELL, TERM, USER`.
  `npx` bez `HOME` navíc nemá kde mít cache.
- **Návrh:** `config.md:167` přepsat: „Server dostane proměnné `HOME`,
  `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER` (výchozí sada `mcp` SDK) a
  proměnné z `env`. Nic jiného.“ Do `mcp.schema.json` do `env.propertyNames`
  přidat `not: {enum: [PATH, HOME, LD_PRELOAD, LD_LIBRARY_PATH, NODE_OPTIONS,
  PYTHONPATH]}` (schéma je teď pustí).

### D20. Callback, který se nepodaří doručit
- **Kde:** `run-record.md:210-217`, `run-record.md:19` vs. `DESIGN.md:119-120`, `DESIGN.md:231-232`.
- **Co:** Tři pokusy, a potom nic definováno není: změní se stav běhu? Kde
  je to vidět? `callback_sent` má být „poslední řádek souboru“, ale pokusů
  jsou až tři řádky.
- **Návrh:** „Každý pokus = jedna událost `callback_sent`. Po třetím
  neúspěchu `callback_failed` (poslední řádek). Stav běhu se nemění,
  `callback.json` zůstává. Při spuštění CLI a v `summary.md` se zobrazí
  ‚callback nedoručen‘. Obnovu řeší časový limit v n8n (§5.1 bod 7).“

### D21. `validate` proti `/models`: potřeba sítě a chybějící kontrola schopností aliasu
- **Kde:** `scenario.md:738-739`, `scenario.md:723` vs. `DESIGN.md:276-278`, `DESIGN.md:295-296`.
- **Co:** `validate` „před každým během“ volá `GET /models`. Nevíme, jaká je
  třída chyby, když síť nejde, ani jak to jde dohromady s konformačními
  testy „bez sítě“. Kontroluje se jen, že obrazový alias umí obrázky, ne že
  alias agenta v `task` umí `tools` a u `schema` `structured_outputs`.
  Formulace „aliasy existují v `/models`“ neplatí, v `/models` jsou id.
- **Návrh:** „`validate` ověří `models.<alias>.id` proti `/models`
  (výsledek se cachuje na 24 h ve `<runs>/_models.json`). Bez sítě a bez
  cache → `transient`. Alias agenta použitého v `task` musí mít v
  `supported_parameters` `tools`, a když krok má `schema`, i
  `structured_outputs` nebo `tools`. Jinak `config`. S `base_url` falešného
  poskytovatele se kontroluje proti jeho `/models`.“

### D22. `call`: soubor předat nejde, typ vstupu za běhu
- **Kde:** `scenario.md:82`, `scenario.md:108`, `scenario.md:421`, `scenario.schema.json:50`.
- **Co:** Volaný scénář umí vrátit `file`, ale `inputs` typ `file` nemají
  (ověřeno: schéma ho odmítne). Obrázek z jednoho scénáře tak nejde předat
  jinému. Když typ hodnoty za `call.inputs` není předem známý, spec neříká
  třídu chyby za běhu.
- **Návrh:** Povolit `type: file` u `inputs` (jen pro `call`; z webhooku
  a CLI chyba `config`). Doplnit: „Typ vstupu, který nejde ověřit předem, se
  kontroluje při `call`; nesoulad = `expression`.“

### D23. `schema: string` / `schema: [string]` projde schématem, ale výstup nemá pole
- **Kde:** `scenario.schema.json:58-70`, `scenario.md:129-130`, `scenario.md:209-219`.
- **Co:** Tvar `shape` povoluje i skalár a seznam na kořeni (ověřeno: obojí
  `ok`). Výstup je ale definovaný jen jako „pole ze schématu“
  (`steps.<id>.<pole>`) a strict JSON schema u poskytovatelů chce jako
  kořen objekt.
- **Návrh:** V `scenario.schema.json` dát `ask.schema` a `task.schema` jako
  `{"type": "object", "minProperties": 1, …}` (kořen jen mapa). Do
  `scenario.md:216` doplnit „kořen `schema` je vždy mapa“.

---

## DROBNÉ

### M1. `ig-post.yaml`: komentáře neodpovídají krokům a chybí vysvětlení prahů
- **Kde:** `ig-post.yaml:23-82`, `:46`, `:72`; `run-record.md:243-252`.
- **Co:** Komentáře čísluje 1–7, kroků je 8 (`stop_obrazek` číslo nemá).
  `summary.md` čísluje 1–8, takže začátečník čísla nespáruje. Prahy `0.7`
  a `0.5` a pojem `noul` nejsou vysvětlené.
- **Návrh:** Číslovat 1–8 shodně se `summary.md` (`# 6. Když prompt porušuje
  pravidla, běh skončí.`). K `kontrola` přidat `# noul = míra „ano“ od 0 do
  1; 0.5 = Jev si není jistý`. K `:72` přidat `# přísnější práh než u tónu:
  raději zastavit`.

### M2. Slovo `prompt` má ve `foto_prompt` tři významy
- **Kde:** `ig-post.yaml:53-57`, `:62`, `:79`.
- **Co:** `ask.prompt` (zadání), výstupní pole `prompt` a `image.prompt`.
  Pak `steps.foto_prompt.prompt` čte jako tautologie.
- **Návrh:** Výstupní pole přejmenovat na `popis_fotky`:
  `schema: { popis_fotky: string }`, `prompt: "{{ steps.foto_prompt.popis_fotky }}"`.

### M3. `limits.max_turns` je povinné i u agentů, kteří se používají jen v `ask`
- **Kde:** `agent.schema.json:29`, `agent.md:45`, `copywriter.md:6-8`, `photographer.md:6-8`.
- **Co:** `max_turns: 1` u copywritera nic neznamená (`ask` ho ignoruje),
  a začátečník to čte jako nastavení.
- **Návrh:** `max_turns` povinné jen když agent má `mcp` (schéma:
  `if: {required: [mcp]} then: {properties: {limits: {required: [max_turns]}}}`).
  `validate`: `task` s agentem bez `max_turns` = chyba `config`
  (§5.1 bod 6 zůstává splněn). Z ukázek `max_turns: 1` odstranit.

### M4. `outputs: {}` nejde splnit
- **Kde:** `scenario.schema.json:18-30`, `scenario.schema.json:340-344`, `scenario.md:483-485`.
- **Co:** Schéma povolí `outputs: {}`. Scénář s `outputs` pak musí mít
  `output`, ale `output` chce aspoň jeden klíč.
- **Návrh:** K `outputs` přidat `"minProperties": 1`.

### M5. `mcp.yaml`: jen `https://`, SSE nejde nastavit
- **Kde:** `mcp.schema.json:37`, `config.md:141-144`, `config.md:168` vs. `DESIGN.md:325`.
- **Co:** Místní HTTP server (sidecar v kontejneru, `http://127.0.0.1`,
  jak ho používal spike (d)) nejde zapsat. SSE, které §5.8 jmenuje, nemá pole.
- **Návrh:** `url` pattern `^(https://|http://(127\.0\.0\.1|localhost)[:/])`.
  Přidat `transport: streamable-http|sse` (výchozí `streamable-http`), nebo
  do `config.md` výslovně napsat „SSE ve v1 není“.

### M6. `config.yaml`: `base_url` na libovolný host a jedna proměnná pro víc účelů
- **Kde:** `config.schema.json:17`, `config.schema.json:79-90`, `config.md:78`.
- **Co:** `base_url` je „jen pro konformační testy“, ale schéma pustí
  `http://evil.example.com`, kam by odešel klíč OpenRouteru. Tatáž
  proměnná jako `webhook.token_env` i `openrouter.api_key_env` projde (ověřeno),
  takže n8n by dostalo klíč OpenRouteru.
- **Návrh:** `base_url` pattern
  `^(https://openrouter\.ai/|http://(127\.0\.0\.1|localhost)[:/])`.
  `validate`: dvě různá `*_env` pole se stejnou hodnotou = chyba `config`.

### M7. Složka `runs/` nemá místo v konfiguraci
- **Kde:** `run-record.md:42`.
- **Co:** „složka z konfigurace serveru“, ale `config.yaml` takové pole
  nemá a jiná konfigurace serveru neexistuje.
- **Návrh:** Do `config.yaml` přidat `runs_dir` (výchozí `./runs`, na
  Modalu cesta k Volume), nebo psát „CLI přepínač `--runs-dir`, výchozí `./runs`“.

### M8. Čísla ve výrazech: `int`, `round`, NaN, `integer` vs. `number`, formát v textu
- **Kde:** `scenario.md:521-522`, `scenario.md:583-584`, `scenario.md:596`, `scenario.md:606-608`, `scenario.md:622-624`.
- **Co:** `int(2.7)`: 2, nebo chyba? `round(2.5)` = `3`, nebo `3.0`? (a
  `str(4 / 2)` = `"2.0"`?) `float("nan")` a `float("inf")` Python přijme,
  výsledek ale není platný JSON. Výsledek `/` (`2.0`) do vstupu typu
  `integer`? Formát čísla v textu (`0.1 + 0.2`) není určen. Limit hloubky
  „před čtením výrazu“ nejde pro operátory změřit bez parseru.
- **Návrh:** „`int(x)` z čísla uřízne desetinnou část, z textu jen celé
  číslo. `round(x)` bez `n` dává celé číslo. `nan`/`inf` = chyba
  `expression`. Číslo s nulovou desetinnou částí se přijme jako `integer`.
  Číslo v textu = nejkratší zápis, který se přečte zpět stejně (`0.30000000000000004`).
  Délka se kontroluje před parserem, hloubka nad AST před vyhodnocením.“

### M9. `tools` pro server, který agent nemá v `mcp`; podsložky
- **Kde:** `agent.md:43`, `scenario.md:249-250`; `agent.md:3`, `scenario.md:3`.
- **Co:** Agent s `tools: {github: [...]}` a bez `mcp` projde schématem
  (ověřeno) a spec neříká, co to znamená. Nevíme ani, jestli se čtou
  podsložky `agents/` a `scenarios/` (dva `copywriter.md` v různých
  složkách).
- **Návrh:** „Klíč `tools` mimo `mcp` = chyba `config`.“ „Čtou se jen soubory
  přímo ve složce, podsložky jsou chyba `config`.“

### M10. Odchylky od DESIGN, které nejsou v OPEN-QUESTIONS
- **Kde:** `scenario.md:169-178` vs. `DESIGN.md:102-103`; `scenario.md:631` vs. `DESIGN.md:269-270`.
- **Co:** D1d dává `retry`, `timeout`, `on_error` „libovolnému kroku“. Spec
  je u `parallel`, `set`, `switch`, `fail` a `output` zakazuje. §5.4 říká,
  že porovnání napříč typy je chyba **validace**, spec ho u neznámých typů
  přesouvá na běh (`expression`). Obojí je rozumné, ale podle `CLAUDE.md` to
  potřebuje souhlas uživatele.
- **Návrh:** Přidat do OPEN-QUESTIONS otázky 12 a 13 s těmito formulacemi a
  doporučením „ponechat“.

### M11. `CLAUDE.md` neodkazuje na spec; DESIGN ve větvi je zastaralý
- **Kde:** `CLAUDE.md:6-9`; `docs/DESIGN.md` ve větvi `phase-1-spec` (bez §5.8).
- **Co:** Workeři Fáze 2 čtou jen DESIGN. Spec cituje „§“ z kopie, která
  §5.8 nemá.
- **Návrh:** Do `CLAUDE.md` přidat: „Po schválení je závazná i `docs/spec/`
  (formáty v1). Rozpor spec × DESIGN hlas koordinátorovi.“ Kopii
  `docs/DESIGN.md` ve větvi sjednotit s hlavním checkoutem.

### M12. Číslo `<nn>` složky kroku není stálé
- **Kde:** `run-record.md:45-48`, `run-record.md:117-124` vs. `DESIGN.md:229`.
- **Co:** `<nn>` se v `parallel` přiděluje „podle skutečného startu“. Stejný
  scénář pak má při každém běhu jiné číslování složek a rozdíl dvou běhů
  (R2) se špatně čte.
- **Návrh:** „`<nn>` = pořadí kroku v souboru (hloubkově, včetně větví),
  pevné pro scénář. Skutečné pořadí startu je vidět z `ts` v `events.jsonl`.“

---

## Stav oprav

Opraveno 2026-09-25 (worker `task_06392950748f`) podle návrhů výše; kde
koordinátor rozhodl jinak, platí jeho rozhodnutí. Ověřeno
`uv run docs/spec/tools/check.py` (YAML 1.2 loader + jsonschema) na všech
ukázkách a úryvcích: agent 4×, config 2×, mcp 2×, scénář 13×, skill 2×,
**0 chyb**; nová pravidla schémat ověřena 9 záměrně chybnými případy (vše
odmítnuto).

| Nález | Stav | Poznámka |
|---|---|---|
| B1 skilly | hotovo | `task`: seznam + `load_skill` (`_skills` v záznamu), `ask`: celé; `skill.md`, `skill.schema.json`, ukázka `skills/thtd-hlas`; OPEN-QUESTIONS 11 |
| B2 `tools` povinné | hotovo | `dependentRequired`, klíče `tools` = `mcp`, `--dry-run` vypíše nabídku; OQ 6 vyřešena podle §5.8 |
| B3 kaskáda | hotovo | `models.<alias>.structured_output`, `_submit_output`, přechod o úroveň níž po `schema` |
| B4 dedupe | hotovo | `<runs>/_dedupe/<sha256>.json`, atomicky; OQ 12 |
| B5 webhook | hotovo | nový `webhook.md` (`POST /runs`, 202/200/401/422); callback vždy od `run_id` |
| B6 YAML 1.2 | hotovo | text ve všech spec souborech; `tools/check.py`; `cases.propertyNames`; CHANGELOG: ověření stejným loaderem |
| D1 oprávnění MCP | odchylka (koordinátor) | vlastník v `mcp.yaml`: povinné `agents`, navíc volitelné `scenarios` a `tools` |
| D2 obejití schválení | odchylka (koordinátor) | `callable` ve scénáři ano; místo `scenarios` v agentovi je `scenarios` u serveru v `mcp.yaml` (agenty píší ostatní) |
| D3 typ `file` | hotovo | jen z `image`/nástroje, cesta uvnitř běhu, `null` z `default`, selhání nahrání = `transient` |
| D4 kořen filesystemu | hotovo | `{run_dir}` v `args`, ukázka `{run_dir}/work` |
| D5 uhodnutelná URL | hotovo | `<run_id>-<32 hex>/<jméno>` pro všechny soubory; `run_started.storage_prefix` |
| D6 tajné ve výsledcích | hotovo | nahrazení `<tajné: JMENO>` v záznamu i callbacku |
| D7 dedupe `started` | hotovo | `started` před 1. voláním nástroje; `started` bez `succeeded` = `config` „ověř ručně" |
| D8 rozpočet | hotovo | kontrola před voláním, překročení o 1 volání/větev, chybějící cena → `transient` → `budget`; `run_finished.image_duration_s`, samostatný časový limit obrázků ve v1 není |
| D9 `max_turns` × `retry` | hotovo | opakování se do `max_turns` nepočítá |
| D10 `image` bez obrázku | hotovo | `refusal`/`content_filter` → `content`, jinak `transient` → `content`; kontrola poměru stran ±2 % |
| D11 `parallel` zrušení | hotovo | `step_finished.status: cancelled`; `budget_usd`/`timeout` na `parallel`/`call` = součet / celá doba |
| D12 úplný `default` | hotovo | všechna pole, `details` se doplní |
| D13 `switch` nad `null` | hotovo | `expression`; chyba ve `when` pokrývá `on_error`; `cases` ⊆ `criteria` |
| D14 pole se šablonami | hotovo | uzavřený seznam, `{{` jinde = `validate` |
| D15 `*`, `in` | hotovo | typy operátorů, výsledek max 100 000, `in` nad seznamem/textem/objektem |
| D16 MCP timeouty | hotovo | `timeouts` v `mcp.yaml`, událost `mcp_server`, `stderr` do `mcp/`, start 1× za běh; `mode="legacy"` je implementační detail z DESIGN §5.8 |
| D17 validace argumentů | hotovo | validace proti původnímu schématu, `invalid_args`, kolize jmen po normalizaci = `config` |
| D18 obrázky z nástrojů | hotovo | nahrazení base64/`reasoning_details` ve všech souborech `calls/`; `tool-<NN>-<k>.png`, user zpráva |
| D19 prostředí stdio | hotovo | 6 proměnných SDK + `env`; zakázaná jména ve schématu |
| D20 nedoručený callback | hotovo | `callback_sent` za pokus, `callback_failed`, stav běhu beze změny |
| D21 `validate` × `/models` | hotovo | cache 24 h `_models.json`, bez sítě `transient`, kontrola `tools`/`structured_outputs` |
| D22 `file` přes `call` | hotovo | `inputs.type: file` jen pro `call`; nesoulad za běhu = `expression` |
| D23 kořen `schema` | hotovo | `schema_root` = mapa |
| M1 komentáře ig-post | hotovo | 1–8 shodně se summary, vysvětlení `noul` a prahů |
| M2 `popis_fotky` | hotovo | ukázka, spec, agent photographer |
| M3 `max_turns` | hotovo | povinné jen s `mcp`; `task` bez něj = `config`; z ukázek odstraněno |
| M4 `outputs: {}` | hotovo | `minProperties: 1` |
| M5 HTTP/SSE | hotovo | `url` i `http://127.0.0.1`/`localhost`; `transport: streamable-http|sse` |
| M6 `base_url`, sdílené env | hotovo | pattern; stejná hodnota ve dvou `_env` = `config` |
| M7 `runs_dir` | hotovo | pole v `config.yaml` (výchozí `./runs`) |
| M8 čísla | hotovo | `int`, `round` bez `n` celé, `nan`/`inf`, `2.0` jako `integer`, zápis v textu, hloubka nad AST |
| M9 `tools` mimo `mcp`, podsložky | hotovo | obojí chyba `config` |
| M10 odchylky od DESIGN | hotovo | OPEN-QUESTIONS **13 a 14** (12 je dedupe) |
| M11 CLAUDE.md, DESIGN | částečně (koordinátor) | věta do `CLAUDE.md` přidána; kopie `docs/DESIGN.md` ve větvi se nesjednocuje — udělá to sloučení s `main` |
| M12 `<nn>` | hotovo | pořadí v souboru, hloubkově |
