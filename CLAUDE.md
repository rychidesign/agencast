# multiagent-workflows — pokyny pro agenty

Uživatel je rychidesign, komunikuje česky. **Odpovídej česky.** Dokumentaci
i komentáře piš česky; názvy v kódu anglicky.

## Nejdřív si přečti
`docs/DESIGN.md` — závazná rozhodnutí (R1–R7, D1–D5) a pevná pravidla
(§5). Co je tam rozhodnuto, neotvírej znovu bez souhlasu uživatele. Co je
označeno OTEVŘENO, rozhodují spiky, ne názor.

Závazná je i `docs/spec/` (formáty v1, schválena uživatelem 2026-09-25;
zmražená podle DESIGN §5.9 — rozšiřovat jen zpětně kompatibilně). Rozpor
spec × DESIGN hlas koordinátorovi, nerozhoduj ho sám.

## Rozdělení repozitáře
- `framework/` — jádro. Sem patří kód frameworku, jeho testy a
  konformační scénáře.
- `workflows/` — vrstva uživatele (agenti, scénáře, skilly, konfigurace).
  Framework ji čte, nikdy do ní negeneruje kód. `config.yaml`, `mcp.yaml`
  a `commands.yaml` mění jen uživatel.
- `spikes/<name>/` — experiment s jasnou otázkou a časovým limitem. Výstup
  je `REPORT.md`: verdikt *funguje / nefunguje / funguje s výhradou* +
  naměřená fakta (příkazy, odpovědi, latence, cena). Kód spiku se do
  `framework/` nepřenáší, přenáší se poznatky.

## Pravidla
- Tajné klíče jen z proměnných prostředí (`OPENROUTER_API_KEY`,
  `MODAL_TOKEN_*`, …) nebo z `.env`, který je v `.gitignore`. **Nikdy je
  nevypisuj, neloguj ani nečti z cizích konfigurací** (např.
  `~/.local/share/opencode/auth.json`).
- Útrata: spiky mají rozpočet v centech, používej levné modely a malé
  vstupy. Před čímkoliv dražším než ~1 USD se zeptej.
- Commituj na větvi, kde pracuješ. **Push, mazání a cokoliv nevratné jen
  se souhlasem uživatele.**
- Nic nesmí selhat potichu: chybu, kterou nedokážeš vyřešit, popiš v
  reportu i s přesnou hláškou.
- Externí fakta (API, parametry knihoven) ověřuj v aktuální dokumentaci a
  uveď zdroj; nepiš je z paměti.
