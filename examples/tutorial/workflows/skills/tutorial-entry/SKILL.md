---
name: tutorial-entry
description: Format of archive entries — use it whenever you write or check an entry or the archive index
---
The archive has two files, both directly in the allowed folder:

1. `<day>.md` — the entry for one day (`<day>` is the date from the prompt, e.g. `2026-09-25.md`):
   - first line `# Entry <day>`,
   - each sentence of the note on its own line starting with `- `,
   - nothing else (no blank lines, no comments).
2. `index.md` — the archive index:
   - first line `# Index`,
   - for each entry a line `- <day>: <first sentence of the note>`.
