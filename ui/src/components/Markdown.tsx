// Malý renderer Markdownu pro summary.md: nadpisy, tabulky, odrážky, odstavce, **tučně**, `kód`.
// Vrací React prvky (žádné innerHTML), takže obsah běhu nemůže vložit HTML.
import type { ReactNode } from "react";
import { CodeBlock } from "./ui";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i} className="text-fg">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return <code key={i} className="rounded bg-nested px-1 font-mono text-[13px] text-fg">{part.slice(1, -1)}</code>;
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link && /^(https?:\/\/|mailto:|\/|#|\.\.?\/)/.test(link[2]))
      return <a key={i} href={link[2]} className="text-accent underline hover:text-fg">{link[1]}</a>;
    return part;
  });
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    const h = /^(#{1,3})\s+(.*)$/.exec(l);
    if (l.startsWith("```")) {
      i++;
      const code: string[] = [];
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      if (i < lines.length) i++;
      const lang = l.slice(3).trim();
      out.push(<CodeBlock key={i} text={code.join("\n")} title={lang || undefined} yaml={/^ya?ml$/i.test(lang)} />);
    } else if (h) {
      const cls = ["text-lg font-semibold", "mt-6 text-base font-semibold", "mt-4 text-sm font-semibold"][h[1].length - 1];
      const Tag = (["h2", "h3", "h4"] as const)[h[1].length - 1];
      out.push(<Tag key={i} className={`${cls} text-fg`}>{inline(h[2])}</Tag>);
      i++;
    } else if (l.startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
      const [head, , ...body] = rows;
      out.push(
        <div key={i} className="overflow-x-auto focus-visible:ring-2 focus-visible:ring-accent" tabIndex={0}>
          <table className="text-[13px]">
            <thead><tr>{cells(head).map((c, j) => <th key={j} className="px-2 py-1 text-left font-semibold text-fg-muted">{inline(c)}</th>)}</tr></thead>
            <tbody>
              {body.map((r, k) => <tr key={k} className="odd:bg-nested">{cells(r).map((c, j) => <td key={j} className={`px-2 py-1 align-top ${c.length < 12 ? "whitespace-nowrap" : ""}`}>{inline(c)}</td>)}</tr>)}
            </tbody>
          </table>
        </div>,
      );
    } else if (/^\s*[-*]\s/.test(l)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s/, ""));
      out.push(<ul key={i} className="list-disc space-y-1 pl-5 text-fg-secondary">{items.map((it, j) => <li key={j}>{inline(it)}</li>)}</ul>);
    } else if (l.trim()) {
      const para = [lines[i++]];
      while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|\||\s*[-*]\s|```)/.test(lines[i])) para.push(lines[i++]);
      out.push(<p key={i} className="text-fg-secondary">{inline(para.join(" "))}</p>);
    } else i++;
  }
  return <div className="space-y-3 text-sm leading-6 text-fg-secondary">{out}</div>;
}
