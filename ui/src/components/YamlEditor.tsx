// `YamlEditor` (§3, §4.5): textarea nad zvýrazněným textem (dva odstíny), čísla řádků, chybné
// řádky s rose značkou, seznam chyb s odkazem na řádek. `ConflictBar` a rozdíl (§4.6).
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
      <div ref={box} className="max-h-[calc(100vh-14rem)] overflow-auto rounded-xl bg-zinc-800/60 font-mono text-sm leading-6 ring-1 ring-zinc-700 focus-within:ring-zinc-400">
        <div className="flex min-w-max">
          <div aria-hidden className="py-4 pr-3 pl-4 text-right text-zinc-500 select-none">
            {lines.map((_, i) => (
              <div key={i} className={bad.has(i + 1) ? "-ml-4 border-l-2 border-rose-400 pl-[14px] text-rose-400" : ""}>{i + 1}</div>
            ))}
          </div>
          <div className="relative flex-1 py-4 pr-4">
            <pre aria-hidden className="pointer-events-none whitespace-pre">
              {lines.map((l, i) => {
                const n = i + 1;
                const hi = flash && n >= flash[0] && n <= flash[1];
                return <div key={i} className={bad.has(n) ? "bg-rose-500/5" : hi ? "bg-zinc-700/50 transition-colors" : ""}><Line text={l || " "} /></div>;
              })}
            </pre>
            <textarea
              ref={area} value={text} readOnly={readOnly} wrap="off" spellCheck={false} aria-label={label ?? file}
              aria-describedby="yaml-hint yaml-errors" aria-invalid={errors.length > 0 || undefined}
              onChange={(e) => onChange(e.target.value)} onSelect={caret} onKeyUp={caret} onClick={caret}
              className="absolute inset-0 resize-none overflow-hidden bg-transparent py-4 pr-4 whitespace-pre text-transparent caret-zinc-100 outline-none selection:bg-zinc-600/60"
            />
          </div>
        </div>
      </div>
      <p id="yaml-hint" className="mt-2 text-xs text-zinc-400">{t(readOnly ? "code.hint" : "code.editHint", { file: `workflows/${file}` })}</p>
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
    <div role="alert" className="sticky top-[4.5rem] z-10 mx-auto mb-4 flex max-w-4xl flex-wrap items-center gap-2 rounded-xl bg-zinc-900 px-4 py-3 text-sm ring-1 ring-amber-400/40">
      <span className="flex-1 text-amber-400">{t(conflict.stale ? "conflict.stale" : "conflict.changed")}</span>
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
      <pre className="max-h-[60vh] overflow-auto rounded-lg bg-zinc-900 p-3 font-mono text-[13px] leading-5">
        {diff.every((d) => d.op === " ") && <span className="text-zinc-400">{t("conflict.same")}</span>}
        {diff.map((d, i) => near(i) && (
          <div key={i} className={d.op === "+" ? "bg-emerald-500/10 text-emerald-300" : d.op === "-" ? "bg-rose-500/10 text-rose-300" : "text-zinc-400"}>
            {d.op} {d.text}
          </div>
        ))}
      </pre>
    </Modal>
  );
}
