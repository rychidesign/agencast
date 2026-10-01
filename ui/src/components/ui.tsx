// Small shared components (§3 inventory): states, skeleton, copy, ⋯ menu, tabs, values.
import {
  Ban, Braces, Check, ChevronRight, CircleCheck, CircleSlash, CircleDashed, CircleDot, CircleX, Copy, Ellipsis, FileText, Inbox,
  TriangleAlert, type LucideIcon, Circle,
} from "lucide-react";
import { createContext, useCallback, useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { t } from "../i18n";
import type { ErrorItem } from "../types";
import { highlight } from "./yaml";

// Buttons 36 px with a mouse, 44 px on touch (`pointer-coarse:`); padding 0 18, radius 10; icon buttons square.
export const btn = {
  primary: "inline-flex h-9 shrink-0 items-center justify-center pointer-coarse:h-11 gap-2 rounded-[var(--radius-button)] bg-accent px-[18px] text-sm font-semibold whitespace-nowrap text-ink hover:bg-fg disabled:opacity-50",
  secondary: "inline-flex h-9 shrink-0 items-center justify-center pointer-coarse:h-11 gap-2 rounded-[var(--radius-button)] bg-control px-[18px] text-sm font-semibold whitespace-nowrap text-fg hover:bg-control-hover disabled:opacity-50",
  danger: "inline-flex h-9 shrink-0 items-center justify-center pointer-coarse:h-11 gap-2 rounded-[var(--radius-button)] bg-danger px-[18px] text-sm font-semibold whitespace-nowrap text-error hover:bg-danger-hover disabled:opacity-50",
  ghost: "inline-flex h-9 shrink-0 items-center justify-center pointer-coarse:h-11 gap-2 rounded-[var(--radius-button)] px-[18px] text-sm font-semibold whitespace-nowrap text-fg-secondary hover:bg-surface-hover hover:text-fg disabled:opacity-50",
  icon: "grid size-9 shrink-0 place-items-center rounded-[var(--radius-button)] pointer-coarse:size-11 bg-control text-fg hover:bg-control-hover disabled:opacity-50",
  /** Contextual "+ Add …" next to a section label or at the end of a container: text only in `type`, a surface only on hover;
   *  always right-aligned, `-mr-2` puts the text on the edge of the fields below. */
  add: "-mr-2 inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-[var(--radius-button)] px-2 text-sm font-medium whitespace-nowrap text-type hover:bg-surface-hover disabled:opacity-50 pointer-coarse:h-11",
  /** ⋯ on cards (design: no fill, a surface only on hover / when open). */
  iconGhost: "grid size-9 shrink-0 place-items-center rounded-[var(--radius-button)] pointer-coarse:size-11 text-fg hover:bg-control aria-expanded:bg-control disabled:opacity-50 [&>svg]:size-[18px]",
};

// --- layout and dialogs -----------------------------------------------------------------------

/** Media query as state; without `matchMedia` (jsdom) `fallback` applies. */
export function useMedia(query: string, fallback = false) {
  const subscribe = useCallback((cb: () => void) => {
    const m = window.matchMedia?.(query);
    m?.addEventListener("change", cb);
    return () => m?.removeEventListener("change", cb);
  }, [query]);
  return useSyncExternalStore(subscribe, () => window.matchMedia?.(query).matches ?? fallback);
}

/** Panel as a bottom sheet up to 1279 px. Set by `PanelSlot`, read by `PanelShell`. */
export const SheetContext = createContext(false);

/** Places a floating menu within the viewport, also at its edge. */
export function placePopover(panel: HTMLElement, anchor: HTMLElement, align: "left" | "right" = "right", matchWidth = false) {
  const a = anchor.getBoundingClientRect();
  panel.style.maxHeight = `${window.innerHeight - 24}px`;
  if (matchWidth) panel.style.width = `${Math.min(a.width, window.innerWidth - 24)}px`;
  const width = Math.min(panel.offsetWidth, window.innerWidth - 24);
  const height = Math.min(panel.offsetHeight, window.innerHeight - 24);
  const left = Math.max(12, Math.min(align === "right" ? a.right - width : a.left, window.innerWidth - width - 12));
  const below = a.bottom + 4 + height <= window.innerHeight - 12;
  panel.style.left = `${left}px`;
  panel.style.top = `${below ? a.bottom + 4 : Math.max(12, Math.min(a.top - height - 4, window.innerHeight - height - 12))}px`;
}

export function usePopoverPosition(open: boolean, panel: RefObject<HTMLElement | null>, anchor: RefObject<HTMLElement | null>, align: "left" | "right" = "right", matchWidth = false, sizeKey = 0) {
  useLayoutEffect(() => {
    if (!open || !panel.current || !anchor.current) return;
    const update = () => panel.current && anchor.current && placePopover(panel.current, anchor.current, align, matchWidth);
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => { window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); };
  }, [open, panel, anchor, align, matchWidth, sizeKey]);
}

/** Tab and Shift+Tab stay inside `root`. */
export function trapTab(root: HTMLElement | null, e: React.KeyboardEvent) {
  const all = [...(root?.querySelectorAll<HTMLElement>(":is(button, input, textarea, select):not(:disabled), a[href], [tabindex='0']") ?? [])]
    .filter((el) => el.offsetParent !== null || el === document.activeElement);
  if (!all.length) return;
  const i = all.indexOf(document.activeElement as HTMLElement);
  e.preventDefault();
  all[e.shiftKey ? (i <= 0 ? all.length - 1 : i - 1) : (i + 1) % all.length]?.focus();
}

/** Full-screen dialog (drawer, panel sheet): focus moves in, Tab stays inside, Esc closes, focus returns after closing. */
export function useDialog<T extends HTMLElement>(onClose: () => void, active = true) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!active) return;
    const prev = document.activeElement as HTMLElement | null;
    if (!ref.current?.contains(document.activeElement)) ref.current?.focus();
    // the page under a full-screen dialog does not scroll
    const root = document.documentElement, overflow = root.style.overflow;
    root.style.overflow = "hidden";
    return () => {
      root.style.overflow = overflow;
      if (prev?.isConnected) prev.focus();
    };
  }, [active]);
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!active || e.defaultPrevented) return;
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    } else if (e.key === "Tab") trapTab(ref.current, e);
  };
  return { ref, onKeyDown };
}

// --- status -------------------------------------------------------------------------------

export type Status =
  | "succeeded" | "failed" | "skipped" | "running" | "queued" | "warning" | "cancelled" | "interrupted" | "dry-run" | "none";

// Only the icon of the running state pulses — pulsing text would lack 4.5:1 contrast mid-animation.
const pulse = (s: Status) => (s === "running" ? " motion-safe:animate-pulse" : "");

const STATUS: Record<Status, { icon: LucideIcon; color: string }> = {
  succeeded: { icon: CircleCheck, color: "text-success" },
  failed: { icon: CircleX, color: "text-error" },
  skipped: { icon: CircleDashed, color: "text-neutral" },
  running: { icon: CircleDot, color: "text-running" },
  queued: { icon: CircleDashed, color: "text-neutral" },
  warning: { icon: TriangleAlert, color: "text-warning" },
  cancelled: { icon: Ban, color: "text-warning" },
  interrupted: { icon: CircleSlash, color: "text-warning" },
  "dry-run": { icon: FileText, color: "text-neutral" },
  none: { icon: Circle, color: "text-neutral" },
};

/** A status is always an icon + text (`sr-only` for a lone icon), never just color. */
export function StatusIcon({ status, label, className = "size-4" }: { status: Status; label: string; className?: string }) {
  const { icon: Icon, color } = STATUS[status];
  return (
    <>
      <Icon className={`${className} shrink-0 ${color}${pulse(status)}`} aria-hidden />
      <span className="sr-only">{label}</span>
    </>
  );
}

export function StatusBadge({ status, children }: { status: Status; children: ReactNode }) {
  const { icon: Icon, color } = STATUS[status];
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon className={`size-4 shrink-0 ${color}${pulse(status)}`} aria-hidden />
      <span>{children}</span>
    </span>
  );
}

/** Status chip on a card: both the icon and the text use the status color. */
export function StatusChip({ status, children }: { status: Status; children: ReactNode }) {
  const { icon: Icon, color } = STATUS[status];
  return (
    <span className={`inline-flex items-center gap-2 rounded-full bg-nested px-2.5 py-[7px] font-mono text-xs font-medium whitespace-nowrap ${color}`}>
      <Icon className={`size-3.5 shrink-0 ${color}${pulse(status)}`} aria-hidden />{children}
    </span>
  );
}

// --- loading and empty states ---------------------------------------------------------------

export function Skeleton({ className = "h-5 w-full" }: { className?: string }) {
  // `surface-hover`: visible on the page background and inside a card (`surface`)
  return <div className={`rounded-[var(--radius-control)] bg-surface-hover motion-safe:animate-pulse ${className}`} aria-hidden />;
}

export function Loading({ rows = 3, pill = false }: { rows?: number; pill?: boolean }) {
  return (
    <div className="space-y-3" role="status" aria-label={t("common.loading")}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={pill ? "h-14 w-full rounded-full" : "h-6 w-full"} />
      ))}
    </div>
  );
}

/** Empty state (design 15, measured from .pen): `surface` r12 p28 gap 14, icon 28, title 18 semibold, description 13. */
export function EmptyState({ text, hint, cli, tall = false, icon: Icon = Inbox }: {
  text: string; hint?: string; cli?: string; /** 380 px as in the design (queue). */ tall?: boolean; icon?: LucideIcon;
}) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3.5 rounded-[var(--radius-card)] bg-surface p-7 text-center ${tall ? "min-h-[380px]" : ""}`}>
      <Icon className="size-7 text-running" aria-hidden />
      <p className="text-lg leading-[26px] font-semibold text-fg">{text}</p>
      {hint && <p className="text-[13px] leading-[19px] text-fg-secondary">{hint}</p>}
      {cli && <CliLine cmd={cli} className="mt-1 w-full max-w-lg text-left" />}
    </div>
  );
}

export function ErrorText({ error }: { error: { message: string } }) {
  return (
    <p role="alert" className="flex items-start gap-2 font-mono text-[13px] text-error">
      <CircleX className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span className="whitespace-pre-wrap">{error.message}</span>
    </p>
  );
}

/** Validation errors (objects from the API): mono message, because it contains the caret `^`. */
export function ErrorList({ errors, hrefFor }: { errors: ErrorItem[]; hrefFor?: (e: ErrorItem) => string | undefined }) {
  if (!errors.length) return null;
  return (
    <ul className="space-y-2">
      {errors.map((e, i) => {
        const link = hrefFor?.(e);
        const msg = <pre className="font-mono whitespace-pre-wrap">{e.message}</pre>;
        return (
          <li key={i} className="flex items-start gap-2 font-mono text-[13px] text-error">
            <CircleX className="mt-0.5 size-4 shrink-0" aria-hidden />
            {link ? <a href={link} className="hover:underline">{msg}</a> : msg}
          </li>
        );
      })}
    </ul>
  );
}

// --- copying --------------------------------------------------------------------------------

export function CopyButton({ text, label = t("common.copy") }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <button type="button" className={btn.icon} onClick={copy} aria-label={label} title={label}>
      {done ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
      <span className="sr-only" aria-live="polite">{done ? t("common.copied") : ""}</span>
    </button>
  );
}

export function CliLine({ cmd, className = "" }: { cmd: string; className?: string }) {
  return (
    <div className={`flex items-center gap-2 rounded-[var(--radius-control)] bg-nested py-1 pr-1 pl-3 ${className}`}>
      <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-fg-secondary" title={cmd}>{cmd}</code>
      <CopyButton text={cmd} label={t("common.copyCommand")} />
    </div>
  );
}

/** Copy in the code block footer: transparent with an outline (design 12 "Code actions"). */
export const copyBtn = "inline-flex h-9 shrink-0 items-center gap-2 rounded-[var(--radius-button)] px-3.5 text-sm font-semibold text-fg ring-1 pointer-coarse:h-11 ring-fg-muted/70 hover:bg-control";

/** Code block header: icon 18 + mono 13 name + chip (r6, outline), p 14 18 with a line (design 12, measured from .pen). */
export function CodeHead({ icon: Icon = Braces, name, chip }: { icon?: LucideIcon; name: string; chip: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 border-b border-line px-[18px] py-3.5">
      <Icon className="size-[18px] shrink-0 text-fg-secondary" aria-hidden />
      <span className="min-w-0 flex-1 truncate font-mono text-[13px] leading-[19px] text-fg" title={name}>{name}</span>
      <span className="shrink-0 rounded-[6px] bg-nested px-[9px] py-[5px] font-mono text-[11px] leading-4 text-fg-secondary ring-1 ring-line">{chip}</span>
    </div>
  );
}

/** Code block ("CodeViewer", design 12): `surface` r16, header, `nested` body with line numbers (27 px row), footer
 *  with a description on the left and Copy on the right. Long lines wrap (model outputs are prose); `yaml` highlights syntax. */
export function CodeBlock({ text: source, title, file, language, foot, yaml = false }: {
  text: string; title?: string; file?: string; /** Chip text in the header (default "Read only"). */ language?: string; foot?: string;
  yaml?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const name = title ?? file ?? t("code.output");
  const lines = source.replace(/\n$/, "").split("\n");
  const colored = yaml ? highlight(lines) : lines.map((line) => line || " ");
  return (
    <section className="overflow-hidden rounded-[var(--radius-panel)] bg-surface">
      <CodeHead name={name} chip={language ?? t("code.readOnly")} />
      <div className="scroll-thin max-h-[60vh] overflow-auto bg-nested py-[18px] font-mono text-[13px] leading-[19px] focus-visible:ring-2 focus-visible:ring-accent" role="region" aria-label={name} tabIndex={0}>
        <table className="w-full border-collapse"><tbody>{colored.map((line, i) => (
          <tr key={i}><td className="w-[58px] py-1 pr-3.5 pl-4 text-right align-top font-mono text-xs leading-[19px] text-fg-muted select-none">{i + 1}</td><td className="py-1 pr-4 whitespace-pre-wrap break-words text-fg-secondary">{line}</td></tr>
        ))}</tbody></table>
      </div>
      <div className="flex items-center justify-between gap-3 p-3.5">
        <span className="min-w-0 truncate font-mono text-[11px] text-fg-muted">{foot}</span>
        <button type="button" className={copyBtn} onClick={async () => {
          await navigator.clipboard.writeText(source);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}>{copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}{copied ? t("common.copied") : t("common.copy")}</button>
      </div>
    </section>
  );
}

// --- menu ⋯ ---------------------------------------------------------------------------------

export interface MenuItem {
  label: string;
  onSelect: () => void;
  shortcut?: string;
  danger?: boolean;
  disabled?: string;
}

/** ⋯ menu; `ghost` = without fill (cards). */
export function Menu({ items, label, ghost = false }: { items: MenuItem[]; label: string; ghost?: boolean }) {
  const [open, setOpen] = useState(false);
  const mac = /Mac|iPhone|iPad|iPod/.test(navigator.platform);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const id = useId();
  usePopoverPosition(open, popup, trigger);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => (root.current?.contains(e.target as Node) || popup.current?.contains(e.target as Node)) || setOpen(false);
    const scroll = () => {
      const a = trigger.current?.getBoundingClientRect();
      if (a && (a.bottom < 0 || a.top > window.innerHeight)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    window.addEventListener("scroll", scroll, true);
    popup.current?.querySelector<HTMLElement>("[role=menuitem]:not([aria-disabled=true])")?.focus();
    return () => { document.removeEventListener("mousedown", close); window.removeEventListener("scroll", scroll, true); };
  }, [open]);
  const onKey = (e: React.KeyboardEvent) => {
    const all = [...(popup.current?.querySelectorAll<HTMLElement>("[role=menuitem]:not([aria-disabled=true])") ?? [])];
    const i = all.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape" && open) {
      e.preventDefault(); // Esc closes only the menu, not the panel or sheet below it
      e.stopPropagation();
      setOpen(false);
      root.current?.querySelector<HTMLElement>("button")?.focus();
    } else if (e.key === "Tab" && open) {
      // Tab closes the menu and continues from the ⋯ button (menu pattern per WAI-ARIA), items are not in the Tab order
      e.stopPropagation();
      setOpen(false);
      root.current?.querySelector<HTMLElement>("button")?.focus();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      all[(i + (e.key === "ArrowDown" ? 1 : all.length - 1)) % all.length]?.focus();
    }
  };
  return (
    <div ref={root} className="relative" onKeyDown={onKey}>
      <button
        ref={trigger}
        type="button" className={ghost ? btn.iconGhost : btn.icon} aria-label={label} aria-haspopup="menu" aria-expanded={open}
        aria-controls={id} onClick={(e) => (e.stopPropagation(), setOpen(!open))}
      >
        <Ellipsis className="size-5" aria-hidden />
      </button>
      {open && createPortal(
        <div ref={popup} id={id} role="menu" className="scroll-quiet popover pop-enter fixed z-[60] flex w-60 flex-col gap-1 overflow-y-auto p-2">
          {items.map((it) => (
            <button
              key={it.label} type="button" role="menuitem" tabIndex={-1} disabled={!!it.disabled} aria-disabled={!!it.disabled || undefined} title={it.disabled}
              className={`group flex min-h-10 w-full items-center rounded-[7px] px-3 text-left text-sm hover:bg-surface-active focus:bg-surface-active disabled:opacity-50 ${it.danger ? "text-error" : "text-fg"}`}
              onClick={(e) => (e.stopPropagation(), setOpen(false), it.onSelect())}
            >
              {it.label}
              {it.shortcut && <span aria-hidden="true" className="pointer-coarse:hidden ml-auto pl-3 font-mono text-[11px] text-fg-muted group-hover:text-fg-secondary group-focus:text-fg-secondary">{it.shortcut.replace(/^Ctrl\+/, mac ? "⌘" : "Ctrl+").replace(/^Alt\+/, mac ? "⌥" : "Alt+")}</span>}
            </button>
          ))}
        </div>, document.body
      )}
    </div>
  );
}

// --- tabs and toggle ------------------------------------------------------------------------

export function TabLinks({ tabs, active, label }: { tabs: { key: string; label: string; href: string }[]; active: string; label: string }) {
  return (
    <nav aria-label={label} className="flex max-w-full min-w-0 flex-wrap gap-x-7 border-b border-line max-md:flex-nowrap max-md:gap-x-2 max-md:overflow-x-auto">
      {tabs.map((tab) => (
        <a
          key={tab.key} href={tab.href} aria-current={tab.key === active ? "page" : undefined}
          className={`-mb-px flex h-12 shrink-0 items-center border-b-2 px-[18px] text-[13px] font-medium max-md:px-3 ${tab.key === active ? "border-accent text-fg" : "border-transparent text-fg-secondary hover:text-fg"}`}
        >
          {tab.label}
        </a>
      ))}
    </nav>
  );
}

/** Segmented Form / `<>` YAML toggle (§3 `FormYamlToggle`): r9 p4 wrapper, r7 segment 28 px (44 on touch), 13 px — as tall as a button. */
export function Toggle<K extends string>({ value, options, onChange, label }: {
  value: K; options: { key: K; label: ReactNode; /** Reason why switching is not possible (tooltip and screen reader text). */ disabled?: string }[];
  onChange: (k: K) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex gap-1 rounded-[9px] bg-nested p-1">
      {options.map((o) => (
        <button
          key={o.key} type="button" role="radio" aria-checked={o.key === value} aria-disabled={!!o.disabled || undefined}
          title={o.disabled} aria-description={o.disabled} onClick={() => !o.disabled && onChange(o.key)}
          className={`inline-flex h-7 items-center gap-2 rounded-[7px] px-3 text-[13px] pointer-coarse:h-11 pointer-coarse:px-3.5 ${o.key === value ? "bg-accent text-ink" : o.disabled ? "cursor-not-allowed text-fg-muted opacity-50" : "text-fg-muted hover:text-fg"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// --- collapsed row (panel accordion) --------------------------------------------------------

export function Collapsible({ title, value, children }: { title: string; value: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div>
      <button
        type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
        className="flex min-h-[52px] w-full items-center gap-2.5 py-4 text-left text-sm text-fg"
      >
        <ChevronRight className={`size-4 shrink-0 text-fg-secondary transition-transform ${open ? "rotate-90" : ""}`} aria-hidden />
        <span className="flex-1 font-medium">{title}</span>
        <span className="max-w-[55%] truncate font-mono text-[11px] text-fg-muted" title={typeof value === "string" ? value : undefined}>{value}</span>
      </button>
      {open && <div id={id} className="pb-4">{children}</div>}
    </div>
  );
}

// --- value of any shape, read-only ------------------------------------------------------------

export function ValueView({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-fg-muted">–</span>;
  if (typeof value === "string")
    return <span className="font-mono text-[13px] whitespace-pre-wrap break-words">{value}</span>;
  if (typeof value !== "object") return <span className="font-mono text-[13px]">{String(value)}</span>;
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v !== "object" || v === null))
      return <span className="font-mono text-[13px]">{value.map(String).join(", ") || "[]"}</span>;
    return (
      <ol className="space-y-1">
        {value.map((v, i) => <li key={i}><ValueView value={v} /></li>)}
      </ol>
    );
  }
  const entries = Object.entries(value);
  if (!entries.length) return <span className="font-mono text-[13px] text-fg-muted">{"{}"}</span>;
  return (
    <dl className="space-y-1">
      {entries.map(([k, v]) => {
        const nested = v !== null && typeof v === "object" && !(Array.isArray(v) && v.every((x) => typeof x !== "object"));
        return (
          <div key={k} className={nested ? "" : "flex flex-wrap items-baseline gap-x-3"}>
            <dt className="font-mono text-[13px] text-fg-muted">{k}</dt>
            <dd className={nested ? "pl-3" : ""}><ValueView value={v} /></dd>
          </div>
        );
      })}
    </dl>
  );
}
