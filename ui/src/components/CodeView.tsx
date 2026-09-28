// `YamlEditor` ke čtení (§3, §4.5): čísla řádků, chybné řádky a barvy výrazů.
import { useEffect, useRef, useState } from "react";
import { Check, Copy, FileCode2 } from "lucide-react";
import { t } from "../i18n";
import type { ErrorItem } from "../types";
import { CodeHead, copyBtn, ErrorList } from "./ui";

const tokens = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|((?<![\w.])(?:inputs|steps|params)\.[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[(?:-?\d+|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\])*)|(\b(?:not\s+in|and|or|not|in)\b|==|!=|<=|>=|[+\-*/%<>])/g;

function colorExpression(text: string) {
  const parts: React.ReactNode[] = [];
  let end = 0;
  for (const match of text.matchAll(tokens)) {
    parts.push(text.slice(end, match.index));
    parts.push(match[1] ? match[0] : <span key={match.index} className={match[2] ? "text-variable" : "text-type"}>{match[0]}</span>);
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

/** Klíče, komentáře, proměnné a operátory mají vlastní barvu (§4.5). */
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

/** Kontext výrazů a víceřádkových hodnot podle odsazení YAML. */
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

export function CodeView({ text, file, errors = [], focus }: {
  text: string;
  /** Soubor ve `workflows/` (nápověda pod blokem). */
  file: string;
  errors?: ErrorItem[];
  /** Řádky (od 1) k podbarvení a posunutí do pohledu. */
  focus?: [number, number];
}) {
  const lines = text.replace(/\n$/, "").split("\n");
  const contexts = lineContexts(lines);
  const bad = new Set(errors.map((e) => e.line).filter(Boolean));
  const ref = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (focus) ref.current?.querySelector(`[data-line="${focus[0]}"]`)?.scrollIntoView({ block: "center" });
  }, [focus]);
  return (
    <div>
      <div className="overflow-hidden rounded-[var(--radius-panel)] bg-surface">
        <CodeHead icon={FileCode2} name={file} chip={t("code.readOnly")} />
        <div ref={ref} className="scroll-thin overflow-auto bg-nested py-4 font-mono text-[13px] leading-[27px] focus-visible:ring-2 focus-visible:ring-accent" tabIndex={0} role="region" aria-label={file}>
          <table className="border-collapse">
            <tbody>
              {lines.map((l, i) => {
                const n = i + 1;
                const hi = focus && n >= focus[0] && n <= focus[1];
                return (
                  <tr key={i} data-line={n} className={bad.has(n) ? "border-l-2 border-error bg-error/10" : hi ? "border-l-2 border-accent bg-surface-active" : ""}>
                    <td className={`w-[58px] pr-3.5 pl-4 text-right align-top font-mono text-xs select-none ${hi ? "text-fg-secondary" : "text-fg-muted"}`}>{n}</td>
                    <td className="pr-4 whitespace-pre"><Line text={l} {...contexts[i]} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 p-3.5">
          <p className="font-mono text-[11px] text-fg-muted">{t("code.hint", { file: `workflows/${file}` })}</p>
          <button type="button" className={copyBtn} onClick={async () => {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}>{copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}{copied ? t("common.copied") : t("common.copy")}</button>
        </div>
      </div>
      {errors.length > 0 && <div className="mt-3"><ErrorList errors={errors} /></div>}
    </div>
  );
}

/** Řádky kroku `id` v textu scénáře: od `- id: <id>` po další položku se stejným nebo menším odsazením. */
export function stepLines(text: string, id: string): [number, number] | undefined {
  const lines = text.split("\n");
  const start = lines.findIndex((l) => new RegExp(`^\\s*-\\s+id:\\s*["']?${id}["']?\\s*(#.*)?$`).test(l));
  if (start < 0) return undefined;
  const indent = lines[start].search(/-/);
  let end = start + 1;
  while (end < lines.length && (lines[end].trim() === "" || lines[end].search(/\S/) > indent)) end++;
  return [start + 1, end];
}
