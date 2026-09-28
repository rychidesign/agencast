// Rozložení: sidebar 232 px; pod 1024 px kontextová lišta a FAB navigace.
import { ArrowLeft, Blocks, Bot, History, Layers2, Menu as MenuIcon, Settings2, Workflow, X, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { API_BASE, enc, useApi } from "../api";
import { formatMoney, formatSpend } from "../format";
import { t } from "../i18n";
import { href, type Tab } from "../router";
import type { Project, Spend } from "../types";
import { useDialog, useMedia } from "./ui";

const NAV: [Tab, LucideIcon][] = [["scenare", Workflow], ["agenti", Bot], ["behy", History], ["skilly", Blocks], ["config", Settings2]];

export function Shell({ project, tab, back, offline, children }: { project?: string; tab?: Tab; back?: boolean; offline?: boolean; children: ReactNode }) {
  const desktop = useMedia("(min-width: 1024px)", true);
  return (
    <div className="min-h-screen lg:flex">
      {desktop ? <Sidebar project={project} tab={tab} back={back || !!project} offline={offline} />
        : <TopBar project={project} tab={tab} back={back || !!project} offline={offline} />}
      <main className="mx-auto w-full max-w-[1240px] min-w-0 px-4 pt-6 pb-28 md:px-6 lg:px-8 lg:pt-8 lg:pb-16">{children}</main>
    </div>
  );
}

type NavProps = { project?: string; tab?: Tab; back?: boolean; offline?: boolean };

const Brand = () => (
  <a href="#/" className="flex h-11 shrink-0 items-center gap-2.5 text-[22px] font-semibold tracking-[-0.7px] lg:h-8">
    <Layers2 className="size-[25px] text-type" aria-hidden />agencast
  </a>
);

/** Fidelity §3: 232 px, padding 28 20, značka 25/22 px, „← Projekty“ 44 px, oddělovač, položky 44 px, dole útrata. */
export function Sidebar(props: NavProps) {
  return (
    <div className="sticky top-0 flex h-screen w-[232px] shrink-0 flex-col gap-[22px] scroll-quiet overflow-y-auto border-r border-line bg-sidebar px-5 py-7">
      <Brand />
      <NavBody {...props} />
    </div>
  );
}

/** Do 1023 px: lišta s kontextem projektu a navigace nad FAB. */
function TopBar(props: NavProps) {
  const [open, setOpen] = useState(false);
  const { project, offline } = props;
  const close = () => setOpen(false);
  const dialog = useDialog<HTMLDivElement>(close, open);
  useEffect(() => {
    if (!open) return;
    dialog.ref.current?.querySelector<HTMLElement>("a")?.focus();
    window.addEventListener("hashchange", close);
    return () => window.removeEventListener("hashchange", close);
  }, [open]);
  return (
    <>
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-sidebar px-4 md:px-6">
        <Brand />
        {project && <p className="min-w-0 flex-1 truncate text-sm font-semibold" title={project}>{project}</p>}
      </header>
      {offline && (
        <p role="alert" data-testid="server-bar" className="border-b border-line bg-sidebar px-4 py-2 text-sm text-warning md:px-6">
          {t("server.offline", { host: API_BASE || location.host })}
        </p>
      )}
      {project && <>
        {open && <div className="fixed inset-0 z-40 bg-canvas/60" onMouseDown={close} aria-hidden />}
        {open && <div ref={dialog.ref} onKeyDown={dialog.onKeyDown} role="dialog" aria-modal="true" aria-label={t("shell.nav")} tabIndex={-1}
          onClick={(e) => (e.target as HTMLElement).closest("a") && close()}
          className="popover pop-enter fixed right-4 bottom-[calc(84px+env(safe-area-inset-bottom))] z-50 flex max-h-[calc(100dvh-108px)] w-[min(260px,calc(100vw-32px))] flex-col gap-1 scroll-quiet overflow-y-auto p-2 focus:outline-none">
          <a href="#/" className="flex h-12 shrink-0 items-center gap-3 rounded-[7px] px-3 text-sm font-medium text-fg-secondary hover:bg-surface-active hover:text-fg">
            <ArrowLeft className="size-4" aria-hidden />{t("projects.title")}
          </a>
          <p className="truncate px-3 py-2 text-[13px] font-semibold text-fg-secondary" title={project}>{project}</p>
          <nav aria-label={t("project.tabs")} className="flex flex-col gap-1">
            {NAV.map(([k, Icon]) => <a key={k} href={href(project, k)} aria-current={k === props.tab ? "page" : undefined}
              className={`flex h-12 shrink-0 items-center gap-3 rounded-[7px] px-3 text-sm font-medium ${k === props.tab ? "bg-surface-active text-fg" : "text-fg-secondary hover:bg-surface-active hover:text-fg"}`}>
              <Icon className="size-4" aria-hidden />{t(`project.tab.${k}`)}
            </a>)}
          </nav>
          <div className="border-t border-line px-3 pt-3 pb-2"><SpendToday project={project} /></div>
        </div>}
        <button type="button" className={`fixed right-4 bottom-[calc(16px+env(safe-area-inset-bottom))] ${open ? "z-50" : "z-30"} grid size-14 place-items-center rounded-full bg-accent text-ink shadow-[var(--shadow-pop)] transition-transform active:scale-95 motion-reduce:transition-none`}
          aria-label={t("shell.nav")} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? <X className="size-6 motion-safe:animate-[fab-turn_150ms_ease-out]" aria-hidden /> : <MenuIcon className="size-6 motion-safe:animate-[fab-turn_150ms_ease-out]" aria-hidden />}
        </button>
      </>}
    </>
  );
}

function NavBody({ project, tab, back, offline }: NavProps) {
  return (
    <>
      {back && (
        <div>
          <a href="#/" className="flex h-11 items-center gap-3 rounded-control px-3.5 text-sm font-medium text-fg-secondary hover:bg-surface-hover hover:text-fg">
            <ArrowLeft className="size-4" aria-hidden />{t("projects.title")}
          </a>
          {project && <div className="mt-[22px] h-px bg-line" aria-hidden />}
        </div>
      )}
      {project && (
        <>
          <p className="-mb-2 min-w-0 truncate px-3.5 text-sm font-semibold" title={project}>{project}</p>
          <nav aria-label={t("project.tabs")} className="flex flex-col gap-1.5">
            {NAV.map(([k, Icon]) => (
              <a key={k} href={href(project, k)} aria-current={k === tab ? "page" : undefined}
                className={`group flex h-11 shrink-0 items-center gap-3 rounded-control px-3.5 text-sm font-medium ${k === tab ? "bg-surface-active text-fg" : "text-fg-secondary hover:bg-surface-hover hover:text-fg"}`}>
                <Icon className={`size-4 ${k === tab ? "text-fg" : "text-fg-muted group-hover:text-fg"}`} aria-hidden />{t(`project.tab.${k}`)}
              </a>
            ))}
          </nav>
          <div className="mt-auto"><SpendToday project={project} /></div>
        </>
      )}
      {offline && (
        <p role="alert" data-testid="server-bar" className={`w-full text-sm text-warning ${project ? "" : "mt-auto"}`}>
          {t("server.offline", { host: API_BASE || location.host })}
        </p>
      )}
    </>
  );
}

/** „Dnes utraceno 1,20 / 5,00 USD“ s pruhem; bez denního limitu jen částka. */
function SpendToday({ project }: { project: string }) {
  const spend = useApi<Spend>(`/projects/${enc(project)}/spend`);
  const detail = useApi<Project>(`/projects/${enc(project)}`);
  if (!spend.data) return null;
  const total = spend.data.total_usd;
  const daily = Number(detail.data?.limits.daily_budget_usd) || 0;
  return (
    <div className="space-y-2.5">
      <p className="text-xs text-fg-muted">{t("spend.label")}</p>
      <p className="font-mono text-xs font-medium" data-testid="spend-today">
        {formatSpend(total)}{daily > 0 && ` / ${formatMoney(daily)}`} USD
      </p>
      {daily > 0 && (
        <div className="h-[3px] overflow-hidden rounded-full bg-track" aria-hidden>
          <div className={`h-full ${total > daily ? "bg-error" : "bg-success"}`} style={{ width: `${Math.min(100, (total / daily) * 100)}%` }} />
        </div>
      )}
    </div>
  );
}
