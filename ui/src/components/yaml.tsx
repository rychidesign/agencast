// YAML highlighting (§4.5) for `YamlEditor`, `DiffModal`, `CodeBlock` and expression fields; step lines in the scenario text.

const tokens = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|((?<![\w.])(?:inputs|steps|params)\.[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[(?:-?\d+|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\])*)|(\b(?:not\s+in|and|or|not|in)\b|==|!=|<=|>=|[+\-*/%<>])/g;

function colorExpression(text: string) {
  const parts: React.ReactNode[] = [];
  let end = 0;
  for (const match of text.matchAll(tokens)) {
    parts.push(text.slice(end, match.index));
    parts.push(match[1] ? match[0] : <span key={match.index} className={match[2] ? "text-variable" : "text-success"}>{match[0]}</span>);
    end = match.index + match[0].length;
  }
  parts.push(text.slice(end));
  return parts;
}

function commentAt(text: string) {
  let quote = "";
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quote) {
      if (c === "\\" && quote === '"') i++;
      else if (c === quote) {
        if (quote === "'" && text[i + 1] === "'") i++;
        else quote = "";
      }
    } else if (c === "'" || c === '"') quote = c;
    else if (c === "#" && (i === 0 || /\s/.test(text[i - 1]))) return i;
  }
  return text.length;
}

function colorValue(text: string, expression: boolean, comments = true) {
  const limit = comments ? commentAt(text) : text.length;
  const value = text.slice(0, limit);
  const parts: React.ReactNode[] = [];
  const templates = /\{\{.*?\}\}/g;
  let end = 0;
  for (const match of value.matchAll(templates)) {
    parts.push(expression ? colorExpression(value.slice(end, match.index)) : value.slice(end, match.index));
    parts.push(<span key={`open-${match.index}`} className="text-fg-muted">{"{{"}</span>);
    parts.push(colorExpression(match[0].slice(2, -2)));
    parts.push(<span key={`close-${match.index}`} className="text-fg-muted">{"}}"}</span>);
    end = match.index + match[0].length;
  }
  const tail = value.slice(end);
  if (expression && end === 0) {
    const quoted = /^(\s*)(["'])([\s\S]*)\2(\s*)$/.exec(tail);
    if (quoted) parts.push(quoted[1], quoted[2], colorExpression(quoted[3]), quoted[2], quoted[4]);
    else parts.push(colorExpression(tail));
  } else parts.push(expression ? colorExpression(tail) : tail);
  if (limit < text.length) parts.push(<span key="comment" className="text-fg-muted">{text.slice(limit)}</span>);
  return parts;
}

/** Keys, comments, variables and operators each have their own color (§4.5). */
export function Line({ text, expression = false, block = false }: { text: string; expression?: boolean; block?: boolean }) {
  if (block) return <span className="text-fg-secondary">{colorValue(text, false, false)}</span>;
  if (/^\s*#/.test(text)) return <span className="text-fg-muted">{text}</span>;
  const m = /^(\s*(?:-\s+)?)([\w.-]+:)(.*)$/.exec(text);
  if (!m) return <span className="text-fg-secondary">{colorValue(text, expression, false)}</span>;
  return (
    <>
      <span className="text-fg-secondary">{m[1]}</span>
      <span className="text-fg">{m[2]}</span>
      <span className="text-fg-secondary">{colorValue(m[3], expression || m[2] === "when:")}</span>
    </>
  );
}

/** Context of expressions and multi-line values by YAML indentation. */
export function lineContexts(lines: string[]) {
  const parents: { indent: number; key: string }[] = [];
  let blockIndent = -1;
  return lines.map((line) => {
    const lineIndent = line.search(/\S/);
    if (blockIndent >= 0 && (lineIndent < 0 || lineIndent > blockIndent)) return { expression: false, block: true };
    blockIndent = -1;
    const match = /^(\s*)(?:-\s+)?([\w.-]+):(.*)$/.exec(line);
    if (!match) return { expression: false, block: false };
    const indent = match[1].length;
    while (parents.length && parents[parents.length - 1].indent >= indent) parents.pop();
    const parent = parents[parents.length - 1]?.key;
    const expression = match[2] === "when" || (match[2] === "value" && parent === "switch") || parent === "set";
    if (!match[3].trim()) parents.push({ indent, key: match[2] });
    if (/^\s*[|>][-+]?(?:\s*(?:#.*)?)?$/.test(match[3])) blockIndent = indent;
    return { expression, block: false };
  });
}

/** Highlighted lines (§4.5); in Markdown (`agents/*.md`, `SKILL.md`) only the YAML frontmatter between `---` lines. */
export function highlight(lines: string[], markdown = false) {
  let from = 0, to = lines.length;
  if (markdown) {
    const close = lines[0] === "---" ? lines.indexOf("---", 1) : -1;
    [from, to] = close > 0 ? [1, close] : [0, 0];
  }
  const contexts = lineContexts(lines.slice(from, to));
  return lines.map((l, i) => i >= from && i < to
    ? <Line text={l || " "} {...contexts[i - from]} />
    : <span className="text-fg-secondary">{l || " "}</span>);
}

/** Value of an expression field (`when`, `set`, `switch.value`) or a template in the step form. */
export function Expression({ text, template = false }: { text: string; template?: boolean }) {
  return <>{template ? colorValue(text, false, false) : colorExpression(text)}</>;
}

/** Lines of step `id` in the scenario text: from `- id: <id>` to the next item with the same or smaller indentation. */
export function stepLines(text: string, id: string): [number, number] | undefined {
  const lines = text.split("\n");
  const start = lines.findIndex((l) => new RegExp(`^\\s*-\\s+id:\\s*["']?${id}["']?\\s*(#.*)?$`).test(l));
  if (start < 0) return undefined;
  const indent = lines[start].search(/-/);
  let end = start + 1;
  while (end < lines.length && (lines[end].trim() === "" || lines[end].search(/\S/) > indent)) end++;
  return [start + 1, end];
}
