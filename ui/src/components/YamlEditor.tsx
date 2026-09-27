// `YamlEditor` (§3, §4.5): textarea nad zvýrazněným textem, čísla řádků,
// chybné řádky a seznam chyb s odkazem na řádek. `ConflictBar` a rozdíl (§4.6).
import { useEffect, useId, useRef, useState } from "react";
import { FileCode2, TriangleAlert } from "lucide-react";
import { t } from "../i18n";
import { lineDiff, type Conflict } from "../textfile";
import type { ErrorItem } from "../types";
import { Line } from "./CodeView";
import { Modal } from "./form";
import { btn, ErrorList } from "./ui";

const LINE_PX = 24;
const PAD_PX = 16;

export function YamlEditor({ text, onChange, file, errors, focus, onCaretLine, label, readOnly = false }: {
  text: string; onChange: (t: string) => void; file: string; errors: ErrorItem[];
  /** Řádky (od 1) k podbarvení a kurzoru (Form → YAML drží vybraný krok). */
  focus?: [number, number]; onCaretLine?: (line: number) => void; label?: string; readOnly?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const hintId = useId();
  const errorsId = useId();
  const [flash, setFlash] = useState(focus);
  const [position, setPosition] = useState<[number, number]>([1, 1]);
  const lines = text.split("\n");
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
    // jen při přepnutí do YAML / změně kroku
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
    <div className="overflow-hidden rounded-[var(--radius-panel)] bg-surface ring-1 ring-line focus-within:ring-accent">
      <div className="flex h-12 items-center gap-2.5 border-b border-line px-[18px]">
        <FileCode2 className="size-[18px] text-fg-secondary" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-mono text-[13px] text-fg">{file}</span>
        <span className="rounded-md bg-nested px-2 py-1 font-mono text-[11px] text-fg-secondary ring-1 ring-line">{file.endsWith(".md") ? "Markdown" : "YAML"}</span>
      </div>
      <div ref={box} className="max-h-[calc(100vh-14rem)] overflow-auto bg-nested font-mono text-[13px] leading-6">
        <div className="flex min-w-max">
          <div aria-hidden className="py-4 pr-3 pl-4 text-right font-mono text-xs text-fg-muted select-none">
            {lines.map((_, i) => (
              <div key={i} data-testid={bad.has(i + 1) ? `yaml-line-${i + 1}` : undefined}
                className={bad.has(i + 1) ? "-ml-4 border-l-2 border-error bg-error/10 pl-[14px] text-error" : flash && i + 1 >= flash[0] && i + 1 <= flash[1] ? "-ml-4 border-l-2 border-accent bg-surface-active pl-[14px]" : ""}>{i + 1}</div>
            ))}
          </div>
          <div className="relative flex-1 py-4 pr-4">
            <pre aria-hidden className="pointer-events-none whitespace-pre">
              {lines.map((l, i) => {
                const n = i + 1;
                const hi = flash && n >= flash[0] && n <= flash[1];
                return <div key={i} className={bad.has(n) ? "bg-error/10" : hi ? "bg-surface-active transition-colors" : ""}><Line text={l || " "} /></div>;
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
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-2 text-xs text-fg-muted">
        <p id={hintId}>{t(readOnly ? "code.hint" : "code.editHint", { file: `workflows/${file}` })}</p>
        <span className="font-mono whitespace-nowrap">{t("code.position", { line: position[0], column: position[1] })}</span>
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

/** Sticky pruh nad kartami (§4.6): soubor se na disku změnil a GUI drží neuložené změny. */
export function ConflictBar({ conflict, onDiff, onReload, onKeep, inHeader = false }: {
  conflict: Conflict; onDiff: () => void; onReload: () => void; onKeep: () => void;
  /** V přilepené hlavičce (editor scénáře): přilepený panel se pak řadí pod pruh, nepřekryje ho. */
  inHeader?: boolean;
}) {
  return (
    <div role="alert" data-testid="conflict-bar" className={`${inHeader ? "w-full" : "sticky top-[calc(var(--page-header-h,0px)+0.5rem)] z-10 mx-auto mb-4 max-w-4xl"} flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] bg-warning/10 px-4 py-3 ring-1 ring-warning/40`}>
      <TriangleAlert className="size-5 shrink-0 text-warning" aria-hidden />
      <div className="min-w-40 flex-1"><strong className="text-sm font-semibold text-warning">{t("conflict.title")}</strong><p className="text-[13px] text-fg-secondary">{t(conflict.stale ? "conflict.stale" : "conflict.changed")}</p></div>
      <button type="button" className={btn.secondary} onClick={onDiff}>{t("conflict.diff")}</button>
      <button type="button" className={btn.secondary} onClick={onReload}>{t("conflict.reload")}</button>
      <button type="button" className={btn.secondary} onClick={onKeep}>{t("conflict.keep")}</button>
    </div>
  );
}

/** Rozdíl dvou textů po řádcích (jen změny s dvěma řádky kontextu). */
export function DiffModal({ title, before, after, onClose, note }: { title: string; before: string; after: string; onClose: () => void; note?: string }) {
  const diff = lineDiff(before, after);
  const near = (i: number) => diff.slice(Math.max(0, i - 2), i + 3).some((d) => d.op !== " ");
  return (
    <Modal title={title} onCancel={onClose} actions={[]} cancelLabel={t("common.close")}>
      {note && <p>{note}</p>}
      <pre className="max-h-[60vh] overflow-auto rounded-[var(--radius-control)] bg-nested p-3 font-mono text-[13px] leading-5">
        {diff.every((d) => d.op === " ") && <span className="text-fg-muted">{t("conflict.same")}</span>}
        {diff.map((d, i) => near(i) && (
          <div key={i} className={d.op === "+" ? "bg-success/10 text-success" : d.op === "-" ? "bg-error/10 text-error" : "text-fg-muted"}>
            {d.op} {d.text}
          </div>
        ))}
      </pre>
    </Modal>
  );
}
