---
name: tutorial-zapis
description: Formát zápisu v archivu — použij vždy, když zápis nebo obsah archivu zapisuješ či kontroluješ
---
Archiv má dva soubory, oba přímo v povolené složce:

1. `<den>.md` — zápis jednoho dne (`<den>` je datum ze zadání, např. `2026-09-25.md`):
   - první řádek `# Zápis <den>`,
   - každá věta poznámky na vlastním řádku, který začíná `- `,
   - nic dalšího (žádné prázdné řádky, žádný komentář).
2. `obsah.md` — obsah archivu:
   - první řádek `# Obsah`,
   - pro každý zápis řádek `- <den>: <první věta poznámky>`.
