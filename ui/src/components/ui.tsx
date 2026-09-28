// Drobné sdílené komponenty (§3 inventář): stavy, skeleton, kopírování, menu ⋯, záložky, hodnoty.
import {
  Ban, Braces, Check, ChevronRight, CircleCheck, CircleSlash, CircleDashed, CircleDot, CircleX, Copy, Ellipsis, FileText, Inbox,
  TriangleAlert, type LucideIcon, Circle,
} from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { t } from "../i18n";
import type { ErrorItem } from "../types";

// Rozměry změřené z .pen (obrazovky 1440): tlačítko 44 px, padding 0 18, radius 10; ikonové 44 × 44.
export const btn = {
  primary: "inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-[var(--radius-button)] bg-accent px-[18px] text-sm font-semibold whitespace-nowrap text-ink hover:bg-fg disabled:opacity-50",
  secondary: "inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-[var(--radius-button)] bg-control px-[18px] text-sm font-semibold whitespace-nowrap text-fg hover:bg-control-hover disabled:opacity-50",
  danger: "inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-[var(--radius-button)] bg-danger px-[18px] text-sm font-semibold whitespace-nowrap text-error hover:bg-danger-hover disabled:opacity-50",
  ghost: "inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-[var(--radius-button)] px-[18px] text-sm font-semibold whitespace-nowrap text-fg-secondary hover:bg-surface-hover hover:text-fg disabled:opacity-50",
  icon: "grid size-11 shrink-0 place-items-center rounded-[var(--radius-button)] bg-control text-fg hover:bg-control-hover disabled:opacity-50",
  /** ⋯ na kartách (návrh: bez výplně, plocha až při hoveru / otevření). */
  iconGhost: "grid size-11 shrink-0 place-items-center rounded-[var(--radius-button)] text-fg hover:bg-control aria-expanded:bg-control disabled:opacity-50 [&>svg]:size-[18px]",
};

// --- stav ---------------------------------------------------------------------------------

export type Status =
  | "succeeded" | "failed" | "skipped" | "running" | "queued" | "warning" | "cancelled" | "interrupted" | "dry-run" | "none";

// Pulzuje jen ikona běžícího stavu — pulzující text by v půlce animace neměl kontrast 4,5:1.
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

/** Stav je vždy ikona + text (u samotné ikony `sr-only`), nikdy jen barva. */
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

/** Stavový čip na kartě: ikona i text používají barvu stavu. */
export function StatusChip({ status, children }: { status: Status; children: ReactNode }) {
  const { icon: Icon, color } = STATUS[status];
  return (
    <span className={`inline-flex items-center gap-2 rounded-full bg-nested px-2.5 py-[7px] font-mono text-xs font-medium whitespace-nowrap ${color}`}>
      <Icon className={`size-3.5 shrink-0 ${color}${pulse(status)}`} aria-hidden />{children}
    </span>
  );
}

// --- načítání a prázdné stavy ---------------------------------------------------------------

export function Skeleton({ className = "h-5 w-full" }: { className?: string }) {
  // `surface-hover`: viditelné na pozadí stránky i uvnitř karty (`surface`)
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

/** Prázdný stav (návrh 15, změřeno z .pen): `surface` r12 p28 gap 14, ikona 28, titul 18 semibold, popis 13. */
export function EmptyState({ text, hint, cli, tall = false, icon: Icon = Inbox }: {
  text: string; hint?: string; cli?: string; /** 380 px jako v návrhu (fronta). */ tall?: boolean; icon?: LucideIcon;
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

/** Kopírovat v patičce bloku kódu: průhledné s obrysem (návrh 12 „Code actions“). */
export const copyBtn = "inline-flex h-10 shrink-0 items-center gap-2 rounded-[var(--radius-button)] px-3.5 text-sm font-semibold text-fg ring-1 ring-fg-muted/70 hover:bg-control";

/** Hlavička bloku kódu: ikona 18 + název mono 13 + čip (r6, obrys), p 14 18 s linkou (návrh 12, změřeno z .pen). */
export function CodeHead({ icon: Icon = Braces, name, chip }: { icon?: LucideIcon; name: string; chip: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 border-b border-line px-[18px] py-3.5">
      <Icon className="size-[18px] shrink-0 text-fg-secondary" aria-hidden />
      <span className="min-w-0 flex-1 truncate font-mono text-[13px] leading-[19px] text-fg" title={name}>{name}</span>
      <span className="shrink-0 rounded-[6px] bg-nested px-[9px] py-[5px] font-mono text-[11px] leading-4 text-fg-secondary ring-1 ring-line">{chip}</span>
    </div>
  );
}

/** Blok kódu („CodeViewer“, návrh 12): `surface` r16, hlavička, tělo `nested` s čísly řádků (řádek 27 px), patička
 *  s popisem vlevo a Kopírovat vpravo. Dlouhé řádky se zalamují (výstupy modelu jsou próza). */
export function CodeBlock({ text: source, title, file, language, foot }: {
  text: string; title?: string; file?: string; /** Text čipu v hlavičce (výchozí „Pouze čtení“). */ language?: string; foot?: string;
}) {
  const [copied, setCopied] = useState(false);
  const name = title ?? file ?? t("code.output");
  const lines = source.replace(/\n$/, "").split("\n");
  return (
    <section className="overflow-hidden rounded-[var(--radius-panel)] bg-surface">
      <CodeHead name={name} chip={language ?? t("code.readOnly")} />
      <div className="max-h-[60vh] overflow-auto bg-nested py-[18px] font-mono text-[13px] leading-[19px] focus-visible:ring-2 focus-visible:ring-accent" role="region" aria-label={name} tabIndex={0}>
        <table className="w-full border-collapse"><tbody>{lines.map((line, i) => (
          <tr key={i}><td className="w-[58px] py-1 pr-3.5 pl-4 text-right align-top font-mono text-xs leading-[19px] text-fg-muted select-none">{i + 1}</td><td className="py-1 pr-4 whitespace-pre-wrap break-words text-fg-secondary">{line || " "}</td></tr>
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
  danger?: boolean;
  disabled?: string;
}

/** ⋯ menu; `ghost` = bez výplně (karty). */
export function Menu({ items, label, ghost = false }: { items: MenuItem[]; label: string; ghost?: boolean }) {
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
        type="button" className={ghost ? btn.iconGhost : btn.icon} aria-label={label} aria-haspopup="menu" aria-expanded={open}
        aria-controls={id} onClick={(e) => (e.stopPropagation(), setOpen(!open))}
      >
        <Ellipsis className="size-5" aria-hidden />
      </button>
      {open && (
        <div id={id} role="menu" className="absolute right-0 z-20 mt-1 w-60 rounded-[var(--radius-card)] bg-surface p-2 ring-1 ring-line">
          {items.map((it) => (
            <button
              key={it.label} type="button" role="menuitem" tabIndex={-1} disabled={!!it.disabled} aria-disabled={!!it.disabled || undefined} title={it.disabled}
              className={`flex h-10 w-full items-center rounded-[var(--radius-control)] px-3 text-left text-sm hover:bg-surface-hover focus:bg-surface-hover disabled:opacity-50 ${it.danger ? "text-error" : "text-fg"}`}
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
    <nav aria-label={label} className="flex flex-wrap gap-x-7 border-b border-line">
      {tabs.map((tab) => (
        <a
          key={tab.key} href={tab.href} aria-current={tab.key === active ? "page" : undefined}
          className={`-mb-px flex h-12 items-center border-b-2 px-[18px] text-[13px] font-medium ${tab.key === active ? "border-accent text-fg" : "border-transparent text-fg-secondary hover:text-fg"}`}
        >
          {tab.label}
        </a>
      ))}
    </nav>
  );
}

/** Segmentový přepínač Form / `<>` YAML (§3 `FormYamlToggle`; návrh 05, změřeno z .pen: obal r9 p4, segment 44 px r7, 13 px). */
export function Toggle<K extends string>({ value, options, onChange, label }: {
  value: K; options: { key: K; label: ReactNode; /** Důvod, proč přepnout nejde (tooltip i text pro čtečku). */ disabled?: string }[];
  onChange: (k: K) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex gap-1 rounded-[9px] bg-nested p-1">
      {options.map((o) => (
        <button
          key={o.key} type="button" role="radio" aria-checked={o.key === value} aria-disabled={!!o.disabled || undefined}
          title={o.disabled} aria-description={o.disabled} onClick={() => !o.disabled && onChange(o.key)}
          className={`inline-flex h-11 items-center gap-2 rounded-[7px] px-3.5 text-[13px] ${o.key === value ? "bg-accent text-ink" : o.disabled ? "cursor-not-allowed text-fg-muted opacity-50" : "text-fg-muted hover:text-fg"}`}
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
