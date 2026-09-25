# Díl 7 — Skládání a provoz: `call` a webhook

**Čas:** asi 35 minut · **Útrata:** 0 USD s `--fake`; volitelný ostrý
běh přes webhook ~0,001 USD
**Co budeš umět:** poskládat scénář ze stavebnic (`call`), spustit
`maw serve` a volat ho jako n8n (token, `request_key`, callback
s podpisem), otevřít `report.html` a pojistit krok s vedlejším účinkem
přes `dedupe_key`.

Předpoklad: díly 1–6 (krok `task` a agent `tutorial-archivar` z dílu 6)
a `curl`.

> Výstupy jsou skutečné — z běhů 25. 9. 2026 proti `maw` 0.2.1. Příkazy
> spouštěj z kořene repozitáře se zkratkou `maw` z dílu 1. Tvoje
> `run_id`, časy a texty budou jiné.

---

## Krok 1 — hotová stavebnice: `kontrola-tonu`

Ve `workflows/scenarios/` už jeden scénář-stavebnici máš:

```yaml
version: 1
name: kontrola-tonu
description: Zkontroluje, že text sedí na tón značky THTD (volá se krokem call z jiných scénářů)
callable: true

inputs:
  text:
    type: string
    required: true
    description: Text ke kontrole
  prah:
    type: number
    default: 0.7
    description: Od jaké hodnoty on_brand je text v pořádku

outputs:
  on_brand:
    type: number
    description: Míra shody s tónem značky od 0 do 1
  v_poradku:
    type: boolean
    description: on_brand dosáhl prahu

steps:
  - id: kontrola
    jev: …
  - id: vysledek
    set:
      v_poradku: steps.kontrola.on_brand >= inputs.prah
  - id: out
    output:
      on_brand: "{{ steps.kontrola.on_brand }}"
      v_poradku: "{{ steps.vysledek.v_poradku }}"
```

Tři věci z něj dělají stavebnici:

- **`callable: true`** — jen takový scénář smí jiný scénář zavolat.
  Bez něj je `call` chyba. Chrání to schvalování: publikační scénář
  (bez `callable`) nemůže nikdo zavolat zevnitř a obejít tak člověka
  v n8n.
- **`inputs`** — co volající **musí** dát (`text`) a co smí (`prah`,
  jinak 0.7).
- **`outputs`** — co volající dostane zpátky. Nic jiného z vnitřku
  (`steps.kontrola.details`…) nevidí.

`inputs` + `outputs` jsou **smlouva**. Stavebnice sama o dalším postupu
nerozhoduje (žádný `fail`) — vrátí `v_poradku` a rozhodne volající.

---

## Krok 2 — vlastní stavebnice

`workflows/scenarios/tutorial-07-slogan.yaml` — sloganista z dílu 2
zabalený do scénáře:

```yaml
version: 1
name: tutorial-07-slogan
description: Napíše slogan k hotovému názvu produktu (tutoriál, díl 7 — stavebnice pro call)
callable: true

inputs:
  nazev:
    type: string
    required: true
    description: Název produktu
  ton:
    type: string
    default: hravy
    description: Tón sloganu (hravy, vazny…)

outputs:
  slogan:
    type: string
    description: Jeden slogan

steps:
  # 1. Sloganista z dílu 2 dostane název a tón od volajícího scénáře.
  - id: napis
    ask:
      agent: tutorial-sloganista
      prompt: |
        Název produktu: {{ inputs.nazev }}
        Tón: {{ inputs.ton }}
        Napiš k němu jeden slogan.
      schema:
        slogan: string

  # 2. Výstup = smlouva s volajícím: čte steps.<id krok call>.slogan.
  - id: out
    output:
      slogan: "{{ steps.napis.slogan }}"
```

Stavebnice je normální scénář — jde spustit i sama
(`maw run tutorial-07-slogan -i nazev=Ovena`).

---

## Krok 3 — skládání krokem `call`

`workflows/scenarios/tutorial-07-skladani.yaml`:

```yaml
version: 1
name: tutorial-07-skladani
description: Vymyslí název, slogan dodá scénář tutorial-07-slogan a tón zkontroluje kontrola-tonu (tutoriál, díl 7)

inputs:
  produkt:
    type: string
    required: true
    description: Jaký produkt pojmenováváme

outputs:
  nazev:
    type: string
    description: Navržený název
  slogan:
    type: string
    description: Slogan ze scénáře tutorial-07-slogan
  on_brand:
    type: number
    description: Hodnocení tónu ze scénáře kontrola-tonu

steps:
  # 1. Obyčejný ask z dílu 2.
  - id: navrh
    ask:
      agent: tutorial-pojmenovavac
      prompt: "Vymysli jeden název pro tento produkt: {{ inputs.produkt }}."
      schema:
        nazev: string

  # 2. Vlastní stavebnice: vstup nazev je required, ton má default.
  - id: slogan
    call:
      scenario: tutorial-07-slogan
      inputs:
        nazev: "{{ steps.navrh.nazev }}"

  # 3. Hotová stavebnice z workflows/: prah má default 0.7.
  - id: ton
    call:
      scenario: kontrola-tonu
      inputs:
        text: "{{ steps.navrh.nazev }}. {{ steps.slogan.slogan }}"

  - id: out
    output:
      nazev: "{{ steps.navrh.nazev }}"
      slogan: "{{ steps.slogan.slogan }}"
      on_brand: "{{ steps.ton.on_brand }}"
```

- `call.scenario` = jméno scénáře, `call.inputs` = jeho vstupy (šablony
  jako v `prompt`).
- Výstup kroku `call` jsou `outputs` volaného scénáře:
  `steps.slogan.slogan`, `steps.ton.on_brand`.
- Volaný scénář běží **uvnitř stejného běhu**: stejný rozpočet, stejný
  časový limit, jeden záznam. Není to nový běh ve frontě.

### Fixtura: cesta ke kroku uvnitř

Kroky volaného scénáře mají ve fixtuře (a v záznamu) **cestu**
`<id kroku call>/<id kroku uvnitř>`.
`framework/tests/golden/tutorial-07-skladani.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-07-skladani. Kroky volaných scénářů
# mají cestu <id kroku call>/<id kroku ve volaném scénáři>.
navrh:
  - json: { nazev: "Ovena" }
slogan/napis:
  - json: { slogan: "Ovena. Zmrzlina, co roste na poli." }
ton/kontrola:
  - answers: { on_brand: 0.82 }
```

(A `framework/tests/golden/tutorial-07-slogan.yaml` s klíčem `napis` pro
stavebnici samotnou — i ona je zlatý test.)

```bash
maw validate tutorial-07-skladani
maw run tutorial-07-skladani -i produkt="veganská zmrzlina z ovesného mléka" --fake framework/tests/golden/tutorial-07-skladani.yaml
```

```
v pořádku: tutorial-07-skladani (4 kroky)
běh 20260925-161539-tutorial-07-skladani-ffe2: úspěch · 0,0 s · 0,0003 USD
```

```
| 1 | navrh | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | call | ✓ | 0,0 s | 0,0001 | scénář tutorial-07-slogan (2 kroky) |
| 3 | ton | call | ✓ | 0,0 s | 0,0001 | scénář kontrola-tonu (3 kroky) |
| 4 | out | output | ✓ | 0,0 s | 0 |  |
| | Celkem | | | | 0,0003 |  |
…
## Výstup
- nazev: „Ovena"
- slogan: „Ovena. Zmrzlina, co roste na poli."
- on_brand: 0,82
```

Záznam volaného scénáře je podsložka kroku `call`:

```
steps/
  01-navrh/
  02-slogan/
    inputs.json            co stavebnice dostala (po doplnění default: ton = hravy)
    output.json            co vrátila
    steps/01-napis/        prompt.md, calls/…
    steps/02-out/
  03-ton/
    inputs.json
    output.json
    steps/01-kontrola/ …
  04-out/
```

A v `events.jsonl` mají kroky uvnitř cestu: `slogan/napis`,
`ton/kontrola`, `ton/vysledek`…

### Co řekne `validate`, když smlouva nesedí

Zkoušej v kopii (`rm -rf /tmp/pokus && mkdir -p /tmp/pokus && cp -r
workflows /tmp/pokus/`) a spouštěj `maw validate
/tmp/pokus/workflows/scenarios/tutorial-07-skladani.yaml`.

Chybí povinný vstup (místo `nazev` předáš `produkt`):

```
config: tutorial-07-skladani.yaml: krok "slogan", call.inputs: scénář 'tutorial-07-slogan' nemá vstupy: produkt (má: nazev, ton)
config: tutorial-07-skladani.yaml: krok "slogan", call.inputs: chybí povinné vstupy scénáře 'tutorial-07-slogan': nazev
```

Vstup navíc (`delka: kratky`):

```
config: tutorial-07-skladani.yaml: krok "slogan", call.inputs: scénář 'tutorial-07-slogan' nemá vstupy: delka (má: nazev, ton)
```

Špatný typ (`prah: vysoky` do `kontrola-tonu`):

```
config: tutorial-07-skladani.yaml: krok "ton", call.inputs.prah: vstup má typ number, hodnota je string
```

Čtení výstupu, který stavebnice nemá (`steps.slogan.text` — jako
u `ask` bez `schema`):

```
config: tutorial-07-skladani.yaml: krok "out", output.slogan: 'steps.slogan' nemá klíč 'text' (dostupné: slogan)
  {{ steps.slogan.text }}
                  ^
```

Volání scénáře bez `callable: true` (`scenario: tutorial-02-nazev-a-slogan`):

```
config: tutorial-07-skladani.yaml: krok "slogan", call.scenario: scénář 'tutorial-02-nazev-a-slogan' nemá callable: true — volat ho nejde (chrání schvalování v n8n, §5.2)
```

**Cyklus.** Dej do kopie `tutorial-07-skladani.yaml` `callable: true`
a do kopie `tutorial-07-slogan.yaml` před `out` krok, který volá
skládání zpátky:

```yaml
  - id: znovu
    call:
      scenario: tutorial-07-skladani
      inputs:
        produkt: "{{ inputs.nazev }}"
```

```
config: tutorial-07-slogan.yaml: krok "znovu", call.scenario: cyklus call: tutorial-07-skladani → tutorial-07-slogan → tutorial-07-skladani
```

Framework by jinak scénáře volal donekonečna (a platil). Kromě cyklů
hlídá i hloubku vnoření: `limits.max_call_depth` v `config.yaml`, u nás 3.

---

## Krok 4 — `maw serve`: framework jako webová služba

V provozu běhy nespouštíš ty z terminálu, ale n8n: pošle `POST` s tím,
co spustit, hned dostane `run_id` a výsledek mu přijde později na jeho
adresu (callback). Přesně to dělá `maw serve`.

### Dvě tajné hodnoty do `.env`

`config.yaml` (vlastník) říká, jak se proměnné jmenují:

```
webhook:
  token_env: WEBHOOK_TOKEN
callback:
  secret_env: CALLBACK_SECRET
```

- **`WEBHOOK_TOKEN`** — heslo, které musí poslat každý, kdo chce běh
  spustit (hlavička `Authorization: Bearer …`). Bez něj by ti kdokoli,
  kdo zná adresu, pouštěl scénáře za tvoje peníze.
- **`CALLBACK_SECRET`** — tajemství, kterým framework podepisuje
  výsledek. Příjemce (n8n) podle podpisu pozná, že zprávu poslal opravdu
  tvůj framework a nikdo ji cestou nezměnil.

Hodnoty vygeneruj a připiš do `.env` **bez vypsání na obrazovku**
(`.env` je v `.gitignore`, do gitu se nedostane):

```bash
python3 -c "import secrets; open('.env', 'a').write(f'\nWEBHOOK_TOKEN={secrets.token_urlsafe(32)}\nCALLBACK_SECRET={secrets.token_urlsafe(32)}\n')"
cut -d= -f1 .env
```

```
OPENROUTER_API_KEY

WEBHOOK_TOKEN
CALLBACK_SECRET
```

`cut` ukáže jen jména. Hodnoty nikam nekopíruj ani nevypisuj — až
budeš nastavovat n8n, vlož je rovnou do jeho credentials. Když máš
z dílu 5 v terminálu `export CALLBACK_SECRET=…`, zruš ho
(`unset CALLBACK_SECRET`): proměnná z prostředí má přednost před `.env`.

Bez nich server nenastartuje:

```
config: chybí proměnná prostředí WEBHOOK_TOKEN (.env nebo prostředí)
config: chybí proměnná prostředí CALLBACK_SECRET (.env nebo prostředí)
```

### Tři terminály

**Terminál 1 — přijímač callbacku.** Místo n8n malý skript,
[`docs/tutorials/callback-prijemac.py`](callback-prijemac.py) (jen
stdlib): vypíše, co přišlo, a ověří podpis. Tajemství čte z `.env`.

```bash
python3 docs/tutorials/callback-prijemac.py
```

```
čekám na callback na http://127.0.0.1:8799/ (Ctrl+C = konec)
```

**Terminál 2 — server**, zatím s falešným poskytovatelem a fixturou
z kroku 3:

```bash
maw serve --fake framework/tests/golden/tutorial-07-skladani.yaml
```

```
maw serve: http://127.0.0.1:8080 — POST /runs, GET /runs/<run_id> · ve frontě 0 běhů · záznamy …/runs · falešný poskytovatel
```

Poslouchá jen na `127.0.0.1` (výchozí `--host`) — z jiného počítače se
k němu nedostaneš. Tak to nech: server je HTTP bez šifrování a token jde
v hlavičce; ven patří jen za reverzní proxy s HTTPS.

**Terminál 3 — ty jako n8n.** Token si načti do proměnné terminálu
(nevypíše se):

```bash
TOKEN=$(sed -n 's/^WEBHOOK_TOKEN=//p' .env)
```

---

## Krok 5 — `POST /runs`: 401, 422, 202

Bez tokenu (nebo se špatným):

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario": "tutorial-07-skladani", "inputs": {"produkt": "veganská zmrzlina"}, "callback_url": "http://127.0.0.1:8799/cb"}'
```

```
{"error": "chybí nebo nesedí token (hlavička Authorization: Bearer …)"}
HTTP 401
```

S tokenem, ale bez povinného vstupu (`"inputs": {}`):

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/runs \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"scenario": "tutorial-07-skladani", "inputs": {}, "callback_url": "http://127.0.0.1:8799/cb"}'
```

```
{"error": "scénář 'tutorial-07-skladani' nebo jeho vstupy neprošly kontrolou", "details": ["chybí povinný vstup 'produkt' (string)"]}
HTTP 422
```

Další 422, které stojí za vidění (měníš jen tělo):

| Tělo | Odpověď |
|---|---|
| `"scenario": "tutorial-07-skladanii"` | `{"error": "neznámý scénář 'tutorial-07-skladanii'", "details": []}` |
| `"inputs": {"produkt": 42}` | `"details": ["vstup 'produkt' má být string, dostal number"]` |
| `"callback_url": "http://example.com/cb"` | `"details": ["callback_url: chybí nebo nezačíná https://"]` |
| navíc `"priorita": "vysoka"` | `"details": ["neznámé pole 'priorita' (povolená: scenario, inputs, callback_url, request_key)"]` |

Všechno, co jde poznat bez spuštění — token, tvar těla, vstupy, `validate`
scénáře —, se odmítne **hned**. Pak nevzniká `run_id` ani callback;
n8n má chybu v odpovědi a nemusí na nic čekat.

`callback_url` smí být jen `https://`. Jediná výjimka je
`http://127.0.0.1` — pro zkoušky jako tahle.

Správný požadavek, tentokrát s `request_key`:

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/runs \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"scenario": "tutorial-07-skladani", "inputs": {"produkt": "veganská zmrzlina z ovesného mléka"}, "callback_url": "http://127.0.0.1:8799/cb", "request_key": "tutorial-07-1"}'
```

```
{"run_id": "20260925-161808-tutorial-07-skladani-9db3", "queue_position": 1}
HTTP 202
```

**202 = přijato**, ne hotovo. Běh je ve frontě (`queue_position` 1 =
je na řadě). Běhy jdou jeden po druhém.

### Callback

V terminálu 1 se hned objeví:

```
POST /cb  X-Run-Id: 20260925-161808-tutorial-07-skladani-9db3
podpis: sedí
{
  "run_id": "20260925-161808-tutorial-07-skladani-9db3",
  "scenario": "tutorial-07-skladani",
  "request_key": "tutorial-07-1",
  "status": "succeeded",
  "outputs": {
    "nazev": "Ovena",
    "slogan": "Ovena. Zmrzlina, co roste na poli.",
    "on_brand": 0.82
  },
  "error": null,
  "warnings": [],
  "cost_usd": 0.0003,
  "duration_s": 0.004,
  "report_url": "file:///…/outputs/20260925-161808-tutorial-07-skladani-9db3-d6adb4c4f6710c8bc3612b66c7543c25/report.html",
  "sent_at": "2026-09-25T16:18:08.704Z"
}
```

Stejný tvar jako v dílu 5 (pole v tabulce tam). Nové je `report_url`
(krok 7). Jak přijímač ověřuje podpis, je v jeho kódu v deseti řádcích:
spočítá HMAC-SHA256 **přesných bajtů těla** s `CALLBACK_SECRET`
a porovná ho s hlavičkou `X-Signature` funkcí `hmac.compare_digest`
(porovnání, které neprozradí délkou trvání, kde se liší). Když podpis
nesedí, vypíše „NESEDÍ" a odpoví 401 — framework to pak zkusí ještě
dvakrát a zapíše `callback_failed` (díl 5).

### `GET /runs/<run_id>`

Když callback nepřišel (n8n zrovna nejelo), stav se dá zjistit:

```bash
curl -s -w '\nHTTP %{http_code}\n' -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/runs/20260925-161808-tutorial-07-skladani-9db3
```

```
{"run_id": "20260925-161808-tutorial-07-skladani-9db3", "scenario": "tutorial-07-skladani", "request_key": "tutorial-07-1", "status": "succeeded", "outputs": {"nazev": "Ovena", "slogan": "Ovena. Zmrzlina, co roste na poli.", "on_brand": 0.82}, "error": null, "warnings": [], "cost_usd": 0.0003, "duration_s": 0.004, "report_url": "file:///…/report.html", "sent_at": "2026-09-25T16:18:08.704Z", "callback_failed": false}
HTTP 200
```

Hotový běh = tělo callbacku + `callback_failed`. Dokud běh čeká nebo
běží, vrací `{"status": "queued", "queue_position": …}`, resp.
`{"status": "running"}`. Neznámé `run_id` → 404. I `GET` chce token.

---

## Krok 6 — `request_key`: pošli to dvakrát

n8n někdy pošle stejný požadavek znovu — vypadne síť dřív, než dostane
odpověď, a jeho HTTP Request node to zopakuje. Pošli úplně stejný
`curl` (se stejným `request_key`) podruhé:

```
{"run_id": "20260925-161808-tutorial-07-skladani-9db3", "queue_position": null}
HTTP 200
```

**200 místo 202**, původní `run_id`, žádný nový běh, žádný druhý
callback. Server si klíč pamatuje v `runs/_queue/keys/` (jeden soubor na
klíč), takže to platí i po restartu serveru.

Pozor: rozhoduje **jen klíč**. Požadavek se stejným `request_key`, ale
jinými vstupy dostane taky 200 a původní běh. n8n proto musí dávat klíč,
který patří k jednomu požadavku (např. id svého běhu), ne k tématu.

---

## Krok 7 — `report.html`

Každý běh má kromě `summary.md` i `report.html` — jeden soubor, CSS
uvnitř, žádné externí zdroje, takže ho jde poslat e-mailem nebo otevřít
offline. Framework ho zkopíruje do úložiště a jeho adresu dá do
callbacku (`report_url`). U nás `storage.type: local`, takže je to
`file://` cesta:

```bash
xdg-open "$(ls -d outputs/20260925-161808-tutorial-07-skladani-9db3-*)/report.html"   # macOS: open
```

(Nebo zkopíruj `report_url` do prohlížeče.) Nahoře stejný souhrn jako
v `summary.md`, pod každým krokem rozbalovací `<details>`:

```
Prompt
Volání 1 · chytry → anthropic/claude-haiku-4.5 · stop · 264+15 tokenů · 0,0003 USD · 1,4 s
Výstup kroku
```

(Tenhle řádek je z ostrého běhu v kroku 9.) Kroky volaných scénářů jsou
v reportu taky, včetně volání Jevu. Base64 obrázků ani tajné hodnoty
v něm nejsou (stejná pravidla jako záznam, díl 5).

Proč to v callbacku je: v n8n uvidíš jen `outputs` a `error`. Když
výsledek vypadá divně, `report_url` je jedno kliknutí ke všemu, co model
dostal a vrátil. S úložištěm R2 (vlastník, `config.yaml`) z toho bude
veřejná HTTPS adresa s 32 náhodnými znaky, kterou nikdo neuhodne.

---

## Krok 8 — `dedupe_key`: vedlejší účinek nejvýš jednou

`request_key` chrání před **stejným požadavkem** dvakrát. Nechrání ale
před **dvěma různými požadavky**, které udělají totéž — typicky když
n8n spustí workflow znovu (ruční „Retry", nový běh = nový klíč). U kroku,
který jen něco napíše do `outputs`, to nevadí. U kroku s **vedlejším
účinkem** — zapíše soubor, publikuje příspěvek, pošle e-mail — ano:
příspěvek by vyšel dvakrát.

Na to je `dedupe_key` u kroku `task`.
`workflows/scenarios/tutorial-07-archiv.yaml` (archivář z dílu 6):

```yaml
version: 1
name: tutorial-07-archiv
description: Zapíše poznámku dne do archivu nejvýš jednou, i když přijde požadavek znovu (tutoriál, díl 7)

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
    description: Co archivář zapsal (při opakování odpověď z prvního běhu)

steps:
  # 1. Krok s vedlejším účinkem (zápis). dedupe_key: pro stejný den proběhne
  #    nejvýš jednou — další běh vezme výstup ze <runs>/_dedupe/ a krok přeskočí.
  - id: zapis
    dedupe_key: "archiv-{{ inputs.den }}"
    task:
      agent: tutorial-archivar
      prompt: |
        Den: {{ inputs.den }}
        Poznámka: {{ inputs.text }}
        Zapiš poznámku do archivu a zkontroluj ji.
      max_turns: 5

  - id: out
    output:
      zprava: "{{ steps.zapis.text }}"
```

Fixtura `framework/tests/golden/tutorial-07-archiv.yaml` má stejné tahy
jako `tutorial-06-archiv`. Restartuj server (terminál 2, Ctrl+C) s ní:

```bash
maw serve --fake framework/tests/golden/tutorial-07-archiv.yaml
```

a pošli dva **různé** požadavky (`n8n-5001`, `n8n-5002`) na stejný den:

```bash
for k in n8n-5001 n8n-5002; do
  curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/runs \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d "{\"scenario\": \"tutorial-07-archiv\", \"inputs\": {\"den\": \"2026-09-25\", \"text\": \"Ráno pršelo. Odpoledne jsme dopsali díl 7.\"}, \"callback_url\": \"http://127.0.0.1:8799/cb\", \"request_key\": \"$k\"}"
  sleep 3
done
```

```
{"run_id": "20260925-161842-tutorial-07-archiv-5637", "queue_position": 1}
HTTP 202
{"run_id": "20260925-161845-tutorial-07-archiv-0e28", "queue_position": 1}
HTTP 202
```

Dva běhy, dva callbacky, oba `succeeded` se stejnou `zprava`. Rozdíl je
v ceně (`cost_usd` 0.0004 vs. **0.0**) a v `summary.md` druhého běhu:

```
| 1 | zapis | task | přeskočeno |  |  | dedupe_key 'archiv-2026-09-25': krok už proběhl v běhu 20260925-161842-tutorial-07-archiv-5637 |
| 2 | out | output | ✓ | 0,0 s | 0 |  |
| | Celkem | | | | 0 |  |
```

Druhý běh nemá složku `work/` ani `mcp/` — server se vůbec nespustil.
Výstup kroku se vzal ze souboru v `runs/_dedupe-fake/` (běhy s `--fake`
mají od `maw` 0.2.2 vlastní složku, ostré běhy `runs/_dedupe/` — viz
[níž](#pozor---fake-má-vlastní-runs_dedupe-fake)):

```bash
cat runs/_dedupe-fake/*.json
```

```
{"state": "succeeded", "run_id": "20260925-161842-tutorial-07-archiv-5637", "output": {"text": "Zapsáno: 2026-09-25.md a obsah.md. Zápis má 2 věty."}}
```

Jméno souboru je SHA-256 ze `scénář/krok/klíč` — stejný den v jiném
scénáři (třeba `tutorial-06-archiv`) se nesplete.

### Když krok spadne uprostřed

Framework zapíše `"state": "started"` **před prvním voláním nástroje**
a `succeeded` až po úspěšném konci kroku. Co když krok mezitím spadne?
Nasimuluj to z CLI — `/tmp/preruseny.yaml` zapíše soubor a pak se točí,
až dojdou tahy:

```yaml
# Zapíše soubor a pak už jen volá nástroje, až dojdou tahy (max_turns) — krok selže po vedlejším účinku.
zapis:
  - tool_calls:
      - name: filesystem__write_file
        arguments: { path: 2026-09-26.md, content: "# Zápis 2026-09-26\n- Rozepsáno.\n" }
  - tool_calls:
      - { name: filesystem__list_directory, arguments: { path: . } }
```

```bash
maw run tutorial-07-archiv -i den=2026-09-26 -i text="Rozepsáno." --fake /tmp/preruseny.yaml
maw run tutorial-07-archiv -i den=2026-09-26 -i text="Rozepsáno." --fake /tmp/preruseny.yaml
```

```
budget v kroku zapis: max_turns 5 vyčerpán bez finální odpovědi (model dál volá nástroje)
běh 20260925-161858-tutorial-07-archiv-63f7: chyba · 0,8 s · 0,0005 USD
…
config v kroku zapis: krok mohl proběhnout jen částečně (dedupe_key 'archiv-2026-09-26', běh 20260925-161858-tutorial-07-archiv-63f7), ověř ručně a smaž …/runs/_dedupe-fake/bb7e315cde46b31154a770c34ace3ddf790d1dca42166e01502c7b2592e8d3a5.json
běh 20260925-161859-tutorial-07-archiv-8627: chyba · 0,0 s · 0 USD
```

Druhý běh krok **nespustil**. Framework neví, jestli první běh stihl
publikovat (tady stihl zapsat soubor) — a hádat nebude. Podívej se do
záznamu prvního běhu (`tool_call`, `work/`), a až víš, že je to
v pořádku, soubor smaž. Nic se tiše neopakuje.

### Pozor: `--fake` má vlastní `runs/_dedupe-fake/`

Falešné běhy zapisují dedupe do `runs/_dedupe-fake/`, ostré do
`runs/_dedupe/`, a nikdy si je nečtou navzájem. Zkouška s `--fake` tak
ostrý vedlejší účinek nepřeskočí: ostrý běh na den, který jsi zkoušel
s `--fake`, krok `zapis` opravdu provede. Falešný běh poznáš v
`summary.md` podle řádku pod hlavičkou:

```
**Falešný běh** (`--fake`) — odpovědi modelů jsou vymyšlené, dedupe v `_dedupe-fake/`.
```

a v `events.jsonl` podle `"fake": true` v `run_started`. (V `maw` 0.2.1
sdílely oba režimy `runs/_dedupe/` a ostrý běh po zkoušce vrátil
vymyšlený výstup — BUGS.md, bod 8.)

---

## Krok 9 — ostrý běh přes webhook (volitelný)

Zastav server (Ctrl+C) a pusť ho **bez** `--fake`:

```bash
maw serve
```

```
maw serve: http://127.0.0.1:8080 — POST /runs, GET /runs/<run_id> · ve frontě 0 běhů · záznamy …/runs
```

```bash
curl -s -w '\nHTTP %{http_code} za %{time_total} s\n' -X POST http://127.0.0.1:8080/runs \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"scenario": "tutorial-07-skladani", "inputs": {"produkt": "veganská zmrzlina z ovesného mléka"}, "callback_url": "http://127.0.0.1:8799/cb", "request_key": "tutorial-07-ostry-1"}'
```

```
{"run_id": "20260925-161929-tutorial-07-skladani-217a", "queue_position": 1}
HTTP 202 za 0.032238 s
```

Callback za necelé 4 s:

```
POST /cb  X-Run-Id: 20260925-161929-tutorial-07-skladani-217a
podpis: sedí
{
  …
  "status": "succeeded",
  "outputs": {
    "nazev": "Ovesový krém",
    "slogan": "Ovesový krém - zdraví v každé lžici!",
    "on_brand": 0.25
  },
  "error": null,
  "warnings": [],
  "cost_usd": 0.00071494,
  "duration_s": 3.787,
  …
}
```

```
| 1 | navrh | ask | ✓ | 1,4 s | 0,0003 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | call | ✓ | 2,0 s | 0,0004 | scénář tutorial-07-slogan (2 kroky) |
| 3 | ton | call | ✓ | 0,4 s | 0,00002 | scénář kontrola-tonu (3 kroky) |
```

`on_brand` 0,25 — slogan s vykřičníkem a „zdraví v každé lžici" není
tón THTD. Běh přesto skončil úspěchem: `kontrola-tonu` jen měří,
rozhoduje volající, a `tutorial-07-skladani` žádný `fail` nemá. Kdybys
chtěl nevhodný text zastavit, přidej za `ton` krok jako v
`ukazka-call.yaml`:

```yaml
  - id: stop
    when: not steps.ton.v_poradku
    fail: "Slogan neodpovídá značce (on_brand = {{ steps.ton.on_brand }})"
```

Na konci zastav server i přijímač (Ctrl+C).

---

## Krok 10 — co z toho potřebuje n8n

n8n tady nenastavujeme, jen co v něm bude. Jde to postavit ze dvou
workflow (fakta o uzlech z dokumentace n8n, repozitář `n8n-io/n8n-docs`,
stránky Webhook, Wait a Crypto node, staženo 2026-09-25):

**Workflow A — spuštění**

1. **Webhook node** (nebo jiný spouštěč — formulář, plán) přijme
   zadání, např. `produkt`.
2. **HTTP Request node**: `POST https://<tvůj-maw>/runs`, hlavička
   `Authorization: Bearer <WEBHOOK_TOKEN>` (ulož jako credential typu
   Header Auth, ne do textu uzlu), tělo:

   ```json
   {
     "scenario": "tutorial-07-skladani",
     "inputs": {"produkt": "…z kroku 1…"},
     "callback_url": "https://<n8n>/webhook/maw-vysledek",
     "request_key": "n8n-<id běhu n8n>"
   }
   ```

   Odpověď 202 → hotovo, `run_id` si ulož. 401/422 → chyba je hned
   v odpovědi (`details`), callback nepřijde.

**Workflow B — výsledek**

3. **Webhook node** na cestě `maw-vysledek`, metoda `POST`, volba
   **Raw Body** zapnutá (podpis se počítá z přesných bajtů těla, ne
   z JSON, který n8n rozebere a znovu složí — díl 5), odpověď
   *Immediately* (framework čeká jen na 2xx).
4. **Crypto node**, akce **Hmac**, **Binary File** zapnuté (raw tělo
   z kroku 3 přijde jako binární data), typ **SHA256**, kódování **HEX**,
   tajemství `CALLBACK_SECRET` v Crypto credential; výsledek porovnej
   (IF node) s hlavičkou `x-signature` bez předpony `sha256=`. Nesedí →
   konec, zprávě nevěř.
5. **IF / Switch** podle `status` a `error.class`: `succeeded` → dál
   (schválení, publikace), `fail` → záměrné zastavení scénářem (např.
   tón), ostatní třídy → porucha, upozornit člověka. `report_url` přilož
   do upozornění.

Místo workflow B jde použít **Wait node** („Resume: On Webhook Call")
přímo ve workflow A a jako `callback_url` poslat jeho
`$execution.resumeUrl` — adresu, kterou n8n vyrobí pro každý běh zvlášť
(to je „resume URL" z dílu 5). Pak nastav **Limit Wait Time**: běh může
čekat ve frontě, a když callback nedorazí, n8n jinak čeká navždy.

Co n8n **nepotřebuje** vědět: modely, agenty, MCP servery ani jak
scénář uvnitř vypadá. Smlouva je `scenario` + `inputs` dovnitř,
`outputs` + `status` + `error` ven.

---

## Co sis zapamatoval

- `callable: true` + `inputs` + `outputs` = stavebnice. `call` běží ve
  stejném běhu; `validate` hlídá chybějící/navíc vstupy, typy, čtené
  výstupy, `callable` a cykly.
- Fixtura a záznam: kroky uvnitř mají cestu `<call>/<krok>`.
- `maw serve`: `WEBHOOK_TOKEN` a `CALLBACK_SECRET` v `.env`; 401/422
  hned a bez callbacku, 202 = ve frontě, callback vždy a podepsaný,
  `GET /runs/<id>` jako záloha.
- `request_key` = stejný požadavek jen jednou; `dedupe_key` = stejný
  vedlejší účinek jen jednou, i napříč běhy. `started` bez `succeeded`
  = ověř ručně.
- `report_url` = celý záznam jedním odkazem.

---

## Cvičení

Chceš k jednomu názvu dva slogany naráz — hravý a vážný. Napiš
`workflows/scenarios/tutorial-07-cviceni.yaml`, který zavolá
`tutorial-07-slogan` **dvakrát paralelně** (díl 4) s různým `ton`,
a fixturu k němu. Nápověda: jak se budou ve fixtuře jmenovat kroky
uvnitř?

<details>
<summary>Řešení</summary>

```yaml
version: 1
name: tutorial-07-cviceni
description: Dva slogany k jednomu názvu naráz — stavebnice tutorial-07-slogan dvakrát paralelně (tutoriál, díl 7 — řešení cvičení)

inputs:
  nazev:
    type: string
    required: true
    description: Název produktu

outputs:
  hravy:
    type: string
    description: Hravý slogan
  vazny:
    type: string
    description: Vážný slogan

steps:
  # Stejný scénář dvakrát, každá větev s jiným tónem. Kroky call mají různá id,
  # proto mají v záznamu i ve fixtuře různé cesty (hravy_slogan/napis, vazny_slogan/napis).
  - id: varianty
    parallel:
      hrava:
        - id: hravy_slogan
          call:
            scenario: tutorial-07-slogan
            inputs:
              nazev: "{{ inputs.nazev }}"
      vazna:
        - id: vazny_slogan
          call:
            scenario: tutorial-07-slogan
            inputs:
              nazev: "{{ inputs.nazev }}"
              ton: vazny

  - id: out
    output:
      hravy: "{{ steps.hravy_slogan.slogan }}"
      vazny: "{{ steps.vazny_slogan.slogan }}"
```

`framework/tests/golden/tutorial-07-cviceni.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-07-cviceni (řešení cvičení z dílu 7).
# Cesta = <id kroku call>/<id kroku ve volaném scénáři>; větev parallel v cestě není.
hravy_slogan/napis:
  - json: { slogan: "Ovena. Lžička, co se směje." }
vazny_slogan/napis:
  - json: { slogan: "Ovena. Rostlinná jemnost v každé lžičce." }
```

Uvnitř obou volání je krok `napis` — rozliší je až `id` kroku `call`.
Proto musí mít každé volání vlastní `id` (to by chtěl `validate` stejně).

```bash
maw run tutorial-07-cviceni -i nazev=Ovena --fake framework/tests/golden/tutorial-07-cviceni.yaml
```

```
| 1 | varianty | parallel | ✓ | 0,0 s | 0,0002 |  |
| 2 | hravy_slogan | call | ✓ | 0,0 s | 0,0001 | scénář tutorial-07-slogan (2 kroky) |
| 3 | vazny_slogan | call | ✓ | 0,0 s | 0,0001 | scénář tutorial-07-slogan (2 kroky) |
| 4 | out | output | ✓ | 0,0 s | 0 |  |
| | Celkem | | | | 0,0002 |  |
…
## Výstup
- hravy: „Ovena. Lžička, co se směje."
- vazny: „Ovena. Rostlinná jemnost v každé lžičce."
```

Že každá větev dostala svůj tón, ověříš v promptech:

```bash
grep Tón runs/20260925-161627-tutorial-07-cviceni-1e5a/steps/*/steps/01-napis/prompt.md
```

```
runs/…/steps/02-hravy_slogan/steps/01-napis/prompt.md:Tón: hravy
runs/…/steps/03-vazny_slogan/steps/01-napis/prompt.md:Tón: vazny
```

`hravy` přišel z `default` stavebnice, `vazny` z volání.

```bash
cd framework && uv run pytest -k tutorial-07 -v; cd ..
```

```
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-archiv] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-cviceni] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-skladani] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-slogan] PASSED
```

</details>

---

## Co přijde dál

Tímhle končí série. Co `maw` 0.2.1 ještě neumí a přijde s Fází 3c
frameworku: běh na Modal.com a úložiště R2, se kterým bude `report_url`
i soubory z `output` veřejná HTTPS adresa. Přehled všech dílů je
v [README.md](README.md).
