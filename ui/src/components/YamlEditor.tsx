// `YamlEditor` (§3, §4.5): textarea nad zvýrazněným textem, čísla řádků,
// chybné řádky a seznam chyb s odkazem na řádek. `ConflictBar` a rozdíl (§4.6).
import { useEffect, useRef, useState } from "react";
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
  const [flash, setFlash] = useState(focus);
  const lines = text.split("\n");
  const bad = new Set(errors.map((e) => e.line).filter(Boolean));

  const goTo = (line: number) => {
    const el = area.current;
    if (!el) return;
    const offset = lines.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
    el.focus({ preventScroll: true });
    el.setSelectionRange(offset, offset);
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
    if (el && onCaretLine) onCaretLine(el.value.slice(0, el.selectionStart).split("\n").length);
  };
  return (
    <div>
      <div ref={box} className="max-h-[calc(100vh-14rem)] overflow-auto rounded-[var(--radius-card)] bg-nested font-mono text-[13px] leading-6 ring-1 ring-line focus-within:ring-accent">
        <div className="flex min-w-max">
          <div aria-hidden className="py-4 pr-3 pl-4 text-right text-fg-muted select-none">
            {lines.map((_, i) => (
              <div key={i} data-testid={bad.has(i + 1) ? `yaml-line-${i + 1}` : undefined}
                className={bad.has(i + 1) ? "-ml-4 border-l-2 border-error bg-error/10 pl-[14px] text-error" : flash && i + 1 >= flash[0] && i + 1 <= flash[1] ? "-ml-4 border-l-2 border-accent bg-surface-hover pl-[14px]" : ""}>{i + 1}</div>
            ))}
          </div>
          <div className="relative flex-1 py-4 pr-4">
            <pre aria-hidden className="pointer-events-none whitespace-pre">
              {lines.map((l, i) => {
                const n = i + 1;
                const hi = flash && n >= flash[0] && n <= flash[1];
                return <div key={i} className={bad.has(n) ? "bg-error/10" : hi ? "bg-surface-hover transition-colors" : ""}><Line text={l || " "} /></div>;
              })}
            </pre>
            <textarea
              ref={area} value={text} readOnly={readOnly} wrap="off" spellCheck={false} aria-label={label ?? file}
              aria-describedby="yaml-hint yaml-errors" aria-invalid={errors.length > 0 || undefined}
              onChange={(e) => onChange(e.target.value)} onSelect={caret} onKeyUp={caret} onClick={caret}
              className="absolute inset-0 resize-none overflow-hidden bg-transparent py-4 pr-4 whitespace-pre text-transparent caret-fg outline-none selection:bg-accent/30"
            />
          </div>
        </div>
      </div>
      <p id="yaml-hint" className="mt-2 text-xs text-fg-muted">{t(readOnly ? "code.hint" : "code.editHint", { file: `workflows/${file}` })}</p>
      <div id="yaml-errors" className="mt-3">
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
export function ConflictBar({ conflict, onDiff, onReload, onKeep }: {
  conflict: Conflict; onDiff: () => void; onReload: () => void; onKeep: () => void;
}) {
  return (
    <div role="alert" data-testid="conflict-bar" className="sticky top-[4.5rem] z-10 mx-auto mb-4 flex max-w-4xl flex-wrap items-center gap-2 rounded-[var(--radius-card)] bg-surface px-4 py-3 text-sm ring-1 ring-warning/60">
      <span className="flex-1 text-warning">{t(conflict.stale ? "conflict.stale" : "conflict.changed")}</span>
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
