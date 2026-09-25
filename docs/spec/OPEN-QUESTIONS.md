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
**Doporučení:** `true` / `false` / `null` (jeden zápis všude).
