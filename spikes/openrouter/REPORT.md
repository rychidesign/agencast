# Spike (a) OpenRouter — REPORT

Datum měření: 2026-09-25. Holé HTTP (Python `urllib`, bez závislostí), klíč jen z prostředí.
Celková útrata: **≈ 0,30 USD** z rozpočtu 0,50 (`results/_spend.json`, součet `usage.cost`).

Opakování: `set -a; . <.env>; set +a; python3 q1_structured.py | q2_jev.py | q3_image.py --case neutral|person [--model ID]`
(jeden skript = jedna otázka; společné funkce `or_common.py` hlídají rozpočet 0,50 USD).

## Verdikty

| # | Otázka | Verdikt |
|---|---|---|
| 1 | Strukturovaný výstup + nástroj, 3 modely | **funguje s výhradou** — Claude a Kimi 10/10 nativně; Gemini flash-lite: schéma 5/5, schéma+nástroj 4/5 nativně, s kaskádou (L2 nástroj-obal) 5/5 |
| 2 | Jev přes `/api/v1/systemone` | **funguje** (5/5, medián 0,30 s, ~0,00003 USD/požadavek); beta nemá viditelné důsledky, viz níže |
| 3 | Obrázek přes chat completions | **funguje s výhradou** — tvar a cena ověřeny; **očekávané odmítnutí u skutečné osoby nenastalo** (obrázek se vygeneroval), třída chyby „content" zůstává nezachycena |

## 1. Strukturovaný výstup a nástroj

ID modelů (ověřeno `GET /api/v1/models`, `results/models.json`):
`anthropic/claude-haiku-4.5` (**pozor: ne `-4-5`**), `moonshotai/kimi-k3` (náhradník `z-ai/glm-5.3-flash` nebyl potřeba),
`google/gemini-3.5-flash-lite`. Všechny deklarují `tools` i `structured_outputs`.
Schéma `{caption: string, hashtags: string[], image_prompt: string}`, `strict: true`, `additionalProperties: false`, `temperature: 0`, `usage: {include: true}`.
Validace: vlastní (JSON parse + klíče + typy). „Nástroj" = `get_brand_guidelines` vrací pevný text; úspěch = nástroj zavolán **a** finální odpověď validní.

Úrovně kaskády: **L1** nativní `response_format` json_schema; **L2** nástroj `submit_post` jako obal schématu; **L3** prompt + validace (nebylo potřeba).

| Model | Případ | Úroveň | Úspěchy | Medián latence | Cena (5×) |
|---|---|---|---|---|---|
| claude-haiku-4.5 | (i) schéma | L1 | 5/5 | 3,7 s | 0,0074 USD |
| claude-haiku-4.5 | (ii) nástroj+schéma | L1 | 5/5 | 4,6 s | 0,0136 USD |
| kimi-k3 | (i) schéma | L1 | 5/5 | 3,7 s | 0,0252 USD |
| kimi-k3 | (ii) nástroj+schéma | L1 | 5/5 | 8,5 s | 0,0490 USD |
| gemini-3.5-flash-lite | (i) schéma | L1 | 5/5 | 1,8 s | 0,0025 USD |
| gemini-3.5-flash-lite | (ii) nástroj+schéma | L1 | **4/5** | 2,8 s | 0,0026 USD |
| gemini-3.5-flash-lite | (ii) nástroj+schéma | L2 | 5/5 | 2,1 s | 0,0022 USD |

Surové odpovědi: `results/q1_structured.json`. Poznámka: první průchod (1 opakování, ověření skriptu) není v tabulce; jeho útrata ano.

Nálezy:
- **Gemini, nástroj + nativní schéma (L1): 1 z 5 selhalo.** V prvním běhu model po výsledku nástroje volal `get_brand_guidelines` dokola (4 kola, žádná odpověď). V kontrolním běhu (`results/q1_gemini_echo_reasoning.json`), kde jsem navíc vracel `reasoning_details` zpět v assistant zprávě (Gemini vrací šifrovaný podpis myšlení), byla chyba jiná: `finish_reason: "error"`, `completion_tokens: 0`, `content` useknutý uprostřed JSON (HTTP status přesto **200**). Tj. chyba providera se může tvářit jako 200 s useknutým obsahem — framework musí kontrolovat `finish_reason` i validitu JSON, ne jen status. Chybu první varianty (smyčka) nemohu s jistotou oddělit od toho, že jsem `reasoning_details` nevracel; kontrolní běh smyčku nezopakoval (n=5, malý vzorek).
- Obě selhání zachytila kaskáda: L2 (nástroj jako obal schématu) 5/5 v obou bězích.
- Kimi k3 je 3–10× dražší a u nástroje nejpomalejší (8,5 s), ale spolehlivý; `reasoning` zapnuté z výroby, `max_tokens` jsem dal 3000.
- Nic z toho nevyvrací „podpora nástrojů deklarovaná OpenRouterem není záruka kvality" (DESIGN §5.5) — ale je to jen 5 opakování jednoho jednoduchého schématu.

## 2. Jev přes `/api/v1/systemone`

Požadavek: `{model: "jev-1.13", state: <česká zákaznická zpráva>, questions: {department: choice, dissatisfaction: score, deadline: noul}}`
(stejné otázky jako `jev-labs`). Doc: <https://openrouter.ai/docs/guides/community/typesafe-sdk>.

| Ukazatel | Hodnota |
|---|---|
| Úspěšnost | 5/5 (HTTP 200) |
| Latence (5×) | 0,283 / 0,288 / 0,304 / 0,319 / 0,392 s, **medián 0,30 s** |
| Cena | 2,83e-5 USD / požadavek (674 vstupních + 86 výstupních tokenů), 5× = 0,000142 USD |
| Determinismus | `department`=delivery/confidence 1 (5/5); `score` 1,05–1,07; `noul` 0,97–0,98 |

Přesný tvar odpovědi (`results/q2_jev.json`):
```json
{ "model": "typesafe/jev-1.13-20260917",
  "answers": {
    "department": {"type":"choice","choice":"delivery","probabilities":{"sales":0,"billing":0,"delivery":1,"technical":0,"other":0},"confidence":1},
    "dissatisfaction": {"type":"score","score":1.07,"legend":{"0":"…","1":"…","2":"…"},"probabilities":{"0":0,"1":0.93,"2":0.07},"confidence":0.9},
    "deadline": {"type":"noul","noul":0.97} },
  "usage": {"input_tokens":674,"output_tokens":86,"cost":2.8308e-05},
  "id": "gen-dec-…", "provider": "TypeSafe" }
```
- `model` v odpovědi je **datovaná verze** `typesafe/jev-1.13-20260917`; `jev-latest` se přeloží na stejnou (`results/q2_jev_model_aliases.json`). Pro reprodukovatelnost logovat toto pole.
- `usage` má jiný tvar než chat completions (`input_tokens`/`output_tokens`, ne `prompt_tokens`), `cost` je v USD.
- `noul` nemá `confidence`; `choice` a `score` mají `probabilities` a `confidence`; `score` má `legend`.
- **Chybný požadavek (chybí `questions`)**: HTTP **400**, tělo
  `{"error":{"message":"[{\"expected\":\"record\",\"code\":\"invalid_type\",\"path\":[\"questions\"],\"message\":\"Invalid input: expected record, received undefined\"}]","code":400},"user_id":"<redacted>"}`.
  `error.message` je **řetězec obsahující JSON pole** (Zod issues), ne strukturovaný objekt; v těle je navíc `user_id` (v uložených výsledcích jsem ho vymazal). Neexistující model: 400 `"Model typesafe/jev-9.99 does not exist"`.
- **Beta:** dokumentace OpenRouteru slovo „beta" nepoužívá (nenalezeno v docs ani na stránce modelu). Viditelné důsledky: Jev **není v `GET /api/v1/models`** (nedá se ověřit dotazem na modely; stránka `openrouter.ai/typesafe/jev-1.13` existuje), SDK `models.list()` s OpenRouterem nefunguje (uvádí dokumentace), chybové tělo je surová Zod zpráva. Stabilita: 6/6 platných požadavků OK, stránka modelu uvádí uptime 100 % / 99,89 % dostupnost (3 dny). Beta se tedy v měření neprojevila, ale vzorek je malý a kontrakt (tvar chyb, verze) není zaručen.

## 3. Obrázek

Model `google/gemini-3.1-flash-image` (i `-preview` varianta existuje; náhradník `google/gemini-2.5-flash-image` je také dostupný). Doc: <https://openrouter.ai/docs/features/multimodal/image-generation> (dokumentuje mj. dedikované Image API; zde použit požadovaný chat-completions režim s `modalities`).

| Případ | Model | Stav | Latence | Cena | Výstup |
|---|---|---|---|---|---|
| produktová fotka (káva, bez osob) | gemini-3.1-flash-image | 200 | 10,6 s | **0,0672 USD** | PNG 1408×768, 1,51 MB |
| skutečná známá osoba (veřejný činitel) | gemini-3.1-flash-image | 200 | 10,1 s | 0,0672 USD | obrázek **vygenerován** |
| tentýž prompt | gemini-2.5-flash-image | 200 | 5,8 s | 0,0387 USD | obrázek vygenerován (+ text „Jasně, tady je: ") |

Tvar odpovědi (`results/q3_neutral_*.json`, bez base64): `choices[0].message.images[]` = `[{"type":"image_url","image_url":{"url":"data:image/png;base64,<…>"}}]`; `message.content` je `null` (u 2.5 krátký text); další klíče `reasoning`, `reasoning_details`, `refusal`; `finish_reason: "stop"`, `native_finish_reason: "STOP"`. `reasoning_details` (šifrované, ~1,4 MB) jsem v uložených JSON zkrátil. Není to URL, vždy data URL s base64 → framework ukládá soubor (DESIGN §5.7 sedí). Rozměry jsem zjistil z PNG hlavičky; výchozí poměr stran nebyl nastaven (vyšlo 1408×768; pro Instagram (1:1, 4:5) je potřeba `image_config`/`aspect_ratio` — v tomto spiku neověřeno). `usage.cost` dominuje `completion_tokens_details.image_tokens` = 1120 tokenů × 60 USD/M.

- **Odmítnutí se nepodařilo vyvolat.** Prompt s konkrétní známou osobou prošel na obou modelech s HTTP 200 a obrázek byl vygenerován (podobizna je rozpoznatelná). Neuložil jsem ho do repozitáře (jen metadata v `results/q3_person_*.json`). Třídu chyby „content" tedy zatím nemáme naměřenou; nezkoušel jsem záměrně porušující prompty (nad rámec zadání).
- Zachycená chyba jiného druhu (model bez obrazového výstupu s `modalities: ["image","text"]`): HTTP **404**, `{"error":{"message":"No endpoints found that support the requested output modalities: image, text","code":404,"metadata":{"routing_funnel":[…],"failed_routing_step":"Filter by Model Output Modalities"}}}` (`results/q3_error_model_without_image_output.json`).
- Pro odmítnutí je třeba počítat s tím, že se může projevit jako **200 bez `images`** (prázdný obsah, `refusal`, `finish_reason` ≠ `stop`) — tento tvar jsem nepozoroval, jen pole `refusal` existuje ve zprávě.

## Co z toho plyne pro návrh

Fakta bez volby enginu/jazyka:

- **D1c / kaskáda (§5.5):** nativní json_schema strict fungovalo na všech třech modelech; potřeba L2 se objevila jen u Gemini v kombinaci nástroj + schéma. Úroveň per model (→ záznam): Claude L1, Kimi L1, Gemini L1 pro samotné schéma, L2 pro schéma+nástroj. L3 nebyl potřeba. Konformační scénář musí testovat **kombinaci** schéma+nástroj zvlášť, ne jen obě věci odděleně.
- **Kontrola úspěchu kroku:** HTTP 200 nestačí. Provider může vrátit 200 s `finish_reason: "error"` a useknutým JSON (Gemini). Validace `finish_reason` + parse + schéma je nutná v každém kroku, opakování patří do frameworku.
- **Multi-turn s nástroji:** u Gemini se vrací šifrované `reasoning_details`; runtime (nebo vlastní smyčka) by je měl posílat zpět beze změny (doporučení OpenRouteru pro reasoning modely; u mého kontrolního běhu neřešilo obě selhání, ale je to správná praxe).
- **Náklad/latence pro plánování rozpočtu běhu:** textový krok 1,8–8,5 s a 0,0005–0,010 USD; Jev 0,3 s a ~0,00003 USD (řádově zanedbatelné); **obrázek 0,04–0,07 USD a 6–11 s** — o dva řády dražší než ostatní kroky, patří do rozpočtu i do časového limitu běhu (D5/Modal).
- **D3/D4 (relevantní data):** vše bylo použitelné holým HTTP bez SDK; `usage.cost` je u všech tří endpointů, ale tvar `usage` se liší (chat: `prompt_tokens/completion_tokens/cost`; systemone: `input_tokens/output_tokens/cost`) → vrstva `usage` musí normalizovat.
- **§5.7 obrázky:** odpověď = data URL base64 (~1,5 MB PNG u 1 obrázku), takže záznam běhu nesmí obsahovat base64 inline; ukládat do souboru a v záznamu nést cestu.
- **Chybové třídy pro §5.1:** (a) 4xx s `error.message` (u Jev je to serializované JSON pole, u OpenRouteru objekt `metadata`), (b) 200 s `finish_reason: "error"`, (c) 404 routování (model nepodporuje modality), (d) jeden nezachycený případ: content-odmítnutí u obrázků (nevyvoláno).
- **Bezpečnost obsahu:** OpenRouter/Gemini negenerovaly odmítnutí u podobizny veřejného činitele → pokud framework potřebuje politiku obsahu (osoby, značky), musí ji vynutit sám (pre-check promptu), nespoléhat na provider.
