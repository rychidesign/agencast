---
name: hashtag-check
description: Kontrola seznamu hashtagů k příspěvku podle pravidel značky (počet, tvar, zakázané).
---
# Kontrola hashtagů

Pravidla:
- Nejvýš 5 hashtagů.
- Jen malá písmena, bez diakritiky.
- Zakázané: #follow4follow, #like4like, #f4f, #instagood.

Výstup vždy v tomto tvaru:
```
VERDIKT: OK | NEOK
PORUŠENÍ: <seznam porušených pravidel nebo "žádná">
OPRAVENO: <opravený seznam hashtagů>
```
