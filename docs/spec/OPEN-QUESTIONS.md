# Otevřené otázky ke specifikaci v1

Rozhodnutí, která patří uživateli: buď se odchylují od znění DESIGN.md,
nebo mění bezpečnost či syntaxi, kterou uživatel píše. Ke každé je
doporučení — **specifikace je už napsaná podle doporučení**, takže
„souhlasím" znamená žádnou změnu. Drobnosti, které rozhodnutí nepotřebují,
jsou v textu specifikace označené **návrh**.

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

### 6. Server v `mcp` bez záznamu v `tools` = všechny jeho nástroje
Alternativa: u každého serveru vyžadovat výslovný seznam nástrojů.
Bezpečnější, ale ukecanější; už uvedení serveru v `mcp` je výslovné
povolení a `--dry-run` vypíše výsledný seznam nástrojů.
**Doporučení:** ponechat „všechny" a vypisovat v `--dry-run`. Pokud
chceš přísnější variantu (povinný seznam), je to změna jednoho pravidla.

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
