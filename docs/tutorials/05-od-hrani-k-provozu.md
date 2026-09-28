# Díl 5 — Od hraní k provozu

Příkazy spouštěj z `examples/tutorial` (z kořene klonu: `cd examples/tutorial`).

**Čas:** asi 20 minut · **Útrata:** 0 USD (všechno s `--fake` nebo bez
volání modelu)
**Co budeš umět:** vyměnit model jedním řádkem, udělat ze scénáře zlatý
test, číst záznam běhu do hloubky, poslat výsledek do n8n
(`--callback-url`) a vědět, co se ti při vylepšování frameworku nikdy
nerozbije.

Předpoklad: díly 1–4.

---

## Krok 1 — aliasy modelů: výměna = jeden řádek

Tvoji agenti znají jen aliasy (`chytry`, `rychly`, `gemini-image`). Co
se pod nimi skrývá, je v `workflows/config.yaml`:

```
models:
  chytry:       { id: anthropic/claude-haiku-4.5 }
  rychly:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }
```

Tenhle soubor mění **jen vlastník** — ty v roli správce, ne jako autor
scénáře, a vědomě: změna aliasu změní model **všem** agentům, kteří ho
používají. Proto si výměnu nejdřív vyzkoušíme na kopii:

```bash
rm -rf /tmp/pokus && mkdir -p /tmp/pokus && cp -r workflows /tmp/pokus/
```

V `/tmp/pokus/workflows/config.yaml` udělej v řádku `chytry` překlep, který
se dělá nejčastěji — `anthropic/claude-haiku-4-5` (pomlčka místo tečky):

```bash
agencast validate /tmp/pokus/workflows/scenarios/tutorial-01-nazvy.yaml
```

```
config: config.yaml: models.chytry.id 'anthropic/claude-haiku-4-5' není v GET /models — překlep? (např. claude-haiku-4.5, ne -4-5)
```

`validate` se ptá OpenRouteru na seznam modelů, takže neexistující model
nepustí dál. Teď řádek přepiš na jiný skutečný model:

```
  chytry:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
```

```bash
agencast validate /tmp/pokus/workflows/scenarios/tutorial-01-nazvy.yaml
agencast run /tmp/pokus/workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="zmrzlina" --dry-run
```

```
v pořádku: tutorial-01-nazvy (2 kroky)
…
| 1 | navrh | ask |  | agent tutorial-pojmenovavac → chytry (google/gemini-3.5-flash-lite); text | 0.01 USD, 2m |
```

Agent ani scénář se nezměnily ani o písmeno. Co je
`structured_output: tool_wrapper`: tenhle model neumí spolehlivě nativní
JSON Schema, tak mu framework JSON předává jinou cestou (viz „kaskáda"
v dílu 2). Kterou cestu model potřebuje, zjistí vlastník zkouškou —
nastavuje se jednou u aliasu, ne v každém scénáři.

Která verze modelu v kterém běhu opravdu běžela, je vždy v záznamu (krok 3).

---

## Krok 2 — zlaté testy

Od dílu 1 píšeš ke každému scénáři fixturu do `../../framework/tests/golden/`.
Tady je proč:

> **Každý soubor ve `workflows/` je test frameworku.** Každý agent musí
> projít kontrolou a každý scénář musí doběhnout s falešným
> poskytovatelem. Když k němu existuje fixtura
> `../../framework/tests/golden/<jméno scénáře>.yaml`, běh musí skončit
> **úspěchem**; bez fixtury stačí úspěch nebo záměrný `fail`.

Až někdo (typicky agent-worker) framework vylepší, tyhle testy spustí.
Když tvůj scénář přestane fungovat, uvidí to **on**, dřív než ty.

```bash
cd ../../framework && uv run pytest
```

```
......................................................................   [100%]
286 passed in 3.09s
```

(Víc řádků teček zkracuji.) Jen tvoje soubory — jsi pořád ve složce
`framework/` repozitáře:

```bash
uv run pytest -k tutorial -v
```

```
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-01-cviceni] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-01-nazvy] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-02-cviceni] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-02-nazev-a-slogan] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-03-cviceni] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-03-rozhodovani] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-03-vyrazy] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-04-cviceni] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-04-paralelne] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-05-cviceni] PASSED
tests/test_golden.py::test_workflow_agent_valid[tutorial-ilustrator] PASSED
tests/test_golden.py::test_workflow_agent_valid[tutorial-pojmenovavac] PASSED
tests/test_golden.py::test_workflow_agent_valid[tutorial-sloganista] PASSED
====================== 13 passed, 273 deselected in 0.23s ======================
```

(`-k tutorial` vybere testy, v jejichž jméně je „tutorial"; ukazuji jen
řádky s výsledky.) Zpátky do projektu tutoriálu: `cd ../examples/tutorial`.

### Jak test vypadá, když neprojde

Fixtura je smlouva stejně jako scénář: když v ní odpověď nesedí na
`schema`, test selže. Tady je fixtura s polem, které `schema` kroku
`navrh` nezná (`nazvy_navic`):

```yaml
navrh:
  - json:
      nazvy_navic: "tohle pole ve schema není"
      nazev: "Ovena"
```

```
FAILED tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-05-cviceni]
…
E           AssertionError: {'class': 'schema', 'step': 'navrh', 'message': "odpověď nesedí na schema: neznámé pole 'nazvy_navic' (překlep?) (kořen)"}
E           assert 'failed' == 'succeeded'
```

Čti řádek `AssertionError`: je v něm přesně to, co by bylo v `summary.md`
— třída, krok, hláška.

### Jak psát fixturu — shrnutí

| Krok | Ve fixtuře | Když krok ve fixtuře chybí |
|---|---|---|
| `ask` bez `schema` | `text: "…"` | „Falešná odpověď." |
| `ask` se `schema` | `json: {pole: hodnota}` — přesně pole ze `schema` | hodnoty vyrobené podle schématu |
| `jev` | `answers: {otázka: hodnota}` | `noul` 0,5, `choice` první možnost, `score` 0 |
| `image` | nic (nebo `image: {width: …, height: …}`) | šedé PNG v poměru `aspect_ratio` |
| `set`, `switch`, `fail`, `output` | nic | — (nevolají model) |

- Klíč je `id` kroku, hodnota je **seznam** odpovědí: 1. volání vezme
  první, 2. druhou…, poslední se opakuje.
- Na simulaci chyb (díl 4): `status: 429`, `refusal: "…"`,
  `finish_reason: error`, `sleep: 5`. Takové fixtury **nedávej**
  do `golden/` — zlatý test s fixturou čeká úspěch. Patří do `/tmp`.
- Fixtura má projít cestou, na které ti záleží nejvíc (u `switch` si
  vyber větev — viz cvičení).
- Testy používají vlastní testovací `config.yaml` se stejnými aliasy
  (`chytry`, `rychly`, `gemini-image`), ne tvůj — nic nestojí a nepotřebují
  klíč.

---

## Krok 3 — záznam běhu do hloubky

Vezmi ostrý běh z dílu 3 (`runs/20260925-151536-tutorial-03-rozhodovani-b547`).

### `events.jsonl`

Jedna událost na řádek, stroj ho čte snadno, člověk s trochou pomoci.
Typy událostí v tomto běhu po řadě:

```
run_started
step_started navrh
model_call navrh
step_finished navrh
step_started kontrola
jev_call kontrola
step_finished kontrola
step_skipped stop
step_started podle_tonu
step_skipped slogan_vazny
step_skipped neznamy_ton
step_started slogan_hravy
model_call slogan_hravy
step_finished slogan_hravy
step_finished podle_tonu
step_started vysledek
step_finished vysledek
step_started out
step_finished out
run_finished
```

(Výpis dělá tenhle příkaz:
`python3 -c "import json;[print(json.loads(l)['type'], json.loads(l).get('step','')) for l in open('runs/20260925-151536-tutorial-03-rozhodovani-b547/events.jsonl')]"`.)

Nejdůležitější řádky:

**`run_started`** — s čím běh začal. Hlavně `models`: na co se aliasy
**v tomhle běhu** přeložily. Když vlastník za měsíc alias změní, pořád
víš, co běželo tehdy.

```
{"ts":"2026-09-25T15:15:36.894Z","type":"run_started","run_id":"20260925-151536-tutorial-03-rozhodovani-b547","scenario":"tutorial-03-rozhodovani","scenario_version":1,"request_key":null,"inputs":{"produkt":"veganská zmrzlina z ovesného mléka"},"models":{"chytry":"anthropic/claude-haiku-4.5","rychly":"google/gemini-3.5-flash-lite","gemini-image":"google/gemini-3.1-flash-image"},"limits":{"run_budget_usd":1.0,"run_image_budget_usd":0.3,"run_timeout":"1h"},"framework_version":"0.1.0","storage_prefix":"20260925-151536-tutorial-03-rozhodovani-b547-c6bf8457c50ee002cb94481826201908"}
```

**`model_call`** — jedno volání modelu: pokus (`attempt`), kdo ho
obsloužil (`provider`), jak skončilo (`finish_reason`), kolik stálo
(`usage`) a kde je celý požadavek a odpověď. `generation_id` najdeš
i v logu OpenRouteru.

```
{"ts":"2026-09-25T15:15:40.532Z","type":"model_call","step":"navrh","attempt":1,"alias":"chytry","model":"anthropic/claude-haiku-4.5","structured_output":"native_schema","http_status":200,"response_model":"anthropic/claude-haiku-4.5","provider":"Amazon Bedrock","generation_id":"gen-1790349337-frPW3LQHMMPBX1MhYdjc","finish_reason":"stop","native_finish_reason":"end_turn","usage":{"input_tokens":264,"output_tokens":13,"cost_usd":0.000329},"duration_s":3.636,"request_file":"steps/01-navrh/calls/01.request.json","response_file":"steps/01-navrh/calls/01.response.json"}
```

**`jev_call`** — totéž pro Jev; `response_model` je datovaná verze Jevu.

```
{"ts":"2026-09-25T15:15:41.026Z","type":"jev_call","step":"kontrola","attempt":1,"model":"jev-1.13","http_status":200,"response_model":"typesafe/jev-1.13-20260917","usage":{"input_tokens":495,"output_tokens":71,"cost_usd":2.079e-05},"answers":{"zapamatovatelny":0.85,"ton":"hravy","originalita":0.64},"duration_s":0.492,"request_file":"steps/02-kontrola/calls/01.request.json","response_file":"steps/02-kontrola/calls/01.response.json"}
```

**`step_skipped`** — vždy s důvodem a s tím, jestli se použil `default`:

```
{"ts":"2026-09-25T15:15:41.028Z","type":"step_skipped","step":"slogan_vazny","kind":"ask","reason_code":"switch","reason":"switch: podle_tonu = \"hravy\"","default_used":true}
```

**`run_finished`** — výsledek, varování, součet spotřeby, z toho obrázky:

```
{"ts":"2026-09-25T15:15:42.806Z","type":"run_finished","status":"succeeded","error":null,"warnings":[],"duration_s":5.912,"usage":{"input_tokens":1010,"output_tokens":112,"cost_usd":0.00074079},"image_cost_usd":0.0,"image_duration_s":0.0}
```

Další typy, které jsi už viděl: `error` (díly 2 a 4: `class`,
`will_retry`), `image_saved`, `callback_sent` / `callback_failed` (krok 4).

### `steps/<nn>-<id>/calls/`

Každé volání API zvlášť: `01.request.json` (co odešlo) a
`01.response.json` (co přišlo). Opakování = `02.*`, `03.*`. Začátek
požadavku na Jev:

```bash
head -c 400 runs/20260925-151536-tutorial-03-rozhodovani-b547/steps/02-kontrola/calls/01.request.json
```

```
{
  "model": "jev-1.13",
  "state": "Produkt: veganská zmrzlina z ovesného mléka. Navržený název: Ověnka",
  "questions": {
    "zapamatovatelny": {
      "type": "noul",
      "instructions": "Je název snadno zapamatovatelný a dá se snadno vyslovit?"
    },
    "ton": {
      "type": "choice",
      "instructions": "Jaký tón má navržený název?",
      "criteria": {
        "hravy"
```

### Co v záznamu nikdy není

- **API klíč** ani hlavičky — `request.json` je jen tělo požadavku.
- **Obrázek v base64.** Odpověď obrazového modelu z dílu 4 by měla přes
  2 MB textu; v záznamu je místo ní odkaz na soubor. A šifrované
  „přemýšlení" modelu (`reasoning_details`, tady skoro 1 MB) je vynechané:

```bash
grep -o '"url": "<[^"]*"\|"reasoning_details": "<[^"]*"' runs/20260925-151755-tutorial-04-paralelne-8c76/steps/05-fotka/calls/01.response.json
```

```
"reasoning_details": "<vynecháno: reasoning_details, 1003920 B>"
"url": "<soubor: steps/05-fotka/image.png, 1149417 B>"
```

- **Tajné hodnoty kdekoli.** Hodnotu každé proměnné, na kterou odkazuje
  pole `*_env` v `config.yaml` (klíč OpenRouteru, tajemství callbacku…),
  framework před zápisem **každého** souboru záznamu nahradí textem
  `<tajné: JMÉNO>`. Vyzkoušíš to bezpečně s vymyšleným tajemstvím
  callbacku, které schválně pošleš jako vstup:

```bash
export CALLBACK_SECRET=tutorial-demo-tajemstvi
agencast run workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="zmrzlina tutorial-demo-tajemstvi" --fake ../../framework/tests/golden/tutorial-01-nazvy.yaml
```

  V `inputs.json`:

```
{
  "produkt": "zmrzlina <tajné: CALLBACK_SECRET>"
}
```

  v `prompt.md`:

```
Vymysli 3 názvy pro tento produkt: zmrzlina <tajné: CALLBACK_SECRET>. Každý na vlastní řádek.
```

  a v `summary.md` varování:

```
## Varování
- tajná hodnota CALLBACK_SECRET byla v záznamu nahrazena textem <tajné: CALLBACK_SECRET>
```

  Hodnota `tutorial-demo-tajemstvi` není v žádném souboru běhu. Pozor:
  maskuje se jen **záznam** — model tu hodnotu dostal. Tajnosti do
  promptů nepatří; scénář je ani nemá jak přečíst (vidí jen `inputs`
  a `steps`), leda bys je sám poslal jako vstup.

---

## Krok 4 — `--callback-url`: co dorazí do n8n

V provozu běh spouští n8n a výsledek čeká na své „resume" adrese.
Framework ho tam pošle `POST`em — **vždy**, při úspěchu i chybě. Z CLI
to vyzkoušíš přepínačem `--callback-url` (jen `https://`). Potřebuje
proměnnou z `callback.secret_env` (u nás `CALLBACK_SECRET`) — tou se
zpráva podepisuje. V ostrém provozu je v `.env`; na zkoušku stačí
`export` z kroku 3.

Abys viděl, co přesně n8n dostane, pustil jsem si na počítači malý
HTTPS server, který se tváří jako n8n a vypíše, co přišlo (skript je
[níž](#příloha-falešné-n8n)):

```bash
agencast run workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="veganská zmrzlina" --fake ../../framework/tests/golden/tutorial-01-nazvy.yaml --callback-url https://127.0.0.1:8443/webhook-waiting/4711 --request-key n8n-4711
```

```
běh 20260925-163820-tutorial-01-nazvy-26eb: úspěch · 0,0 s · 0,0001 USD
```

Falešné n8n vypsalo:

```
POST /webhook-waiting/4711
Content-Type: application/json
X-Run-Id: 20260925-163820-tutorial-01-nazvy-26eb
X-Signature: sha256=ccebf60ebacc5ff2160fcf507a3d68326c6959804b64c3d75a57538ee7ec38fc
{"run_id": "20260925-163820-tutorial-01-nazvy-26eb", "scenario": "tutorial-01-nazvy", "request_key": "n8n-4711", "status": "succeeded", "outputs": {"nazvy": "Ovesňák\nMrazík Oves\nZmrzlá Pláň"}, "error": null, "warnings": [], "cost_usd": 0.0001, "duration_s": 0.001, "report_url": "file:///…/outputs/20260925-163820-tutorial-01-nazvy-26eb-ed13aae87c48c49d241de2ab0633a6ab/report.html", "sent_at": "2026-09-25T16:38:20.885Z"}
```

Pole těla:

| Pole | Co v n8n uděláš |
|---|---|
| `status` | `succeeded` / `failed` — první větvení |
| `outputs` | přesně pole z `outputs` scénáře; při chybě `null` |
| `error` | `{class, step, message}` — podle `class` pozná n8n záměrný `fail` od poruchy (díl 3) |
| `warnings` | např. obrázek selhal s `on_error: continue` (díl 4) |
| `request_key` | co poslalo n8n (`--request-key`), aby spárovalo odpověď |
| `cost_usd`, `duration_s` | pro přehled útraty |
| `report_url` | adresa `report.html` v úložišti (od `maw` 0.2.0; souhrn běhu s prompty a odpověďmi, díl 7); `null`, jen když se report nepodařilo vytvořit nebo nahrát (pak je o tom varování) |

Typ `file` v `outputs` je **adresa** souboru v úložišti, ne soubor. U nás
`storage.type: local` → `file://…` cesta, se kterou Instagram nic
neudělá. Veřejná URL přijde s úložištěm R2 (mění vlastník v
`config.yaml`).

### Podpis

`X-Signature` = HMAC-SHA256 **přesných bajtů těla** s tajemstvím
z `CALLBACK_SECRET`. n8n si ho spočítá stejně a zprávě věří, jen když
sedí. Ověření (tělo uložené falešným n8n):

```bash
python3 -c "
import hmac, hashlib
telo = open('posledni-telo.json', 'rb').read()
print('sha256=' + hmac.new(b'tutorial-demo-tajemstvi', telo, hashlib.sha256).hexdigest())
"
```

```
sha256=db2349c82058367a50eaad251879583dc86da4ef9d5b919a62c11173aa6af601
```

Sedí s hlavičkou. Důležité pro n8n: počítej podpis ze **surového těla**,
ne z JSON, který n8n už rozebralo a znovu poskládalo — jiné mezery =
jiný podpis. (`callback.json` ve složce běhu je stejný obsah, ale hezky
odsazený, takže podpis z něj nevyjde.)

### Když n8n neodpovídá

```bash
agencast run workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="zmrzlina" --fake ../../framework/tests/golden/tutorial-01-nazvy.yaml --callback-url https://127.0.0.1:8444/webhook-waiting/4713
```

```
callback nedoručen
běh 20260925-152125-tutorial-01-nazvy-2fc8: úspěch · 0,0 s · 0,0001 USD
```

Trvalo to 35 s — tři pokusy s prodlevou 5 s a 30 s:

```
{"ts":"2026-09-25T15:21:25.104Z","type":"callback_sent","url":"https://127.0.0.1/webhook-waiting/4713","attempt":1,"http_status":null,"error":"ConnectError: All connection attempts failed"}
{"ts":"2026-09-25T15:21:30.113Z","type":"callback_sent","url":"https://127.0.0.1/webhook-waiting/4713","attempt":2,"http_status":null,"error":"ConnectError: All connection attempts failed"}
{"ts":"2026-09-25T15:22:00.146Z","type":"callback_sent","url":"https://127.0.0.1/webhook-waiting/4713","attempt":3,"http_status":null,"error":"ConnectError: All connection attempts failed"}
{"ts":"2026-09-25T15:22:00.146Z","type":"callback_failed","url":"https://127.0.0.1/webhook-waiting/4713","attempts":3,"error":"ConnectError: All connection attempts failed"}
```

Běh zůstává `úspěch` — nedoručený callback nezmění výsledek. Uvidíš to
v `summary.md` („**Callback nedoručen**") i v přehledu:

```bash
agencast runs list
```

```
20260925-152125-tutorial-01-nazvy-2fc8        succeeded                         0,0 s   0,0001 USD callback nedoručen
```

Aby n8n nečekalo věčně, nastav mu u čekajícího kroku časový limit.

---

## Krok 5 — co se ti nikdy nerozbije

Framework budou vylepšovat agenti-workeři. Pro tvoje soubory platí
pravidla kompatibility (`docs/DESIGN.md` §5.9):

1. **`version: 1` se jen rozšiřuje.** Přibýt smí nová volitelná pole
   a nové typy kroků. Přejmenovat, odstranit nebo změnit význam
   existujícího pole se nesmí. Nové pole má vždy výchozí hodnotu, která
   zachová dosavadní chování.
2. **Zlomová změna = `version: 2`.** Framework pak umí obě verze zároveň
   a příkaz `migrate` ti soubory převede a změny vypíše. Starý soubor
   běží dál, dokud ho nepřevedeš sám.
3. **Zlaté scénáře** — každý tvůj scénář, agent a skill ve `workflows/`
   musí po každé změně frameworku projít `validate` a doběhnout
   s `--fake` (krok 2). Tvoje fixtury tak hlídají, že se to dodržuje.
4. **Zastarávání s varováním.** Když se nějaká konstrukce přestane
   doporučovat, nejdřív uvidíš varování ve `validate` (běh jde dál);
   zmizet smí až v další verzi formátu.
5. **Neznámá verze = chyba**, nikdy tichý odhad.

V praxi: napiš `version: 1`, drž fixturu u každého scénáře a aktualizace
frameworku tě nemusí zajímat.

---

## Co přijde dál

Díly 1–5 vznikly s `maw` 0.1.0; díly 6 a 7 potřebují `maw` 0.2.1:

- **[Díl 6 — Agent s nástroji](06-agent-s-nastroji.md):** krok `task`
  (smyčka model ↔ nástroje MCP s limitem tahů), `mcp.yaml` z pohledu
  vlastníka, skilly přes `load_skill`, záznam volání nástrojů.
- **[Díl 7 — Skládání a provoz](07-skladani-a-provoz.md):** `call`
  (scénář volá scénář), `agencast serve` pro n8n (token, `request_key`,
  podepsaný callback), `report.html` a `dedupe_key` pro kroky, které smí
  proběhnout jen jednou.

Přehled všech dílů: [README.md](README.md).

---

## Co sis zapamatoval

- Výměna modelu = jeden řádek v `config.yaml` (vlastník); `validate` ho
  ověří proti OpenRouteru; záznam drží, co běželo.
- Každý scénář ve `workflows/` je zlatý test; fixtura se jménem scénáře
  v `../../framework/tests/golden/`; `cd ../../framework && uv run pytest`.
- `events.jsonl` = celý příběh běhu; `calls/` = každé volání; klíče,
  base64 ani tajné hodnoty v záznamu nejsou.
- Callback: vždy, podepsaný HMAC; `class` v `error` odliší `fail` od
  poruchy.

---

## Cvičení

Zlatý test scénáře z dílu 3 prochází jen větví `hravy`. Chceš mít
otestovanou i větev `vazny`. Zkopíruj
`workflows/scenarios/tutorial-03-rozhodovani.yaml` jako
`tutorial-05-cviceni.yaml` a napiš k němu fixturu, se kterou běh projde
větví `vazny`. Ověř to falešným během i `pytest`.

<details>
<summary>Řešení</summary>

Scénář se liší jen hlavičkou:

```bash
diff workflows/scenarios/tutorial-03-rozhodovani.yaml workflows/scenarios/tutorial-05-cviceni.yaml
```

```
2,3c2,3
< name: tutorial-03-rozhodovani
< description: Vymyslí název, nechá ho posoudit Jevem a podle tónu napíše slogan (tutoriál, díl 3)
---
> name: tutorial-05-cviceni
> description: Vymyslí název, nechá ho posoudit Jevem a podle tónu napíše slogan (tutoriál, díl 5 — řešení cvičení, větev vazny)
```

(Pozor na dvojtečku s mezerou v `description` — první verze měla
`… řešení cvičení: fixtura …` a YAML ji odmítl:
`config: tutorial-05-cviceni.yaml, řádek 3: YAML nejde přečíst — hodnota s {, [, ': ' nebo ' #' patří do uvozovek …`
a pod tím původní hláška parseru `mapping values are not allowed here`.
Text s `: ` dej do uvozovek, nebo dvojtečku vynech.)

`../../framework/tests/golden/tutorial-05-cviceni.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-05-cviceni (řešení cvičení z dílu 5).
# Jev vrátí ton: vazny → proběhne větev vazny, takže odpověď potřebuje slogan_vazny.
navrh:
  - json:
      nazev: "Ovena"
kontrola:
  - answers:
      zapamatovatelny: 0.9
      ton: vazny
      originalita: 1.1
slogan_vazny:
  - json:
      slogan: "Ovena. Rostlinná jemnost v každé lžičce."
```

Klíč je `slogan_vazny`, ne `slogan_hravy` — fixtura odpovídá krokům,
které **opravdu proběhnou**.

```bash
agencast run workflows/scenarios/tutorial-05-cviceni.yaml -i produkt="veganská zmrzlina" --fake ../../framework/tests/golden/tutorial-05-cviceni.yaml
```

```
běh 20260925-152230-tutorial-05-cviceni-c273: úspěch · 0,0 s · 0,0003 USD
```

```
| 4 | podle_tonu | switch | ✓ | 0,0 s | 0,0001 | větev vazny |
| 5 | slogan_hravy | ask | přeskočeno |  |  | switch: podle_tonu = "vazny" |
| 6 | slogan_vazny | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 7 | neznamy_ton | fail | přeskočeno |  |  | switch: podle_tonu = "vazny" |
…
## Výstup
- nazev: „Ovena"
- ton: „vazny"
- slogan: „Ovena. Rostlinná jemnost v každé lžičce."
- zapamatovatelnost: 90
```

```bash
cd ../../framework && uv run pytest -k tutorial-05 -v; cd ../examples/tutorial
```

```
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-05-cviceni] PASSED [100%]
```

Bez `ton: vazny` ve fixtuře by falešný Jev vrátil první možnost
(`hravy`) a test by prošel — ale jinou větví, než jsi chtěl. Proto si
v `summary.md` vždy zkontroluj poznámku `větev …`.

</details>

---

## Příloha: falešné n8n

Pro zvědavé — takhle jsem zachytil callback v kroku 4. Potřebuje
`openssl` a Python; běží jen na tvém počítači.

```bash
mkdir -p /tmp/n8n-mock && cd /tmp/n8n-mock
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 1 -subj "/CN=localhost" -addext "subjectAltName=IP:127.0.0.1,DNS:localhost"
```

`/tmp/n8n-mock/prijimac.py`:

```python
# Falešné n8n: HTTPS server, který vypíše hlavičky a tělo příchozího callbacku.
import http.server, ssl

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        print("POST", self.path)
        for k in ("Content-Type", "X-Run-Id", "X-Signature"):
            print(f"{k}: {self.headers[k]}")
        print(body.decode())
        open("posledni-telo.json", "wb").write(body)
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass

srv = http.server.HTTPServer(("127.0.0.1", 8443), H)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain("cert.pem", "key.pem")
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
srv.serve_forever()
```

Spusť ho v jednom terminálu (`cd /tmp/n8n-mock && python3 prijimac.py`),
ve druhém (v projektu `examples/tutorial`) řekni frameworku, ať certifikátu věří,
a pošli callback:

```bash
export CALLBACK_SECRET=tutorial-demo-tajemstvi
export SSL_CERT_FILE=/tmp/n8n-mock/cert.pem
agencast run workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="veganská zmrzlina" --fake ../../framework/tests/golden/tutorial-01-nazvy.yaml --callback-url https://127.0.0.1:8443/webhook-waiting/4711 --request-key n8n-4711
```

`SSL_CERT_FILE` nech nastavené jen v tomhle terminálu. Říká „věř **jen**
tomuhle certifikátu", takže spojení k OpenRouteru pak selže:

```
transient: GET https://openrouter.ai/api/v1/models selhalo ([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)) a platná cache runs/_models.json není — kontrola modelů potřebuje síť
```

Po zkoušce: `unset SSL_CERT_FILE CALLBACK_SECRET`.
