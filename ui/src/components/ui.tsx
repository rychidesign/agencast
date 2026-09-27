// Drobné sdílené komponenty (§3 inventář): stavy, skeleton, kopírování, menu ⋯, záložky, hodnoty.
import {
  Ban, Check, ChevronRight, CircleCheck, CircleSlash, CircleDashed, CircleDot, CircleX, Copy, Ellipsis, FileText,
  TriangleAlert, type LucideIcon, Circle,
} from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { t } from "../i18n";
import type { ErrorItem } from "../types";

export const btn = {
  primary: "inline-flex h-9 items-center justify-center gap-2 rounded-[var(--radius-control)] bg-accent px-4 text-sm font-medium text-ink hover:bg-fg disabled:opacity-50 pointer-coarse:h-11",
  secondary: "inline-flex h-9 items-center justify-center gap-2 rounded-[var(--radius-control)] bg-surface px-4 text-sm text-fg ring-1 ring-line focus-visible:ring-2 focus-visible:ring-accent hover:bg-surface-hover disabled:opacity-50 pointer-coarse:h-11",
  danger: "inline-flex h-9 items-center justify-center gap-2 rounded-[var(--radius-control)] bg-surface px-4 text-sm text-error ring-1 ring-line focus-visible:ring-2 focus-visible:ring-accent hover:bg-surface-hover disabled:opacity-50 pointer-coarse:h-11",
  ghost: "inline-flex h-9 items-center justify-center gap-2 rounded-[var(--radius-control)] px-4 text-sm text-fg-secondary hover:bg-surface-hover hover:text-fg disabled:opacity-50 pointer-coarse:h-11",
  icon: "grid size-8 place-items-center rounded-[var(--radius-control)] text-fg-muted hover:bg-surface-hover hover:text-fg disabled:opacity-50 pointer-coarse:size-11",
};

// --- stav ---------------------------------------------------------------------------------

export type Status =
  | "succeeded" | "failed" | "skipped" | "running" | "queued" | "warning" | "cancelled" | "interrupted" | "dry-run" | "none";

const STATUS: Record<Status, { icon: LucideIcon; color: string }> = {
  succeeded: { icon: CircleCheck, color: "text-success" },
  failed: { icon: CircleX, color: "text-error" },
  skipped: { icon: CircleDashed, color: "text-neutral" },
  running: { icon: CircleDot, color: "text-running motion-safe:animate-pulse" },
  queued: { icon: CircleDashed, color: "text-neutral" },
  warning: { icon: TriangleAlert, color: "text-warning" },
  cancelled: { icon: Ban, color: "text-warning" },
  interrupted: { icon: CircleSlash, color: "text-warning" },
  "dry-run": { icon: FileText, color: "text-neutral" },
  none: { icon: Circle, color: "text-neutral" },
};

/** Stav je vždy ikona + text (u samotné ikony `sr-only`), nikdy jen barva. */
export function StatusIcon({ status, label, className = "size-4" }: { status: Status; label: string; className?: string }) {
  const { icon: Icon, color } = STATUS[status];
  return (
    <>
      <Icon className={`${className} shrink-0 ${color}`} aria-hidden />
      <span className="sr-only">{label}</span>
    </>
  );
}

export function StatusBadge({ status, children }: { status: Status; children: ReactNode }) {
  const { icon: Icon, color } = STATUS[status];
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon className={`size-4 shrink-0 ${color}`} aria-hidden />
      <span>{children}</span>
    </span>
  );
}

/** Stavový čip na kartě (§5): ikona barevně, text šedý. */
export function StatusChip({ status, children }: { status: Status; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-nested px-2 py-0.5 text-xs whitespace-nowrap text-fg-secondary">
      <StatusBadge status={status}>{children}</StatusBadge>
    </span>
  );
}

// --- načítání a prázdné stavy ---------------------------------------------------------------

export function Skeleton({ className = "h-5 w-full" }: { className?: string }) {
  return <div className={`rounded-[var(--radius-control)] bg-surface motion-safe:animate-pulse ${className}`} aria-hidden />;
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

export function EmptyState({ text, cli }: { text: string; cli?: string }) {
  return (
    <div className="rounded-[var(--radius-card)] bg-surface p-6 text-sm text-fg-secondary">
      <p>{text}</p>
      {cli && <CliLine cmd={cli} className="mt-3" />}
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

/** Chyby validace (objekty z API): hláška mono, protože obsahuje stříšku `^`. */
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

// --- kopírování -----------------------------------------------------------------------------

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

// --- menu ⋯ ---------------------------------------------------------------------------------

export interface MenuItem {
  label: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: string;
}

export function Menu({ items, label }: { items: MenuItem[]; label: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => root.current?.contains(e.target as Node) || setOpen(false);
    document.addEventListener("mousedown", close);
    root.current?.querySelector<HTMLElement>("[role=menuitem]:not([aria-disabled=true])")?.focus();
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  const onKey = (e: React.KeyboardEvent) => {
    const all = [...(root.current?.querySelectorAll<HTMLElement>("[role=menuitem]:not([aria-disabled=true])") ?? [])];
    const i = all.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
      setOpen(false);
      root.current?.querySelector<HTMLElement>("button")?.focus();
    } else if (e.key === "Tab" && open) {
      // Tab menu zavře a pokračuje od tlačítka ⋯ (vzor menu podle WAI-ARIA), položky v pořadí Tab nejsou
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
        type="button" className={btn.icon} aria-label={label} aria-haspopup="menu" aria-expanded={open}
        aria-controls={id} onClick={(e) => (e.stopPropagation(), setOpen(!open))}
      >
        <Ellipsis className="size-4" aria-hidden />
      </button>
      {open && (
        <div id={id} role="menu" className="absolute right-0 z-20 mt-1 w-60 rounded-[var(--radius-card)] bg-surface p-1 ring-1 ring-line">
          {items.map((it) => (
            <button
              key={it.label} type="button" role="menuitem" tabIndex={-1} disabled={!!it.disabled} aria-disabled={!!it.disabled || undefined} title={it.disabled}
              className={`flex h-9 w-full items-center rounded-[var(--radius-control)] px-3 text-left text-sm hover:bg-surface-hover focus:bg-surface-hover disabled:opacity-50 pointer-coarse:h-11 ${it.danger ? "text-error" : "text-fg"}`}
              onClick={(e) => (e.stopPropagation(), setOpen(false), it.onSelect())}
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// --- záložky a přepínač ---------------------------------------------------------------------

export function TabLinks({ tabs, active, label }: { tabs: { key: string; label: string; href: string }[]; active: string; label: string }) {
  return (
    <nav aria-label={label} className="flex flex-wrap gap-4 border-b border-line">
      {tabs.map((tab) => (
        <a
          key={tab.key} href={tab.href} aria-current={tab.key === active ? "page" : undefined}
          className={`border-b-2 px-1 py-2 text-sm pointer-coarse:py-3 ${tab.key === active ? "border-accent text-fg" : "border-transparent text-fg-secondary hover:text-fg"}`}
        >
          {tab.label}
        </a>
      ))}
    </nav>
  );
}

/** Segmentová pilulka Form / `<>` YAML (§3 `FormYamlToggle`). */
export function Toggle<K extends string>({ value, options, onChange, label }: {
  value: K; options: { key: K; label: ReactNode; /** Důvod, proč přepnout nejde (tooltip i text pro čtečku). */ disabled?: string }[];
  onChange: (k: K) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full bg-nested p-0.5">
      {options.map((o) => (
        <button
          key={o.key} type="button" role="radio" aria-checked={o.key === value} aria-disabled={!!o.disabled || undefined}
          title={o.disabled} aria-description={o.disabled} onClick={() => !o.disabled && onChange(o.key)}
          className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm pointer-coarse:h-11 ${o.key === value ? "bg-surface text-fg" : o.disabled ? "cursor-not-allowed text-fg-muted opacity-50" : "text-fg-secondary hover:text-fg"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// --- sbalený řádek (akordeon panelu) --------------------------------------------------------

export function Collapsible({ title, value, children }: { title: string; value: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div>
      <button
        type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
        className="flex h-12 w-full items-center gap-3 text-left text-[15px] text-fg"
      >
        <span className="flex-1 font-medium">{title}</span>
        <span className="max-w-[55%] truncate font-mono text-[13px] text-fg-muted">{value}</span>
        <ChevronRight className={`size-4 text-fg-muted transition-transform ${open ? "rotate-90" : ""}`} aria-hidden />
      </button>
      {open && <div id={id} className="pb-4">{children}</div>}
    </div>
  );
}

// --- hodnota libovolného tvaru, jen ke čtení --------------------------------------------------

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
