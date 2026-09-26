// Drobné sdílené komponenty (§3 inventář): stavy, skeleton, kopírování, menu ⋯, záložky, hodnoty.
import {
  Ban, Check, ChevronRight, CircleCheck, CircleDashed, CircleDot, CircleX, Copy, Ellipsis, FileText,
  TriangleAlert, type LucideIcon, Circle,
} from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { t } from "../i18n";
import type { ErrorItem } from "../types";

export const btn = {
  primary: "inline-flex h-9 items-center gap-2 rounded-lg bg-zinc-100 px-4 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-50",
  secondary: "inline-flex h-9 items-center gap-2 rounded-lg bg-zinc-800 px-4 text-sm text-zinc-100 hover:bg-zinc-700 disabled:opacity-50",
  icon: "grid size-8 place-items-center rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100",
};

// --- stav ---------------------------------------------------------------------------------

export type Status =
  | "succeeded" | "failed" | "skipped" | "running" | "queued" | "warning" | "cancelled" | "dry-run" | "none";

const STATUS: Record<Status, { icon: LucideIcon; color: string }> = {
  succeeded: { icon: CircleCheck, color: "text-emerald-400" },
  failed: { icon: CircleX, color: "text-rose-400" },
  skipped: { icon: CircleDashed, color: "text-zinc-400" },
  running: { icon: CircleDot, color: "text-sky-400 motion-safe:animate-pulse" },
  queued: { icon: CircleDashed, color: "text-zinc-400" },
  warning: { icon: TriangleAlert, color: "text-amber-400" },
  cancelled: { icon: Ban, color: "text-amber-400" },
  "dry-run": { icon: FileText, color: "text-zinc-400" },
  none: { icon: Circle, color: "text-zinc-500" },
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
    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-900 px-2 py-0.5 text-xs whitespace-nowrap text-zinc-300">
      <StatusBadge status={status}>{children}</StatusBadge>
    </span>
  );
}

// --- načítání a prázdné stavy ---------------------------------------------------------------

export function Skeleton({ className = "h-5 w-full" }: { className?: string }) {
  return <div className={`rounded-lg bg-zinc-800 motion-safe:animate-pulse ${className}`} aria-hidden />;
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
    <div className="rounded-xl bg-zinc-800/40 p-6 text-sm text-zinc-300">
      <p>{text}</p>
      {cli && <CliLine cmd={cli} className="mt-3" />}
    </div>
  );
}

export function ErrorText({ error }: { error: { message: string } }) {
  return (
    <p role="alert" className="flex items-start gap-2 text-sm text-rose-400">
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
          <li key={i} className="flex items-start gap-2 text-[13px] text-rose-400">
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
    <div className={`flex items-center gap-2 rounded-lg bg-zinc-900 py-1 pr-1 pl-3 ${className}`}>
      <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-zinc-300" title={cmd}>{cmd}</code>
      <CopyButton text={cmd} label={t("common.copyCommand")} />
    </div>
  );
}

// --- menu ⋯ ---------------------------------------------------------------------------------

export interface MenuItem {
  label: string;
  onSelect: () => void;
}

export function Menu({ items, label }: { items: MenuItem[]; label: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => root.current?.contains(e.target as Node) || setOpen(false);
    document.addEventListener("mousedown", close);
    root.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  const onKey = (e: React.KeyboardEvent) => {
    const all = [...(root.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? [])];
    const i = all.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
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
        <div id={id} role="menu" className="absolute right-0 z-20 mt-1 w-60 rounded-xl bg-zinc-800 p-1 ring-1 ring-zinc-700">
          {items.map((it) => (
            <button
              key={it.label} type="button" role="menuitem"
              className="flex h-9 w-full items-center rounded-lg px-3 text-left text-sm hover:bg-zinc-700 focus:bg-zinc-700"
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
    <nav aria-label={label} className="flex gap-1">
      {tabs.map((tab) => (
        <a
          key={tab.key} href={tab.href} aria-current={tab.key === active ? "page" : undefined}
          className={`rounded-full px-3 py-1.5 text-sm ${tab.key === active ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:text-zinc-100"}`}
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
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full bg-zinc-800 p-0.5">
      {options.map((o) => (
        <button
          key={o.key} type="button" role="radio" aria-checked={o.key === value} aria-disabled={!!o.disabled || undefined}
          title={o.disabled} aria-description={o.disabled} onClick={() => !o.disabled && onChange(o.key)}
          className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm ${o.key === value ? "bg-zinc-700 text-zinc-100" : o.disabled ? "cursor-not-allowed text-zinc-600" : "text-zinc-400 hover:text-zinc-100"}`}
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
        className="flex h-12 w-full items-center gap-3 text-left text-[15px]"
      >
        <span className="flex-1 font-medium">{title}</span>
        <span className="max-w-[55%] truncate text-zinc-400">{value}</span>
        <ChevronRight className={`size-4 text-zinc-400 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden />
      </button>
      {open && <div id={id} className="pb-4">{children}</div>}
    </div>
  );
}

// --- hodnota libovolného tvaru, jen ke čtení --------------------------------------------------

export function ValueView({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-zinc-500">–</span>;
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
  if (!entries.length) return <span className="font-mono text-[13px] text-zinc-500">{"{}"}</span>;
  return (
    <dl className="space-y-1">
      {entries.map(([k, v]) => {
        const nested = v !== null && typeof v === "object" && !(Array.isArray(v) && v.every((x) => typeof x !== "object"));
        return (
          <div key={k} className={nested ? "" : "flex flex-wrap items-baseline gap-x-3"}>
            <dt className="font-mono text-[13px] text-zinc-400">{k}</dt>
            <dd className={nested ? "pl-3" : ""}><ValueView value={v} /></dd>
          </div>
        );
      })}
    </dl>
  );
}

/** Štítek nad polem ke čtení (§5: 12–13 px semibold). */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-[13px] font-semibold text-zinc-300">{label}</div>
      <div className="rounded-lg bg-zinc-900 px-3 py-2 ring-1 ring-zinc-700">{children}</div>
    </div>
  );
}
