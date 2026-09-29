// `YamlEditor` (§3, §4.5): textarea over highlighted text, line numbers,
// erroneous lines and an error list linking to the line. `ConflictBar` and the diff (§4.6).
import { useEffect, useId, useRef, useState } from "react";
import { Check, FileCode2, GitCompareArrows, RotateCcw, TriangleAlert } from "lucide-react";
import { t } from "../i18n";
import { lineDiff, type Conflict } from "../textfile";
import type { ErrorItem } from "../types";
import { Modal } from "./form";
import { btn, ErrorList } from "./ui";
import { highlight } from "./yaml";

const LINE_PX = 27;
const PAD_PX = 16;

export function YamlEditor({ text, onChange, file, errors, focus, onCaretLine, label, readOnly = false }: {
  text: string; onChange: (t: string) => void; file: string; errors: ErrorItem[];
  /** Lines (from 1) to highlight and for the cursor (Form → YAML keeps the selected step). */
  focus?: [number, number]; onCaretLine?: (line: number) => void; label?: string; readOnly?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const hintId = useId();
  const errorsId = useId();
  const [flash, setFlash] = useState(focus);
  const [position, setPosition] = useState<[number, number]>([1, 1]);
  const lines = text.split("\n");
  const colored = highlight(lines, file.endsWith(".md"));
  const bad = new Set(errors.map((e) => e.line).filter(Boolean));

  const goTo = (line: number) => {
    const el = area.current;
    if (!el) return;
    const offset = lines.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
    el.focus({ preventScroll: true });
    el.setSelectionRange(offset, offset);
    setPosition([line, 1]);
    if (box.current) box.current.scrollTop = Math.max(0, (line - 1) * LINE_PX + PAD_PX - box.current.clientHeight / 3);
  };
  useEffect(() => {
    if (!focus) return;
    goTo(focus[0]);
    setFlash(focus);
    const timer = setTimeout(() => setFlash(undefined), 1500);
    return () => clearTimeout(timer);
    // only when switching to YAML / changing the step
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.[0]]);

  const caret = () => {
    const el = area.current;
    if (!el) return;
    const before = el.value.slice(0, el.selectionStart);
    const line = before.split("\n").length;
    setPosition([line, before.length - before.lastIndexOf("\n")]);
    onCaretLine?.(line);
  };
  return (
    // design 11 (measured from .pen): r16, toolbar p 14 18 with a line, 27 px row (13/19 + 4 + 4), mono 11 footer
    <div className="overflow-hidden rounded-[var(--radius-panel)] bg-surface focus-within:ring-1 focus-within:ring-accent">
      <div className="flex items-center gap-2.5 border-b border-line px-[18px] py-3.5">
        <FileCode2 className="size-[18px] text-fg-secondary" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-mono text-[13px] text-fg">{file}</span>
        <span className="rounded-[6px] bg-nested px-[9px] py-[5px] font-mono text-[11px] leading-4 text-fg-secondary ring-1 ring-line">{file.endsWith(".md") ? "Markdown" : "YAML"}</span>
      </div>
      <div ref={box} className="max-h-[calc(100vh-14rem)] scroll-thin overflow-auto bg-nested font-mono text-[13px] leading-[27px]">
        <div className="flex min-w-max">
          <div aria-hidden className="min-w-[58px] py-4 pr-3.5 pl-4 text-right font-mono text-xs leading-[27px] text-fg-muted select-none">
            {lines.map((_, i) => (
              <div key={i} data-testid={bad.has(i + 1) ? `yaml-line-${i + 1}` : undefined}
                className={bad.has(i + 1) ? "-ml-4 border-l-2 border-error bg-error/10 pl-[14px] text-error" : flash && i + 1 >= flash[0] && i + 1 <= flash[1] ? "-ml-4 border-l-2 border-accent bg-surface-active pl-[14px] text-fg-secondary" : ""}>{i + 1}</div>
            ))}
          </div>
          <div className="relative flex-1 py-4 pr-4">
            <pre aria-hidden className="pointer-events-none whitespace-pre">
              {colored.map((line, i) => {
                const n = i + 1;
                const hi = flash && n >= flash[0] && n <= flash[1];
                return <div key={i} className={bad.has(n) ? "bg-error/10" : hi ? "bg-surface-active transition-colors" : ""}>{line}</div>;
              })}
            </pre>
            <textarea
              ref={area} value={text} readOnly={readOnly} wrap="off" spellCheck={false} aria-label={label ?? file}
              aria-describedby={`${hintId} ${errorsId}`} aria-invalid={errors.length > 0 || undefined}
              onChange={(e) => onChange(e.target.value)} onSelect={caret} onKeyUp={caret} onClick={caret}
              className="absolute inset-0 resize-none overflow-hidden bg-transparent py-4 pr-4 whitespace-pre text-transparent caret-fg outline-none selection:bg-accent/30"
            />
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-[18px] py-2.5 text-xs text-fg-muted">
        <p id={hintId}>{t(readOnly ? "code.hint" : "code.editHint", { file: `workflows/${file}` })}</p>
        <span className="font-mono text-[11px] whitespace-nowrap">{t("code.position", { line: position[0], column: position[1] })}</span>
      </div>
      <div id={errorsId} className={errors.length ? "border-t border-line p-4" : ""}>
        <ul className="space-y-2">
          {errors.map((e, i) => (
            <li key={i}>
              {e.line ? (
                <button type="button" onClick={() => goTo(e.line!)} className="text-left hover:underline">
                  <ErrorList errors={[{ ...e, message: `${t("code.line", { n: e.line })}${e.step ? ` · ${e.step}` : ""} · ${e.message}` }]} />
                </button>
              ) : <ErrorList errors={[{ ...e, message: `${e.step ? `${e.step} · ` : ""}${e.message}` }]} />}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** Sticky bar above the cards (§4.6): the file changed on disk and the GUI holds unsaved changes. */
export function ConflictBar({ conflict, onDiff, onReload, onKeep, inHeader = false }: {
  conflict: Conflict; onDiff: () => void; onReload: () => void; onKeep: () => void;
  /** In the sticky header of the scenario editor: the bar stays above the panel. */
  inHeader?: boolean;
}) {
  return (
    // design 11 (measured from .pen): warning surface, 3 px left bar, r8, p 20, gaps 16; title 15, description 13, actions below the text
    <div role="alert" data-testid="conflict-bar" className={`${inHeader ? "w-full" : "sticky top-[calc(var(--page-header-h,0px)+0.5rem)] z-10 mb-4"} space-y-4 rounded-control border-l-[3px] border-warning bg-[color-mix(in_srgb,var(--color-warning)_14%,var(--color-canvas))] p-5`}>
      <div className="space-y-1">
        <p className="flex items-center gap-3 text-[15px] leading-[23px] text-warning"><TriangleAlert className="size-4 shrink-0" aria-hidden />{t("conflict.title")}</p>
        <p className="text-[13px] leading-5 text-fg-secondary">{t(conflict.stale ? "conflict.stale" : "conflict.changed")}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        <button type="button" className={btn.secondary} onClick={onDiff}><GitCompareArrows className="size-4" aria-hidden />{t("conflict.diff")}</button>
        <button type="button" className={btn.danger} onClick={onReload}><RotateCcw className="size-4" aria-hidden />{t("conflict.reload")}</button>
        <button type="button" className={btn.secondary} onClick={onKeep}><Check className="size-4" aria-hidden />{t("conflict.keep")}</button>
      </div>
    </div>
  );
}

/** Line-by-line diff of two texts (only changes with two lines of context); `markdown` highlights only the frontmatter. */
export function DiffModal({ title, before, after, onClose, note, markdown = false }: {
  title: string; before: string; after: string; onClose: () => void; note?: string; markdown?: boolean;
}) {
  const diff = lineDiff(before, after);
  const near = (i: number) => diff.slice(Math.max(0, i - 2), i + 3).some((d) => d.op !== " ");
  // diff rows go in order: "-" and " " from `before`, "+" and " " from `after` (as in `lineDiff`)
  const [old, now] = [before, after].map((s) => highlight(s.replace(/\n$/, "").split("\n"), markdown));
  let x = 0, y = 0;
  const colored = diff.map((d) => d.op === "+" ? now[y++] : d.op === "-" ? old[x++] : (y++, old[x++]));
  return (
    <Modal title={title} onCancel={onClose} actions={[]} cancelLabel={t("common.close")}>
      {note && <p>{note}</p>}
      <pre className="max-h-[60vh] scroll-thin overflow-auto rounded-[var(--radius-control)] bg-nested p-3 font-mono text-[13px] leading-5">
        {diff.every((d) => d.op === " ") && <span className="text-fg-muted">{t("conflict.same")}</span>}
        {diff.map((d, i) => near(i) && (
          <div key={i} className={d.op === "+" ? "bg-success/10" : d.op === "-" ? "bg-error/10" : "opacity-60"}>
            <span className={d.op === "+" ? "text-success" : d.op === "-" ? "text-error" : "text-fg-muted"}>{d.op} </span>{colored[i]}
          </div>
        ))}
      </pre>
    </Modal>
  );
}
