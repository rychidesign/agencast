// `TypePicker` (§3, §4.1): prostý seznam typů vpravo od +, psaní filtruje, šipky/Enter/Esc.
import { Plus } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { createPortal } from "react-dom";
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

export function TypePicker({ onPick, onClose, paste, anchor }: {
  onPick: (p: Pick) => void; onClose: () => void; anchor?: RefObject<HTMLElement | null>; /** id vyjmutého kroku → položka „Vložit ‚x‘ sem“. */ paste?: string;
}) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState("");
  const [active, setActive] = useState(0);
  const items: Pick[] = [...(paste && !filter ? ["paste" as const] : []), ...filterTypes(filter)];
  useLayoutEffect(() => {
    const position = () => {
      const panel = ref.current;
      const a = anchor?.current?.getBoundingClientRect();
      if (panel && a && window.innerWidth >= 768) {
        const width = panel.offsetWidth, height = panel.offsetHeight;
        const left = a.right + 8 + width <= window.innerWidth - 12 ? a.right + 8 : a.left - width - 8;
        panel.style.left = `${Math.max(12, Math.min(left, window.innerWidth - width - 12))}px`;
        panel.style.top = `${Math.max(12, Math.min(a.top + a.height / 2 - height / 2, window.innerHeight - height - 12))}px`;
      }
    };
    position();
    ref.current?.focus();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
    return () => { window.removeEventListener("scroll", position, true); window.removeEventListener("resize", position); };
  }, [anchor]);
  useEffect(() => {
    const close = (e: MouseEvent) => (anchor?.current?.contains(e.target as Node) || ref.current?.contains(e.target as Node)) || onClose();
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [anchor, onClose]);
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
  return createPortal(
    <div ref={ref} role="listbox" tabIndex={-1} aria-label={t("picker.label")} onKeyDown={onKey}
      aria-activedescendant={items[active] ? `${id}-${items[active]}` : undefined}
      className="popover pop-enter fixed z-[60] max-h-[calc(100dvh-24px)] w-80 max-w-[calc(100vw-24px)] overflow-y-auto p-2 text-fg focus:outline-none max-md:inset-x-4 max-md:bottom-4 max-md:max-h-[70vh] max-md:w-auto">
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
    </div>, document.body
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
          : `relative grid size-10 place-items-center rounded-full bg-surface before:absolute before:-inset-0.5 before:content-[''] text-fg hover:bg-control focus-visible:ring-2 focus-visible:ring-accent ${paste ? "ring-1 ring-accent" : ""} ${always || open ? "" : "opacity-0 group-hover/conn:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-60"}`}>
        <Plus className="size-4" aria-hidden />{text}
      </button>
      {open && <TypePicker anchor={btnRef} paste={paste} onClose={close} onPick={(p) => (setOpen(false), onPick(p))} />}
    </div>
  );
}
