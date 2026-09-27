# Zadání pro redesign GUI AgenCast (pen.dev)

## Co je to za aplikaci

AgenCast je webové rozhraní pro stavbu a spouštění workflow LLM agentů. Uživatel v něm spravuje projekty, v projektu scénáře (posloupnost kroků), agenty, skilly a config, spouští běhy a čte jejich výsledky (kroky, soubory, cena). Rozhraní je technické a husté: hodně identifikátorů, cest, výrazů a YAML, proto se v něm hodně používá neproporcionální písmo. Primárně desktop, ale musí jít ovládat i dotykem na tabletu. Jazyk rozhraní je čeština. Dnes je tmavé; tmavá varianta je povinná, světlá je bonus.

## Co od tebe potřebuji

Knihovnu komponent v pen.dev, kde každá komponenta má stavy a varianty ze seznamu níže, a k tomu jednoduchý celkový rámec obrazovek. Rozložení a vizuální jazyk jsou na tobě. Pojmenuj komponenty a varianty podle názvů v tomto seznamu, ať je můžu mapovat na kód.

Implementace je React + Tailwind, ikony Lucide. Když použiješ Lucide ikony, přenesu je 1:1; jiná sada je možná, ale pak potřebuji SVG.

## Základy

### Písmo

- Proporcionální rodina pro texty a mono rodina pro identifikátory, cesty, výrazy, YAML, JSON a čísla (tabulkové číslice).
- Velikosti, které potřebuji rozlišit: eyebrow (malý štítek verzálkami, např. „KROK 3“, „HLAVIČKA“, „SPUSTIT BĚH“), nadpis stránky/karty, název sekce, tělo, popisek pole, nápověda k poli, meta text na kartách (počty, čas, soubor).

### Barvy

- Tři úrovně povrchu: pozadí stránky, karta/panel, vnořený prvek (pole, čip, blok kódu).
- Tři úrovně textu: primární, sekundární, ztlumený.
- Sémantické stavy, každý má ikonu i barvu (viz Stavy): úspěch, chyba, varování, běží, neutrální/čeká.
- Dvě vyhrazené barvy mimo stavy: jedna pro „proměnná“ (tlačítko vkládání proměnných, položky proměnných), jedna pro „typ kroku“ (ikony typů). Nesmí se plést se stavovými.
- Ztlumení pro: nedostupné, přeskočené, nedošlo, vyjmuto, disabled.

### Ikony

Sada 16 px, jednotný tah. Potřebuji:

- Typy kroků (10): ask (dotaz agentovi), task (agent s nástroji), jev (levné rozhodnutí), image (obrázek), parallel (větve zároveň), switch (jedna z možností), call (jiný scénář), set (výpočet bez LLM), fail (zastavit s chybou), output (výstup scénáře) + „neznámý typ“.
- Stavy (10): úspěch, chyba, přeskočeno, běží, ve frontě, varování, zrušeno, přerušeno, dry-run (jen plán), bez běhu.
- Akce: přidat, smazat, kopírovat, zkopírováno, načíst znovu, zpět (navigace), vrátit zpět (undo), spustit, zavřít, menu ⋯, rozbalit/sbalit, proměnná {}, kód/YAML, klíč (token), hlavička scénáře, šipka toku mezi kroky, otevřít v jiném kontextu ↗, dostupnost projektu (tečka).

## Komponenty

### 1. Tlačítka

Varianty: primární, sekundární, nebezpečná (smazat, přepsat, odebrat), ikonová (jen ikona), pilulka „+ přidat …“ (drobná, u štítku sekce), kulaté (+) na konektoru toku.
Stavy každé: default, hover, focus (klávesnice), disabled, busy s textem („Ukládám…“, „Spouštím…“). S ikonou i bez ikony. Dotyková velikost (44 px) jako varianta.

### 2. Pole formuláře (obal)

Štítek, hvězdička povinného pole, volitelná akce u štítku (např. pilulka „+ přidat“), nápověda, chyba (mono, může být víceřádková, obsahuje ukazatel ^ na místo chyby).
Stavy: default, hover, focus, disabled, invalid, s nápovědou, s chybou, povinné.

### 3. Typy vstupů

- Text jednořádkový; varianta mono (identifikátor, cesta, jméno souboru).
- Textarea; varianta mono (instrukce agenta, JSON, YAML).
- Číslo (max_turns, budget, limity).
- Select (agent, model/alias, API chat/images, kvalita, typ úložiště, filtr scénáře, filtr stavu, typ vstupu).
- Checkbox samostatný i v seznamu (MCP servery a jejich nástroje; disabled s poznámkou „vlastník nepovolil“).
- Radio se dvěma řádky (název + vysvětlení): „Dry-run: jen plán, zdarma“ / „Ostrý běh: volá modely a stojí peníze“.
- Heslo (token serveru).
- Čip s odebráním (skilly agenta) + select „přidat skill“.
- Inline editace klíče (název vstupu, výstupu, otázky, aliasu modelu): stav platný, neplatný formát, „už existuje“; potvrzuje se opuštěním pole.

### 4. Pole pro výraz / šablonu (CodeInput)

Mono pole, jedno- i víceřádkové, s tlačítkem „Vložit proměnnou“ (ikona {}) v barvě proměnných. Stavy tlačítka: default, hover, otevřené, disabled („Žádné dostupné proměnné“ v tooltipu).

- Našeptávač při psaní: seznam položek mono, aktivní položka.
- Nabídka proměnných po kliknutí na {}: skupiny „Vstupy“ a „Krok <id>“, položky mono, aktivní/hover.

### 5. Stavy (StatusIcon, StatusBadge, StatusChip)

Deset stavů z části Ikony. Tři formy: samotná ikona, ikona + text, čip (pilulka s ikonou a textem).
Texty: „úspěch“, „chyba“, „přeskočeno“, „běží“ (ikona pulzuje), „ve frontě“, „varování“, „zrušeno“, „přerušen“, „jen plán (dry-run)“, „bez běhů“.
Čip posledního běhu nese i čas: „✓ před 12 min“, „✗ včera 14:02“, „◌ běží“. Chybový čip s počtem: „3 chyby“ (může být klikací).

### 6. Zpětná vazba a prázdné stavy

- Skeleton: řádek, pilulka, karta.
- Prázdný stav: text + volitelný CLI řádek s příkazem („Projekt zatím nemá žádný scénář.“, „Žádné běhy.“, „Vyber soubor.“).
- Chybový text s ikonou; seznam chyb validace (položky s ikonou, mono text, položka klikací jako odkaz na soubor/krok).
- CLI řádek: příkaz mono + tlačítko kopírovat, stav „Zkopírováno“.
- Lišty: „Server agencast neodpovídá, zkouším znovu…“ (trvalá); konfliktní lišta „Soubor se na disku změnil.“ / „Rozpracované změny v prohlížeči patří ke starší verzi souboru.“ se třemi akcemi (Zobrazit rozdíl, Načíst z disku a zahodit moje změny, Ponechat moje); stavový řádek po přejmenování („Přepsáno: a.yaml, b.yaml“); blok chyby configu (text + seznam + odkaz „Otevřít Config“).
- Stav uložení (SaveNote): „Ukládám…“, „Neuloženo“, „Uloženo ✓ 14:02“, „Načteno z disku (14:02)“, chyba uložení (text z API) + volitelný čip počtu chyb.
- Živý ukazatel v seznamu běhů: „2 běží · 1 ve frontě“.
- Progress bar denní útraty („dnes 1,20 / 5,00 USD“) a pruh pravděpodobnosti 0–1 u odpovědí Jev.

### 7. Menu ⋯, záložky, přepínač, akordeon

- Menu ⋯: spouštěč (ikonový), otevřený seznam, položka default/hover/focus, položka nebezpečná (Smazat, Odebrat z registru).
- Záložky (odkazy): aktivní, neaktivní, hover; varianta s počtem „Volání (3)“.
- Segmentový přepínač se dvěma volbami (Form | YAML, Form | Markdown, Založit nový | Přidat existující): aktivní, neaktivní, disabled s tooltipem („Oprav YAML: řádek 12“).
- Akordeon řádek: titul + shrnutí hodnoty + šipka; zavřený, otevřený, hover. Používá se pro Podmínka (hodnota „vždy“ nebo výraz), Spolehlivost („výchozí“ nebo seznam vyplněných polí), Podrobnosti kroku.
- Sbalitelný strom souborů (složka otevřená/zavřená, soubor, vybraný soubor).

### 8. Modály

Jeden rámec: titul, tělo, akce (primární / sekundární / nebezpečná) + Zrušit nebo Zavřít; stav busy. Obsahové varianty:

- Nový scénář / agent / skill: jméno (mono, kontrola formátu a kolize), popis, model (select).
- Nový projekt: přepínač Založit nový / Přidat existující, jméno, cesta; varianta bez práva zápisu jen s CLI příkazem.
- Přejmenovat (scénář, agent, krok): jméno; u kroku výčet kroků, ve kterých se přepíšou odkazy.
- Smazat (krok, scénář, agent, skill, projekt z registru): text důvodu; varianta „krok čtou jiné kroky“ s výčtem; varianta „smaže i N kroků uvnitř“; varianta odmítnutí z API s důvodem.
- Změnit typ kroku (co zůstane, co se zahodí).
- Neuložené změny při přepnutí režimu: Uložit a přepnout / Zahodit a přepnout.
- Přepsat verzi na disku (nebezpečná akce).
- Rozdíl proti disku: blok mono s řádky − a + barevně, „Texty jsou stejné.“
- Validace scénáře: načítám, seznam chyb, nebo čip „bez chyb“.

### 9. Karta projektu (ProjectCard)

Obsah: ukazatel dostupnosti (tečka + „dostupný“/„nedostupný“), název, cesta (mono), počet scénářů a agentů, útrata dnes, čip posledního běhu (všechny stavy z části 5 včetně „bez běhů“), menu ⋯ (Otevřít, Kopírovat cestu, Odebrat z registru).
Stavy: default, hover, focus, nedostupný (ztlumená, místo počtů text důvodu), skeleton. Zvláštní karta „Přidat projekt“ (default, hover).

### 10. Karta scénáře (ScenarioCard)

Obsah: řetěz ikon typů kroků v pořadí (nejvýš 5, pak čip „+N“), název nebo popis, meta řádek (počet kroků · agenti · vstupy · výstupy · „volatelný“), jméno souboru (mono), čas posledního běhu nebo „bez běhů“, čip posledního běhu NEBO čip chyb validace („2 chyby“), menu ⋯ (Otevřít, Běhy tohoto scénáře, Kopírovat příkaz spuštění, Validovat).
Stavy: default, hover, focus, s chybami validace, bez běhů, s posledním během v každém stavu, volatelný. Zvláštní karta „Nový scénář“ a prázdný stav seznamu.

### 11. Položka seznamu agentů / skillů

Jméno (mono), volitelný ukazatel chyb („✗ 2 chyby“). Stavy: aktivní, neaktivní, hover. Tlačítko „Nový agent“ / „Nový skill“ a prázdný stav.

### 12. Řádek běhu (RunRow) a filtr

Sloupce: stav (ikona + text), run_id (mono), scénář, kdy („před 5 min“, „dnes 14:02“) nebo u běžícího „běží · krok 3/7 navrh“ nebo „ve frontě (2.)“, trvání, cena USD, poznámka (důvod chyby, „jen plán (dry-run)“, „přerušen“, „falešný běh“, callback).
Stavy řádku: běží (živě), ve frontě, úspěch, chyba, přerušen, zrušen, dry-run; hover. Filtry (select scénář, select stav), tlačítko „Načíst další“, prázdný stav s CLI příkazem.

### 13. Karta kroku (StepCard) v editoru

Obsah: pořadové číslo, řádek typu (ikona typu + název typu + id mono), hodnota kroku, volitelně podmínka „když <výraz>“ (mono), ukazatel chyby a text chyby, ovládání karty (menu ⋯: Posunout nahoru/dolů, Vyjmout, Vložit krok nad/pod, Smazat; samostatné tlačítko koš).
Stavy: default, hover, vybraná, focus, s chybou, prázdná hodnota („doplň v panelu“, ztlumeně), s podmínkou, vyjmutá (čeká na vložení jinam), ovládání skryté/zobrazené (hover, fokus; na dotyku trvale ztlumeně).
Varianty hodnoty podle typu (příklady): ask/task „pisatel: „Napiš úvod…““; jev „„Je text hotový?“ · choice; +2 otázky“; image „gpt-image · 1:1 · medium · „Produktová fotka…““; call „→ obrazek · 2 vstupy“; set/output „nadpis, perex“; fail text zprávy; parallel „a ∥ b“; switch „podle steps.jev.volba: ano, ne, jinak“.

### 14. Karta kroku v běhu

Stejná komponenta; místo pořadového čísla ikona stavu, místo podmínky trvání a cena (mono).
Stavy: běží (pulzuje, běžící čas), úspěch, chyba, zrušeno, přeskočeno (ztlumená, důvod v hodnotě), přerušen, nedošlo (ztlumená), varování „Varování: krok selhal, běh pokračoval (on_error: continue).“ jako řádek u karty.

### 15. Hlavičková karta scénáře (HeaderCard)

Ikona místo čísla, štítek „HLAVIČKA“, hodnota „2 vstupy: zadani, pomer · 1 výstup: obrazek“ nebo „bez vstupů · bez výstupů“. Stavy: default, hover, vybraná.

### 16. Kontejnery kroků (parallel, switch, call)

- Hlavní karta kontejneru (odlišitelná od běžné karty), tlačítko sbalit/rozbalit; sbalený stav ukazuje „N kroků“.
- Větev: štítek (název větve / „= hodnota“ / „jinak (default)“), uvnitř seznam karet nebo prázdno; text „jinak: nic“; tlačítko „+ větev“ / „+ případ“. Parallel má větve vedle sebe, switch případy za sebou.
- Call: karta s odkazem „<cíl> otevřít ↗“; v běhu jako kontejner s kroky volaného scénáře.
- Všechny také ve stavech běhu (viz 14).

### 17. Konektor toku a přidání kroku

Šipka mezi kartami; v editoru se na hover/fokus mění v (+); s vyjmutým krokem je (+) zobrazené trvale a zvýrazněné; na konci seznamu (+) trvale + pilulka „+ output“.
Výběr typu (TypePicker): seznam položek „klíčové slovo (mono) + popis“ ve třech skupinách oddělených linkou, aktivní položka, řádek filtru („filtr: as“), „Žádný typ neodpovídá.“, položka „Vložit ‚x‘ sem“.
Popisy typů: ask „jedno volání agenta“, task „agent s nástroji“, jev „levné rozhodnutí Jev“, image „vygenerovat obrázek“, parallel „větve zároveň“, switch „jedna z možností“, call „spustit jiný scénář“, fail „zastavit běh s chybou“, set „spočítat hodnoty bez LLM“.

### 18. Panel (PanelShell) a jeho obsahy

Rámec: eyebrow, titul, tlačítko zavřít, volitelné akce. Obsahy:

- Panel kroku v editoru: select Typ kroku, pole id (s pravidlem formátu), akordeon Podmínka, pole podle typu (Agent select; Prompt šablona; Schéma výstupu JSON; Otázky jako řádky: klíč + otázka + typ + kritéria + odebrat, „+ Přidat otázku“; State; Model; Poměr stran / Kvalita / Rozlišení „pevně, nebo {{ inputs.x }}“; Scénář + Vstupy u call, čip „nevolatelný“ s vysvětlením; Hodnoty u set; Zpráva u fail; Nejvýš tahů; MCP servery checkboxy; Nástroje), akordeon Spolehlivost (timeout, budget_usd, retry, on_error, default, dedupe_key), akordeon Podrobnosti (čipy „Čte z“ / „Výstup čtou“ jako odkazy na kroky, „nic“, odkaz „Otevřít v YAML“), seznam chyb kroku.
- Panel hlavičky: popis, přepínač „Scénář smí volat jiný scénář krokem call“ s vysvětlením, Vstupy a Výstupy jako řádky (jméno inline, typ select, popis, výchozí hodnota, odebrat; „+ Přidat vstup“ / „+ Přidat výstup“).
- Panel spuštění („SPUSTIT BĚH“): vstupy podle typu (text, číslo, checkbox, JSON, disabled „soubor předá jen krok call“), radio Dry-run / Ostrý běh, tabulka limitů (na běh, z toho obrázky, čas běhu, dnes utraceno / limit), varování („Máš neuložené změny: běh použije verzi na disku.“, „Scénář má vstup typu file…“), chyba API, tlačítko „Spustit dry-run“ / „Spustit ostrý běh“ / „Spouštím…“.
- Panel kroku v běhu: řádek stavu (badge + trvání + cena + „3 tahy · 2 volání nástrojů“), text přeskočení / varování / chyba, záložky podle typu (Prompt, Odpověď, Výstup, Volání (n), Nástroje, Obrázek, Soubory), obsahy: blok kódu (mono, JSON/Markdown), odpovědi Jev (klíč, hodnota, pruh 0–1), položka volání (pokus · tah · alias → model; provider · finish_reason · HTTP; trvání · tokeny · cena; chybová položka s „↻“ při opakování), položka nástroje (tah · server.tool; trvání; odkaz na soubor; varianty „nepovolený“ / „neplatné argumenty“ / „nástroj vrátil chybu“), obrázek, seznam souborů, prázdný stav „Nic k zobrazení.“

### 19. Editory textu

- YAML editor: čísla řádků, zvýrazněný rozsah vybraného kroku, řádek s chybou, jen ke čtení s hintem „Soubor x, jen ke čtení.“, hint „Upravuješ přímo soubor… Uloží se až tlačítkem Uložit.“
- Markdown editor agenta/skillu (mono textarea) a náhled Markdownu.
- Blok kódu jen ke čtení (výstup kroku, soubory běhu), obrázek běhu, report v rámu.

### 20. Formuláře agenta, skillu a configu

- Agent: popis, model (select aliasů + nápověda „Alias z config.yaml, nikdy konkrétní id modelu.“), skilly (čipy + přidat), MCP (server checkbox a k němu checkboxy nástrojů; poznámky „(vlastník nepovolil)“, „server nástroje neomezuje“), limity (max_turns povinné podmíněně s textem „Povinné: agent má MCP server.“, budget_usd, timeout), Instrukce (velká textarea), seznam „Používá“ (odkazy na scénáře). Skill: Markdown + „používají“.
- Config: sekce Modely (řádky aliasů: alias inline, id modelu, API select chat/images, kvalita select jen u images, structured_output, max_tokens, smazat alias disabled s důvodem „Alias používá pisatel: smazat nejde.“, poznámka „používají 2 agenti“; „+ alias“), Jev model, Úložiště (type select + pole; pole *_env s ukazatelem „nastavena na serveru“ / „na serveru chybí“ / „server o proměnné zatím neví“), Limity, Proměnné, MCP servery jen ke čtení (agenti, scénáře, nástroje; „mění se v YAML režimu“, „Projekt nemá mcp.yaml.“), stav „config.yaml neprošel kontrolou, oprav ho v YAML“.

## Celkový rámec (obrazovky)

Stačí jednoduchý rámec, kam se komponenty skládají; detailní layout je na tobě.

1. Token serveru: karta s polem hesla, nápovědou, chybou „Token serveru nesedí.“, Uložit.
2. Projekty: nadpis, podtitul, cesta registru (mono), načíst znovu, mřížka karet projektů.
3. Projekt: navigace zpět, název, cesta (mono), útrata dnes + progress denního limitu, limity běhu, čip „N chyb“ s rozbalovacím seznamem chyb, načíst znovu; záložky Scénáře · Agenti · Config · Skilly · Běhy; obsah záložky (mřížka karet / seznam + detail / formulář / tabulka běhů).
4. Editor scénáře: zpět („projekt / Scénáře“), drobečky cesty přes call, název (mono), popis, přepínač Form | YAML, stav uložení, Přejmenovat, Smazat, Vrátit zpět, Spustit, Uložit; konfliktní lišta; sloupec karet kroků s konektory; panel (krok / hlavička / spuštění); YAML režim.
5. Detail běhu: zpět („projekt / Běhy“), scénář (mono, odkaz) + run_id, badge stavu (u chyby „chyba: <důvod>“), čip „falešný běh“, trvání · cena, řádek vstupů („zadani = „…““), záložky Kroky · Souhrn · Report · Soubory, checkbox „sledovat běh“, hint pro přerušený běh, stavový řádek „Běh skončil: úspěch“; obsah: sloupec karet kroků v běhu + panel, nebo „Běh čeká ve frontě.“, nebo dry-run s plánem, souhrn Markdown, report, strom souborů + prohlížeč.
6. Stránka „Tahle adresa v GUI neexistuje.“ s odkazem na Projekty.

## Pravidla, která musí zůstat

- Stav je vždy ikona + text, nikdy jen barva.
- Identifikátory, cesty, výrazy, YAML, JSON a čísla v mono.
- Karta kroku v editoru a v běhu je jedna komponenta; liší se jen obsahem místa pro číslo a pravé části.
- Barva proměnných a barva typů kroků nesmí kolidovat se stavovými barvami.
- Dotykové cíle 44 px na dotykových zařízeních.
- Vše česky, texty ber z tohoto seznamu.

## Výstup

Jeden .pen soubor s knihovnou komponent (varianty = stavy) a rámci obrazovek. Ke každé komponentě název z tohoto seznamu.
