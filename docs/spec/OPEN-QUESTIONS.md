# Otevřené otázky ke specifikaci v1

Rozhodnutí, která patří uživateli: buď se odchylují od znění DESIGN.md,
nebo mění bezpečnost či syntaxi, kterou uživatel píše. Ke každé je
doporučení — **specifikace je už napsaná podle doporučení**, takže
„souhlasím" znamená žádnou změnu. Drobnosti, které rozhodnutí nepotřebují,
jsou v textu specifikace označené **návrh**.

Stav: 14 otázek; **vyřešené 6 a 7**. Otázky 8–14 mají výchozí volbu
koordinátora nebo recenze a čekají na schválení uživatelem.

### 1. `prompt` místo `task` uvnitř kroku `ask`
DESIGN §6 píše `ask: { agent, task: "…" }`. Slovo `task` je ale zároveň
typ kroku, takže by ve scénáři znamenalo dvě různé věci.
**Doporučení:** `prompt` (u `ask`, `task` i `image` stejně).

### 2. `schema` uvnitř `ask`/`task`, ne jako vlastnost každého kroku
D1d řadí `schema` mezi vlastnosti libovolného kroku, §6 ho píše uvnitř
`ask`. Smysl má jen u kroků s modelem, který vrací text.
**Doporučení:** uvnitř `ask`/`task` (jak je v §6).

### 3. `budget_usd` místo `budget`
D1d jmenuje vlastnost kroku `budget`, D1a u agenta `limits.budget_usd`.
Jedno slovo pro jednu věc.
**Doporučení:** `budget_usd` všude (jednotka je vidět v názvu).

### 4. Výstup scénáře: `outputs` v hlavičce + `output` jako poslední krok
§5.3 chce, aby scénář deklaroval `outputs`. Spec to řeší hlavičkou
(typy) a krokem `output` (hodnoty), který smí být jen jednou a jen na
konci — ne ve větvích `switch`/`parallel`. Různé výsledky podle větve se
řeší přes `default` a `set`.
**Doporučení:** ano, takto. Scénář se tak čte „nahoře co vrací, dole
odkud to vezme".

### 5. Nové třídy chyb `fail` a `internal`
§5.1 zná `transient`, `schema`, `content`, `budget`, `timeout`, `config`.
Záměrný krok `fail` a chyba samotného frameworku do žádné nepatří, a
callback by je jinak nerozlišil od poruchy poskytovatele.
**Doporučení:** přidat obě.

### 6. Server v `mcp` bez záznamu v `tools` — **vyřešeno**
Původní doporučení („všechny nástroje") odporovalo DESIGN §5.8 (allowlist
podle jména; nový nástroj, který server přidá, agent nesmí uvidět).
**Rozhodnuto podle DESIGN §5.8 (koordinátor, 2026-09-25):** každý server
z `mcp` agenta musí mít v `tools` výslovný seznam; server bez záznamu je
chyba `config`; `validate --dry-run` vypíše nástroje, které server
nabízí. Navíc vlastník v `mcp.yaml` určuje `agents`, `scenarios` a horní
`tools` serveru.

### 7. Literály ve výrazech: `true` / `false` / `null`
D1c říká „výrazy v pythonovském stylu", Python ale píše `True`, `False`,
`None`. Uživatel přitom stejné hodnoty vidí v YAML, JSON a záznamu běhu
jako `true` / `false` / `null`.
**Rozhodnuto (koordinátor, 2026-09-25):** `true` / `false` / `null`.
Platí tedy `x == null` a `str(null)` = `"null"`.

---

Otázky 8–10 vznikly ze spiku (c) (`spikes/expressions/REPORT.md` na větvi
`spike-expressions`). Koordinátor je rozhodl a spec je podle toho napsaná;
při schvalování je můžeš změnit.

### 8. `and` / `or` / `not` jen nad `true` / `false`
Python bere i „pravdivost" jiných hodnot (prázdný text nebo seznam =
nepravda, `0` = nepravda). Spec to zakazuje: `steps.copy.hashtags and …`
je chyba s radou napsat `len(steps.copy.hashtags) > 0`. Ve scénáři je
tak vždy vidět, na co se podmínka ptá.
**Výchozí volba:** jen `true`/`false`. Alternativa: pythonová pravdivost.

### 9. `round` zaokrouhluje půlku od nuly
Python zaokrouhluje bankéřsky (`round(2.5)` = `2`, `round(3.5)` = `4`).
Spec definuje školní zaokrouhlení: `round(2.5)` = `3`, `round(-2.5)` =
`-3` — výslovná odchylka od Pythonu.
**Výchozí volba:** půlka od nuly. Alternativa: jako Python.

### 10. `null` v šabloně je chyba
`{{ x }}`, kde `x` je `null`, se nevloží potichu: chyba v `validate`
(`config`), když to jde poznat předem, jinak za běhu (`expression`).
Výjimka: `null` z výslovného `default` kroku se vloží jako `null` (v textu
jako `null`).
**Výchozí volba:** chyba s výjimkou pro výslovný `default`.
Alternativa: vkládat vždy text `null` (nic neselže, ale chybějící hodnota
může potichu projít až do promptu nebo callbacku).

---

Otázky 11–14 vznikly z nezávislé kontroly (`REVIEW.md`, nálezy B1, B4,
M10). Spec je napsaná podle doporučení.

### 11. Skilly u `ask` se vkládají celé
U `task` nese system prompt jen seznam skillů a tělo si model načte
nástrojem `load_skill` (DESIGN §5.8). `ask` je jedno volání bez nástrojů,
takže `load_skill` v něm nejde. Spec proto u `ask` vkládá těla skillů
celá do system promptu.
**Doporučení:** vkládat celé. Alternativa: agent se skilly v `ask`
zakázat (chyba `config`).

### 12. `dedupe` jako sdílený stav mezi běhy
D2: běhy si nesdílí soubory (kromě `state` a úložiště). `dedupe_key` ale
musí přežít běh, jinak neochrání před dvojí publikací. Spec ho proto dělá
výjimkou jako `state`: každý klíč je samostatný atomicky vytvořený soubor
v `<runs>/_dedupe/`, nikdy jeden sdílený log (souběžné zápisy se tak
neztratí). Stav `started` bez `succeeded` zastaví další běh s výzvou
„ověř ručně".
**Doporučení:** ponechat (hlavní DESIGN to už v D2 a §5.2 uvádí).

### 13. `retry`, `timeout`, `on_error` jen u některých kroků
D1d dává `retry`, `timeout`, `budget`, `on_error` „libovolnému kroku".
Spec je povoluje jen tam, kde mají smysl (tabulka v scenario.md §3):
např. `retry` u `set` nebo `on_error` u `fail` nic neznamená, tak je
zápis chyba `config`, ne tiše ignorované pole.
**Doporučení:** ponechat (hlavní DESIGN to už v D1d upřesňuje odkazem na
spec).

### 14. Porovnání napříč typy u neznámých typů až za běhu
§5.4 říká, že porovnání napříč typy je chyba **validace**. Když ale typ
hodnoty předem znát nejde (např. prvek objektu `details` od Jev), spec
chybu hlásí až za běhu jako třídu `expression`. Typy známé předem
(`inputs`, `schema`, `jev`, `set`) kontroluje `validate`.
**Doporučení:** ponechat.
