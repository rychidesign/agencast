# Spike (c) Výrazy pro D1c — REPORT

Datum měření: 2026-09-25. Python 3.12, uv 0.11.8, projektový venv v této složce. Bez API klíčů, útrata 0 USD.

Jak to zopakovat:
```
cd spikes/expressions
uv sync                     # nainstaluje kandidáty podle uv.lock
uv run python run.py        # celá matice kandidát × výraz → results/*.json + tabulka (≈12 s)
uv run python custom_eval.py  # self-check prototypu vlastního evaluátoru
python3 meta.py             # metadata z PyPI a GitHub API → results/meta.json
```
Soubory: `cases.py` (kontext + 58 výrazů), `adapters.py` (konfigurace kandidátů), `custom_eval.py`
(prototyp vlastního evaluátoru), `run.py` (matice; každý výraz v samostatném procesu, timeout 10 s,
limit paměti 1,5 GB), `results/<kandidát>.json` (každý výraz: výsledek nebo typ a text chyby, čas,
hodnocení), `results/summary.json`, `results/table.md`.

## Verdikt

| Kandidát | Verdikt pro D1c + §5.4 |
|---|---|
| **vlastní evaluátor nad `ast`** | **funguje** — jediný splní všechna tři kritéria D1c (nulový přístup k systému, typové chyby s čitelnou hláškou, determinismus) i §5.4 (porovnání napříč typy = chyba). Prototyp má 207 řádků kódu + 13 řádků self-checku. Výhrada: testovací sadu i evaluátor psal stejný autor, viz „Zkreslení". |
| simpleeval + podtřída (tečka jen jako klíč) | **funguje s výhradou** — bezpečné, ale tiše vrací `False` pro `3 == "3"`, `True + 1` = 2, pravdivostní hodnota listu v `and`; bez seznamových literálů. Dotáhnout na §5.4 = přepsat porovnání, `and/or/not` a aritmetiku, tj. zhruba tolik kódu jako vlastní evaluátor, a k tomu závislost navíc. |
| simpleeval (výchozí) | nefunguje — `steps.copy` vrací metodu `dict.copy`, povolená volání metod (`inputs.keys()`), přiřazení `x = …` projde, výchozí funkce `rand`/`randint` |
| asteval (`minimal=True`) | **nefunguje** — `open('/etc/passwd').read()` **přečte soubor** i v minimálním režimu; `print`, `type` dostupné; je to interpret celého Pythonu (cykly, funkce), ne výrazový jazyk |
| evalidate | nefunguje — atributy povoluje podle **jména**, ne typu: tečkový přístup k dictům vyžaduje vyjmenovat všechny klíče kontextu; nesedí na dynamické `steps` |
| RestrictedPython | **nefunguje (nevhodný)** — sám o sobě říká „not a sandbox system" (METADATA ř. 64); projde `lambda`, `:=`, volání metod; žádná ochrana proti DoS (`10**10**10` → timeout, `"a"*10**9` → 1 GB řetězec za 0,33 s) |
| cel-python (CEL) | funguje s výhradou — bezpečné, ale jiná syntaxe (proti D1c), 260 µs/výraz, hlášky s interními typy, `true + 1` = 2 |
| cel-rust (`common-expression-language`, CEL) | funguje s výhradou — bezpečné a přísné, ale jiná syntaxe; **SIGSEGV** (pád celého procesu) na výrazu `1+1+…` s ~15 000 členy; `3 == "3"` → `False` |

## Matice kandidát × kategorie

Sada: **24 platných**, **14 chybových**, **20 škodlivých** výrazů nad kontextem z `cases.py`
(`inputs`, `steps.kontrola`, `steps.copy`, `item`). Pro CEL se použil idiomatický přepis (`&&`, `size()`,
`null`, `double(x) / 4.0`); škodlivé výrazy jdou do CEL doslova (většina skončí syntaktickou chybou =
odmítnuto). Funkce `min/max/round/join` jsou u CEL doregistrované.

| kandidát | platné ok | chybové: vyhozena chyba (z toho hláška zmiňuje klíč/typ) / **tiše prošlo** | škodlivé odmítnuté / **prošlo** | medián µs na platný výraz |
|---|---|---|---|---|
| vlastní (`custom_eval.py`) | 24/24 | 14/14 (14) / 0 | 20/20 / 0 | 10 |
| simpleeval | 16/24 | 11/14 (10) / 3 | 19/20 / 1 | 16 |
| simpleeval + dictonly | 23/24 | 11/14 (9) / 3 | 20/20 / 0 | 13 |
| asteval | 17/24 | 11/14 (10) / 3 | 16/20 / 4 | 23 |
| evalidate | 17/24 | 12/14 (9) / 2 | 20/20 / 0 | 26 |
| RestrictedPython | 17/24 | 12/14 (10) / 2 | 15/20 / 5 | 37 |
| cel-python | 24/24 | 12/14 (6) / 2 | 20/20 / 0 | 261 |
| cel-rust | 24/24 | 13/14 (10) / 1 | 19/20 / 1 | 20 |

Hodnocení (`run.py:grade`): platné = hodnota i typ sedí (bool musí být bool); chybové = výjimka,
„čitelná" pokud text obsahuje jméno klíče / typ / index (hrubá heuristika); škodlivé = výjimka,
u DoS případů (H18–H20) stačí i výsledek spočítaný bez pádu a timeoutu. `type()` v CEL
(H12) je standardní funkce vracející jen typ, proto se u CEL nepočítá jako průnik.
Časy jsou orientační (kompilace + vyhodnocení při každém volání, 300 opakování, jeden stroj).
Determinismus: u všech kandidátů 300 opakování každého platného výrazu = stejný výsledek.

Co přesně selhalo (`results/summary.json → failures`):

| kandidát | selhání |
|---|---|
| simpleeval | V07 V08 V10 V16 V17 V20 V22 (vše `steps.copy…`), V21 (seznamový literál), E05 E06 E09 tiše, H10 `inputs.keys()` projde |
| simpleeval + dictonly | V21, E05 E06 E14 tiše |
| asteval | 7× `steps.copy`, E05 E06 E09 tiše, **H03 `open()` čte soubor**, H10, H12 `type()`, H13 `print()` |
| evalidate | 7× `steps.copy`, E05 E06 tiše |
| RestrictedPython | 7× `steps.copy`, E05 E06 tiše, H05 `lambda`, H10, H14 `:=`, H16 1 GB řetězec, H17 timeout |
| cel-python | E06 `true + 1` = 2, E14 `list && bool` vrátí list |
| cel-rust | E05 `3 == "3"` = false, **H18 SIGSEGV** |

## Nálezy

1. **Tečka přes `getattr` koliduje s metodami dictu.** Krok pojmenovaný `copy` (ze zadání) rozbije
   všechny výrazy `steps.copy.…` u simpleeval, asteval, evalidate i RestrictedPython: `steps.copy`
   vrátí vázanou metodu `dict.copy` a `.hashtags` pak neexistuje. simpleeval zkouší nejdřív
   `getattr` a až pak `obj[key]` (`simpleeval.py` `_eval_attribute`, `ATTR_INDEX_FALLBACK`);
   ostatní potřebují obal `dict` s `__getattr__`, který má stejný problém. Totéž hrozí pro kroky/klíče
   `items`, `keys`, `values`, `get`, `pop`, `update`… **Tečka musí být čtení klíče, ne atribut.**
   Splňují to jen vlastní evaluátor, simpleeval s přepsaným `_eval_attribute` a CEL.
2. **Porovnání napříč typy (§5.4) tiše vrací `False`.** `inputs.limit == "3"` → `False` bez chyby
   u všech pythonových knihoven i u cel-rust. Chybu hlásí jen vlastní evaluátor a cel-python.
   (`<`/`>` napříč typy hlásí `TypeError` všichni, protože to dělá Python sám.)
3. **`bool` je v Pythonu `int`.** `True + 1` = 2 u všech pythonových knihoven i u cel-python
   (`celtypes.BoolType(int)`, `celtypes.py:389`). Odmítá to vlastní evaluátor a cel-rust.
4. **Pravdivostní hodnota ne-boolu.** `steps.copy.hashtags and …` projde u simpleeval+dictonly
   a cel-python. Prototyp vyžaduje v `and/or/not` bool (hláška radí `len(x) > 0`). **Tohle je
   návrhové rozhodnutí, ne fakt** — viz otevřené otázky.
5. **asteval není sandbox pro náš účel.** I s `minimal=True` jsou v tabulce symbolů `open`
   (jen pro čtení), `print`, `type`, `dir` (`astutils.py:211 LOCALFUNCS`, 127 symbolů). Test
   `open('/etc/passwd').read()` vrátil obsah souboru. `no_attribute=True` zakáže atributy úplně
   (pak nefunguje ani tečka nad dictem), `open("/etc/passwd")` jde zavolat dál.
6. **RestrictedPython** je kompilátor podmnožiny Pythonu pro Zope skripty, ne výrazový jazyk;
   dokumentace: „RestrictedPython is not a sandbox system or a secured environment". Chování
   závisí na strážcích (`_getattr_`, `_getitem_`), které si dodá aplikace. S `safer_getattr`
   (varianta z `Guards.py:246`, `default=None`) vracel chybějící klíč **tiše `None`**; v matici je
   proto `safer_getattr_raise`. Bez vlastních limitů na `**` a `*` padá na DoS.
7. **cel-rust shodí proces.** `1+1+…+1` s 15 000 a více členy (~30 kB) → exit 139 (SIGSEGV),
   12 000 členů ještě projde. Výjimka z Pythonu to nezachytí. Obrana: limit délky výrazu před
   voláním knihovny. Pythonové parsery skončí čistou výjimkou (`RecursionError`,
   `MemoryError: Parser stack overflowed`, `SyntaxError: too many nested parentheses` nad 200 úrovní závorek).
8. **simpleeval výchozí konfigurace**: přiřazení `inputs.jazyk = "cs"` projde a vrátí `"cs"`
   (`ast.Assign` ve výchozích uzlech, `simpleeval.py:569`); výchozí funkce jsou `rand`, `randint`
   (nedeterministické, `simpleeval.py:524`); volání metod řetězců jsou povolená, jen `format`
   a dunder atributy blokuje. `EvalWithCompoundTypes` (kvůli seznamovým literálům) přidá
   i `ListComp`/`DictComp`/`GeneratorExp`, takže by se musely zase odebrat.
9. **evalidate** povoluje atributy podle jména (`EvalModel.attributes`), bez ohledu na typ objektu.
   Pro tečkový přístup do `steps` jsem musel dynamicky vyjmenovat všechny klíče kontextu; krok
   pojmenovaný `upper` by pak povolil i `"x".upper()`. Hláška pro chybějící klíč:
   „Attribute x is not allowed" (jmenuje špatný klíč).
10. **`round(2.5)` = 2** u všech kandidátů (pythonové bankéřské zaokrouhlení). Deterministické,
    ale pro autora scénáře překvapivé → specifikace to musí říct (nebo definovat round-half-up).
11. **CEL a čitelnost** (idiomatický přepis v `cases.py`, pole `cel`): `&&`/`||`/`!`, `size()`
    místo `len()`, `null`, bez záporných indexů (`xs[size(xs) - 1]`), bez implicitního převodu
    int↔double (`double(item.cena) / 4.0`, `on_brand * 100.0`), `int / int` je celočíselné dělení.
    Bezpečnostní model je výborný (bez side-effectů, omezené makra), ale jde proti rozhodnutí
    D1c „v pythonovském stylu".
12. **Pozice v hláškách.** Python u „neočekávaného konce" (`a <`) vrací `offset 0`, prototyp to
    převádí na stříšku za koncem výrazu. `ast` dává `col_offset` v bajtech UTF-8, pro češtinu
    je potřeba převod na znaky (prototyp to dělá).

## Ukázky chybových hlášek

Chybějící klíč `steps.neexistuje.x`:

| kandidát | hláška |
|---|---|
| vlastní | `key: 'steps' nemá klíč 'neexistuje' (dostupné: kontrola, copy)` + řádek výrazu se stříškou pod `neexistuje` |
| simpleeval | `AttributeDoesNotExist: Attribute 'neexistuje' does not exist in expression 'steps.neexistuje.x'` |
| asteval | `AttributeError: steps.neexistuje.x \n AttributeError: neexistuje` |
| evalidate | `ValidationException: Attribute x is not allowed` |
| RestrictedPython | `safer_getattr`: **žádná chyba, `None`**; `safer_getattr_raise`: `AttributeError` |
| cel-python | `CELEvalError: ("no such member in mapping: 'neexistuje'", <class 'KeyError'>, None)` |
| cel-rust | `KeyError: 'neexistuje'` |

Porovnání čísla s textem `inputs.limit == "3"` a `steps.kontrola.on_brand < "0.7"`:

| kandidát | `==` | `<` |
|---|---|---|
| vlastní | `type: porovnání number s string — převeď typ výslovně (int(), str())` + stříška pod `"3"` | `type: nelze number < string` + stříška |
| simpleeval, asteval, evalidate, RestrictedPython | **`False`** | `TypeError: '<' not supported between instances of 'float' and 'str'` |
| cel-python | `found no matching overload for Token('RULE', 'relation_eq') applied to '(<class 'celpy.celtypes.IntType'>, …StringType…)'` | obdobně |
| cel-rust | **`False`** | `No such overload: the operation is not defined for the given operand types. CEL does not coerce between types, …` |

Syntaktická chyba `steps.kontrola.on_brand <`:

| kandidát | hláška |
|---|---|
| vlastní | `syntax: neočekávaný konec výrazu` + stříška za koncem |
| simpleeval | `SyntaxError: invalid syntax (<unknown>, line 1)` |
| RestrictedPython | `Line 1: SyntaxError: invalid syntax at statement: 'steps.kontrola.on_brand <'` |
| cel-rust | `Failed to parse expression …: ERROR: <input>:1:26: Syntax error: mismatched input '<EOF>' expecting {…}` |

Další hlášky prototypu (výstup `custom_eval.py`):
```
index: index 10 mimo rozsah 'steps.copy.hashtags' (délka 3)
type: nelze null + number          (inputs.poznamka + 1, stříška pod 1)
type: 'and' chce bool, dostal list — porovnej výslovně (např. len(x) > 0)
forbidden: volání metod není povolené                  (steps.copy.caption.upper())
forbidden: funkce 'open' není povolená (povolené: len, min, max, round, str, int, float, join)
limit: výraz má 100001 znaků, max 2000
```

## Údržba (PyPI + GitHub API, 2026-09-25, `results/meta.json`)

| balíček | verze | vydáno | licence | ★ | runtime závislosti | wheel |
|---|---|---|---|---|---|---|
| simpleeval | 1.0.8 | 2026-09-12 | MIT (PyPI klasifikátor; GitHub „NOASSERTION") | 613 | žádné | 18 kB |
| asteval | 1.0.10 | 2026-08-21 | MIT | 221 | žádné (NumPy volitelně) | 23 kB |
| evalidate | 2.1.4 | 2026-03-02 | MIT | 42 | žádné | 13 kB |
| RestrictedPython | 8.5 | 2026-08-19 | ZPL-2.1 (PyPI) | 743 | žádné | 30 kB |
| cel-python (`celpy`) | 0.5.0 | 2026-01-31 | Apache-2.0 | 174 | google-re2, jmespath, lark, pendulum, pyyaml | 83 kB |
| common-expression-language (cel-rust) | 0.10.0 | 2026-09-15 | Apache-2.0 | 43 | typer, rich, prompt-toolkit, pygments (kvůli CLI) | 1,2 MB (nativní) |
| vlastní evaluátor | — | — | naše | — | žádné (stdlib `ast`) | 207 ř. |

Všechny projekty jsou živé (push v posledních měsících, nic archivováno).

## Odhad řádků vlastního evaluátoru

Prototyp `custom_eval.py`: **207 řádků kódu** (bez prázdných a komentářů) + 13 řádků self-checku.
Obsahuje: whitelist uzlů přes `match`, tečku a `[]` jako čtení klíče/indexu, přísné typy
(porovnání, aritmetika, bool v `and/or/not`, `==` s `None` povolené napříč typy, `is` jen
`is None`), `in` nad listem/řetězcem/objektem, seznamové literály, 8 funkcí s typovou kontrolou,
limit délky 2000 znaků a hloubky 100, hlášky s třídou chyby (`syntax/name/key/index/type/value/zero/forbidden/limit`),
jménem klíče, seznamem dostupných klíčů a pozicí.

Odhad pro framework (Fáze 2): **~350–500 řádků** + testy.
- ~200–250: runtime evaluátor (to, co je v prototypu, uklizené).
- ~100–200: statická kontrola pro `validate` nad stejným AST: syntaxe, zakázané uzly, neznámé
  funkce, odkazy na neexistující / přeskočené kroky (§5.4), a pokud jsou známá výstupní schémata
  kroků, i typová kontrola porovnání (§5.4 chce „chybu validace", ne až za běhu).
- ~50: napojení na `{{ }}` šablony (stejný evaluátor pro čistý odkaz), mapování na třídy chyb §5.1.
- Testy: `cases.py` je hotový základ konformačních scénářů (58 případů).

## Zkreslení a limity měření

- Vlastní evaluátor a testovací sadu psal stejný worker; 24/24 + 14/14 + 20/20 dokazuje, že
  požadované chování jde postavit na ~200 řádcích, ne že je prototyp bez chyb. Nezávislé
  adversariální testy by měl psát někdo jiný.
- Konfigurace knihoven je „rozumná, jak by ji napsal autor frameworku", ne maximálně zpevněná
  (kromě varianty simpleeval + dictonly). Každá knihovna jde dál ohýbat — otázka je, kolik kódu
  to stojí; u simpleeval je to srovnatelné s vlastním evaluátorem.
- Heuristika „čitelné hlášky" jen hledá podřetězec (jméno klíče, `str`, `bool`…). Ukázky výše jsou
  lepší vodítko.
- DoS: měřeno jen těch pět tvarů (H16–H20); výpočetní složitost funkcí (`join` nad obřím listem
  z výstupu kroku) neměřena.

## Co z toho plyne pro Fázi 2

Fakta:
- Žádná knihovna v pythonovské syntaxi nesplní §5.4 (porovnání napříč typy = chyba) bez
  přepsání porovnání; čtyři ze šesti pythonových konfigurací navíc rozbije krok jménem `copy`.
- asteval a RestrictedPython nesplní „nulový přístup k systému" ve výchozím stavu
  (`open()` čte soubor, `lambda`, `:=`), obě jsou interpretry celého Pythonu místo výrazového jazyka.
- CEL splňuje bezpečnost nejlépe z knihoven, ale je to jiná syntaxe (rozhodnutí D1c říká
  pythonovský styl) a u obou implementací je výhrada (cel-python pomalý + těžké závislosti,
  cel-rust segfault a `3 == "3"` → false).
- Vlastní evaluátor: 0 závislostí, 207 řádků, sémantika i hlášky (česky, s pozicí a dostupnými
  klíči) plně pod kontrolou; D4 počítá s „evaluátorem výrazů dle D1c" ve výchozí sadě knihoven.

Doporučení (rozhoduje koordinátor):
1. **Vlastní evaluátor nad `ast`** — přepsat poznatky z prototypu do `framework/`, ne kopírovat kód.
   Důvod: jediný splní D1c i §5.4 bez ohýbání cizí knihovny; kód je malý a na nás je údržba stejně
   (D3). Rychlost (~10 µs) není faktor.
2. Záložní varianta: simpleeval + podtřída (přepsat `_eval_attribute`, `_eval_compare`,
   `_eval_boolop`, odebrat `Assign`/`Import`/f-stringy, přidat `List`). Dává smysl jen pokud
   nechceme vlastní kód vůbec; ve výsledku je to podobně řádků + závislost.
3. Nepoužívat asteval, RestrictedPython, evalidate. CEL jen pokud by se D1c otevřelo znovu.
4. Obrana do hloubky bez ohledu na volbu: limit délky výrazu **před** parserem (cel-rust
   segfault, `RecursionError` Pythonu), žádný `getattr` v evaluátoru, funkce bez side-effectů
   a bez náhody.

Otevřené otázky pro specifikaci (prototyp zvolil v závorce, ne rozhodnuto):
- Pravdivost v `and`/`or`/`not`: jen bool, nebo pythonová truthiness? (jen bool)
- `==`/`!=` s `None` napříč typy povoleno? (ano; jinak chyba)
- `round`: bankéřské (Python) nebo half-up? `/` vždy float? (Python: bankéřské, float)
- `str(None)` → `"None"` nebo `"null"`? `str(True)` → `"True"`? (Python)
- Patří do jazyka seznamové literály, `in`, `x if c else y`, řezy `xs[1:3]`, `**`? (literály a `in` ano; ternár, řezy, `**` ne)
- `+` řetězec + číslo: chyba (nutné `str()`)? (chyba)
- Limity délky a hloubky (2000 znaků / 100) a třída chyby výrazu za běhu v §5.1 (validace = `config`; za běhu?).
