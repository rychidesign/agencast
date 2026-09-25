# Spike (b) Modal — REPORT

Datum: 2026-09-25. Modal SDK `modal` **1.5.5** (Python 3.11 lokálně, kontejnery 3.12), `mcp` SDK nebyl potřeba (holý JSON-RPC).
Kód: `q1_mcp.py` (Q1), `flow.py` (Q2–Q4), `env.sh` (načtení `.env` bez CRLF).
Cena: pár desítek sekund CPU + 3×60 s sleep — řádově centy, hluboko pod 1 USD (přesný údaj z billingu nezjišťován).

## Verdikty

| # | Otázka | Verdikt |
|---|---|---|
| 1 | Image + stdio MCP server (npx) | **funguje** |
| 2 | Webhook → `.spawn()` → callback, `max_containers=1`, fronta | **funguje** (s výhradou k redeployi, viz nálezy) |
| 3 | Volume + veřejná URL souboru přes web endpoint | **funguje**; R2 neimplementováno (chybí klíče), popis níže |
| 4 | `modal.Secret` → `OPENROUTER_API_KEY` v kontejneru | **funguje** (`from_name` i `from_dict`) |

## Naměřená čísla

| Měření | Hodnota |
|---|---|
| Build image `debian_slim` + apt `nodejs npm` + `npm i -g @modelcontextprotocol/server-filesystem` | 7,9 s (vrstva npm; základ z cache), celý `modal run` se 2 image ≈ 87 s |
| Cold start funkce (nový kontejner) + celý MCP handshake, preinstalováno | 7,4 s wall (initialize→tools/list uvnitř 0,7 s) |
| Cold start, `npx -y` za běhu | 6,1 s wall; z toho MCP initialize **3,8 s** (stažení balíčku) |
| Warm volání, preinstalováno | 0,77 s wall; initialize 0,57 s |
| Warm volání, `npx -y` (npm cache v kontejneru) | 1,11 s wall; initialize 0,98 s |
| Čas do prvního `tools/list` (uvnitř kontejneru od spuštění procesu) | 0,74 s preinst. / 3,77 s npx (cold), 0,59 / 0,99 s (warm) |
| Server nabízí | 14 nástrojů (`read_file`, `write_file`, `edit_file`, `directory_tree`, …) |
| Latence webhooku `submit` (401 bez tokenu / 200 s tokenem) | 0,77–0,79 s (3 požadavky za sebou, kontejner warm) |
| Cold start `run_flow` po prvním submitu | 3,7 s (submit → start funkce) |
| Pořadí běhů (start / konec, s od startu prvního) | #1 0,0 / 61,6; #2 66,7 / 127,8; #3 128,5 / 189,6 |
| Callback dorazil po konci běhu | +4,7 s (první, studený callback endpoint), +0,3 s, +0,4 s |
| Mezera mezi běhy (konec → start dalšího) | 0,7–5,1 s |
| Veřejný GET PNG z Volume (`spike-file`) | 5,9 s cold, 0,88–0,93 s warm; 404 na neexistující run |

Běhy proběhly **striktně po jednom** (žádné překryvy), webhook odpověděl okamžitě, ne po doběhnutí.
`backlog_at_submit` z `run_flow.get_current_stats().backlog` vrátil 1, 1, 3 — nepřesné/opožděné, nespoléhat se na to pro „pozici ve frontě“ z D2 (nález).

## API Modalu (ověřeno v SDK 1.5.5 a dokumentaci)

- **`max_containers`** — nový název (dřívější `concurrency_limit`), parametr `@app.function(max_containers=1)`. Signatura v SDK: `min_containers, max_containers, buffer_containers, scaledown_window, timeout, startup_timeout, retries`. Doc: <https://modal.com/docs/guide/scale>
- **Web endpoint:** `@modal.fastapi_endpoint(method="POST", label="…")` (pod `@app.function`). Vyžaduje `fastapi` v image. `modal.web_endpoint` je deprecated alias. Doc: <https://modal.com/docs/guide/webhooks>
- **`.spawn()`** — `run_flow.spawn(...)` vrací `FunctionCall`, `call.object_id` = `fc-…`; výsledek `FunctionCall.from_id(id).get()`. Doc: <https://modal.com/docs/guide/webhooks> (sekce o spawn z endpointu), <https://modal.com/docs/guide/job-queue>
- **Volume:** `modal.Volume.from_name("flow-runs", create_if_missing=True)`, v kontejneru `volumes={"/runs": vol}`; po zápisu `vol.commit()`, čtenář před čtením `vol.reload()`. CLI: `modal volume ls|get flow-runs <path>`.
- **Secrets:** `modal.Secret.from_name("x")`, `modal.Secret.from_dict({...})`; CLI `modal secret create NAME KEY=val`.
- **Adresa endpointu:** `https://<workspace>--<label>.modal.run`; z jiné funkce `fn.get_web_url()` (fungovalo pro callback URL).

## Limity (doc)

- Web endpoint: max HTTP request timeout **150 s**; delší → HTTP **303** redirect s query parametrem na původní požadavek. Proto submit jen `.spawn()` a hned vrací. <https://modal.com/docs/guide/webhook-timeouts> (150 s jsem netestoval, jen z dokumentace.)
- Timeout funkce: default 300 s, nastavitelný **1 s – 24 h** (`timeout=`); počítá se jen doba vykonávání, ne čekání ve frontě, a je per pokus (retries ho restartují). <https://modal.com/docs/guide/timeouts> — pro běhy „minuty až hodina“ z D2 stačí.
- `.spawn()` při `max_containers=1`: vstupy čekají ve frontě funkce a jdou postupně (ověřeno 3 běhy). Maximální délku fronty jsem neověřoval.

## Q3 — totéž přes Cloudflare R2 (neimplementováno)

Potřeba: R2 bucket; API token (S3 kompatibilní) → `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` jako Modal Secret; endpoint `https://<account_id>.r2.cloudflarestorage.com`. Knihovna: `boto3` (`client("s3", endpoint_url=…, region_name="auto")`) → `upload_file(path, bucket, f"{run_id}/image.png", ExtraArgs={"ContentType": …})`. Veřejná URL: buď custom doména / `r2.dev` subdoména zapnutá na bucketu (trvalá veřejná), nebo `generate_presigned_url` (časově omezená, funguje jen přes S3 endpoint). Instagram Graph API chce stabilní veřejnou URL → custom doména/r2.dev. Ověřit v dokumentaci Cloudflare R2 před implementací (nepsáno z ověřeného čtení v tomto spiku).

## Q4 — Secrets

`OPENROUTER_API_KEY` z lokálního `.env` uložen `modal secret create spike-openrouter OPENROUTER_API_KEY=$OPENROUTER_API_KEY` (bez zápisu do kódu; secret v shellu expandován, nic se nevypsalo) a připojen `Secret.from_name`. Druhá varianta `Secret.from_dict({"OR_KEY_FROM_DICT": os.environ[...]})` (hodnota se čte z lokálního env při `modal deploy`, do kódu se nezapisuje, ale putuje s definicí funkce). V kontejneru obě proměnné přítomné (délka > 0, callback nesl jen `true`). Doporučení: `from_name` (klíč žije v Modalu, rotace bez redeploye kódu). Token endpointů (`FLOW_TOKEN`) také ze secretu, kontrola v hlavičce `x-token` (bez tokenu 401).

## Nečekané nálezy

1. **`modal deploy` nad běžící app nemusí vyměnit warm kontejnery.** Po opravě kódu (`Request` → `Header`) 3× redeploy stále obsluhoval starou verzi, dokud jsem app nezastavil (`modal app stop -y`) a nenasadil znovu. Pro D5: nasazovat se stop/deploy, nebo ověřit verzi po deployi.
2. **`request: "fastapi.Request"` (řetězcová anotace) se v `fastapi_endpoint` bere jako povinný query parametr** (422 `loc: query.request`). Pro čtení hlaviček použít `Header()`.
3. `.env` v hlavním checkoutu má **CRLF** konce řádků → `source` dá tokenu na konci `\r` a Modal hlásí `Invalid metadata value`. Načítat přes `tr -d '\r'` (`env.sh`). Při tomto selhání se do výstupu chyby dostalo ID tokenu (ne secret); do reportu nepatří.
4. `backlog` z `get_current_stats()` není spolehlivá pozice ve frontě (viz výše). Pozici pro `run_id` v D2 by musela držet vlastní evidence (např. `modal.Dict`/n8n).
5. Studené starty: kontejner ~4–7 s, první volání studeného web endpointu k tomu připočítá ~4–5 s (viz callback #1, GET souboru).
6. `modal.Dict` je pohodlný pro sběr callbacků v testu, ale `Dict.from_name` bez `create_if_missing=True` na neexistující selže.

## Co z toho plyne pro návrh

- **D2 (fronta):** `max_containers=1` + `.spawn()` dává přesně „běhy jeden za druhým“ bez vlastní fronty; webhook odpovídá < 1 s. Timeout běhu do 24 h; čekání ve frontě se do timeoutu funkce nepočítá (na timeout v n8n to ale platí). Pozici ve frontě si musí držet framework/n8n sám. Callback z kontejneru na HTTPS endpoint fungoval (POST z funkce ven bez omezení).
- **D2 (záznam běhu):** složka běhu na Volume + čtení přes `modal volume get` i přes web endpoint funguje; nutné `commit()`/`reload()`. Soubory jsou dostupné bez R2, ale URL je Modal-specifická; pro Instagram/trvalé odkazy zůstává R2.
- **D5 (hosting):** MCP servery přes `npx` v Modal kontejneru fungují; **předinstalovat balíček do image** (cold handshake 0,7 s vs 3,8 s, warm 0,6 vs 1,0 s). Image vrstva s npm se sestaví za ~8 s. Jeden společný Dockerfile lze použít přes `modal.Image.from_dockerfile` (nezkoušeno).
- Endpointy je nutné chránit vlastním tokenem (Modal web endpointy jsou jinak veřejné); token i API klíče ze `modal.Secret`.
- Nasazení: stop + deploy (nález 1).

## Úklid

`modal app stop spike-flow` a `spike-mcp` (stav *stopped*; endpoint `spike-submit` vrací 404). Smazány secrety `spike-token`, `spike-openrouter` a Dict `spike-callbacks`. Volume `flow-runs` zůstává (3 složky běhů). Cizí aplikace/volumes uživatele nedotčeny. Token pro endpointy je jen v ignorovaném `.env.spike` (secret už neexistuje).
