// `TypePicker` (§3, §4.1): prostý seznam typů vpravo od +, psaní filtruje, šipky/Enter/Esc.
import { Plus } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { t } from "../i18n";
import type { StepType } from "../types";
import { btn } from "./ui";

/** Skupiny oddělené hairline; `output` se nenabízí (jde jen na konec hlavního seznamu). */
export const PICKER_GROUPS: StepType[][] = [["ask", "task", "jev", "image"], ["parallel", "switch", "call", "fail"], ["set"]];

export type Pick = StepType | "paste";

/** Položky po filtru: klíčové slovo začíná filtrem, jinak ho obsahuje slovo nebo popis. */
export function filterTypes(filter: string): StepType[] {
  const all = PICKER_GROUPS.flat();
  const f = filter.toLowerCase();
  if (!f) return all;
  const starts = all.filter((k) => k.startsWith(f));
  return starts.length ? starts : all.filter((k) => k.includes(f) || t(`picker.${k}`).toLowerCase().includes(f));
}

export function TypePicker({ onPick, onClose, paste }: {
  onPick: (p: Pick) => void; onClose: () => void; /** id vyjmutého kroku → položka „Vložit ‚x‘ sem“. */ paste?: string;
}) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState("");
  const [active, setActive] = useState(0);
  const [flip, setFlip] = useState(false);
  const items: Pick[] = [...(paste && !filter ? ["paste" as const] : []), ...filterTypes(filter)];
  useLayoutEffect(() => {
    const r = ref.current?.getBoundingClientRect();
    if (r && r.right > window.innerWidth) setFlip(true);
    ref.current?.focus();
  }, []);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current?.parentElement?.contains(e.target as Node) || onClose();
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [onClose]);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a + (e.key === "ArrowDown" ? 1 : items.length - 1)) % Math.max(1, items.length));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (items[active]) onPick(items[active]);
    } else if (e.key === "Escape" || e.key === "Tab") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    } else if (e.key === "Backspace") {
      setFilter((f) => f.slice(0, -1));
      setActive(0);
    } else if (/^[a-z]$/i.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
      setFilter((f) => f + e.key.toLowerCase());
      setActive(0);
    }
  };
  let group = -1;
  return (
    <div ref={ref} role="listbox" tabIndex={-1} aria-label={t("picker.label")} onKeyDown={onKey}
      aria-activedescendant={items[active] ? `${id}-${items[active]}` : undefined}
      className={`absolute top-1/2 z-30 w-80 -translate-y-1/2 rounded-card bg-surface p-2 text-fg shadow-2xl ring-1 ring-line focus:outline-none ${flip ? "right-full mr-2" : "left-full ml-2"}`}>
      {filter && <div className="px-3 py-1 font-mono text-xs text-fg-muted" aria-live="polite">{t("picker.filter", { filter })}</div>}
      {items.map((k, i) => {
        const g = k === "paste" ? -2 : PICKER_GROUPS.findIndex((gr) => gr.includes(k));
        const line = i > 0 && g !== group;
        group = g;
        return (
          <div key={k}>
            {line && <div className="mx-2 my-1 h-px bg-line" aria-hidden />}
            <div id={`${id}-${k}`} role="option" aria-selected={i === active}
              onMouseDown={(e) => (e.preventDefault(), onPick(k))} onMouseEnter={() => setActive(i)}
              className={`flex h-10 cursor-pointer items-center gap-3 rounded-control px-3 text-[13px] pointer-coarse:h-11 ${i === active ? "bg-surface-active" : ""}`}>
              {k === "paste" ? (
                <span>{t("picker.paste", { id: paste! })}</span>
              ) : (
                <>
                  <span className="w-16 shrink-0 font-mono text-fg">{k}</span>
                  <span className={`truncate ${i === active ? "text-fg-secondary" : "text-fg-muted"}`}>{t(`picker.${k}`)}</span>
                </>
              )}
            </div>
          </div>
        );
      })}
      {!items.length && <div className="px-3 py-2 text-[13px] text-fg-muted">{t("picker.none")}</div>}
    </div>
  );
}

/** `AddButton` (§3): (+) 44 px kolečko (návrh 05); mezi kartami se ukazuje při hoveru/fokusu místo šipky, na konci trvale.
 *  S `text` je to sekundární tlačítko „+ Přidat krok“ pod hlavním sloupcem (fidelity §6). */
export function AddButton({ label, onPick, paste, always = false, testid, text }: {
  label: string; onPick: (p: Pick) => void; paste?: string; always?: boolean; testid?: string; text?: string;
}) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const close = () => {
    setOpen(false);
    btnRef.current?.focus();
  };
  return (
    <div className="relative inline-flex">
      <button ref={btnRef} type="button" aria-label={label} title={label} aria-haspopup="listbox" aria-expanded={open} data-testid={testid}
        onClick={() => setOpen(!open)}
        className={text ? `${btn.secondary} ${paste ? "ring-1 ring-accent" : ""}`
          : `grid size-11 place-items-center rounded-full bg-surface text-fg hover:bg-control focus-visible:ring-2 focus-visible:ring-accent ${paste ? "ring-1 ring-accent" : ""} ${always || open ? "" : "opacity-0 group-hover/conn:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-60"}`}>
        <Plus className="size-4" aria-hidden />{text}
      </button>
      {open && <TypePicker paste={paste} onClose={close} onPick={(p) => (setOpen(false), onPick(p))} />}
    </div>
  );
}
