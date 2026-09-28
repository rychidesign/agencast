// Rozložení (redesign G5, G6, G14): sidebar 232 px + hlavní oblast; pod 1024 px lišta 56 px s drawerem navigace.
import { ArrowLeft, Blocks, Bot, History, Layers2, Menu as MenuIcon, Settings2, Workflow, X, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { API_BASE, enc, useApi } from "../api";
import { formatMoney, formatSpend } from "../format";
import { t } from "../i18n";
import { href, type Tab } from "../router";
import type { Project, Spend } from "../types";
import { btn, useDialog, useMedia } from "./ui";

const NAV: [Tab, LucideIcon][] = [["scenare", Workflow], ["agenti", Bot], ["behy", History], ["skilly", Blocks], ["config", Settings2]];

export function Shell({ project, tab, back, offline, children }: { project?: string; tab?: Tab; back?: boolean; offline?: boolean; children: ReactNode }) {
  const desktop = useMedia("(min-width: 1024px)", true);
  return (
    <div className="min-h-screen lg:flex">
      {desktop ? <Sidebar project={project} tab={tab} back={back || !!project} offline={offline} />
        : <TopBar project={project} tab={tab} back={back || !!project} offline={offline} />}
      <main className="mx-auto w-full max-w-[1240px] min-w-0 px-4 pt-6 pb-16 md:px-6 lg:px-8 lg:pt-8">{children}</main>
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
    <div className="sticky top-0 flex h-screen w-[232px] shrink-0 flex-col gap-[22px] overflow-y-auto border-r border-line bg-sidebar px-5 py-7">
      <Brand />
      <NavBody {...props} />
    </div>
  );
}

/** Do 1023 px: lišta 56 px (značka, projekt, ☰) a drawer přes celou výšku se stejnou navigací (položky 48 px). */
function TopBar(props: NavProps) {
  const [open, setOpen] = useState(false);
  const { project, offline } = props;
  return (
    <>
      <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-line bg-sidebar px-4 md:px-6">
        <Brand />
        {project && <p className="min-w-0 flex-1 truncate text-sm font-semibold" title={project}>{project}</p>}
        <button type="button" className={`${btn.iconGhost} ml-auto [&>svg]:size-5`} aria-label={t("shell.nav")} aria-expanded={open} aria-haspopup="dialog"
          onClick={() => setOpen(true)}>
          <MenuIcon aria-hidden />
        </button>
      </header>
      {offline && !open && (
        <p role="alert" data-testid="server-bar" className="border-b border-line bg-sidebar px-4 py-2 text-sm text-warning md:px-6">
          {t("server.offline", { host: API_BASE || location.host })}
        </p>
      )}
      {open && <Drawer {...props} onClose={() => setOpen(false)} />}
    </>
  );
}

function Drawer({ onClose, ...props }: NavProps & { onClose: () => void }) {
  const dialog = useDialog<HTMLDivElement>(onClose);
  // hashchange: odkaz v draweru (i na aktuální stránku) drawer zavře
  useEffect(() => {
    window.addEventListener("hashchange", onClose);
    return () => window.removeEventListener("hashchange", onClose);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 bg-canvas/70" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialog.ref} onKeyDown={dialog.onKeyDown} role="dialog" aria-modal="true" aria-label={t("shell.nav")} tabIndex={-1}
        onClick={(e) => (e.target as HTMLElement).closest("a") && onClose()}
        className="flex h-full w-[min(320px,100%)] flex-col gap-[22px] overflow-y-auto border-r border-line bg-sidebar px-5 pt-1.5 pb-7 focus:outline-none">
        <div className="-mr-2 flex h-14 shrink-0 items-center justify-between">
          <Brand />
          <button type="button" className={`${btn.iconGhost} [&>svg]:size-5`} onClick={onClose} aria-label={t("common.close")} title={t("common.close")}>
            <X aria-hidden />
          </button>
        </div>
        <NavBody {...props} drawer />
      </div>
    </div>
  );
}

function NavBody({ project, tab, back, offline, drawer = false }: NavProps & { drawer?: boolean }) {
  const item = drawer ? "h-12" : "h-11";
  return (
    <>
      {(back || drawer) && (
        <div>
          <a href="#/" className={`flex ${item} items-center gap-3 rounded-control px-3.5 text-sm font-medium text-fg-secondary hover:bg-surface-hover hover:text-fg`}>
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
                className={`group flex ${item} shrink-0 items-center gap-3 rounded-control px-3.5 text-sm font-medium ${k === tab ? "bg-surface-active text-fg" : "text-fg-secondary hover:bg-surface-hover hover:text-fg"}`}>
                <Icon className={`size-4 ${k === tab ? "text-fg" : "text-fg-muted group-hover:text-fg"}`} aria-hidden />{t(`project.tab.${k}`)}
              </a>
            ))}
          </nav>
          <div className="mt-auto"><SpendToday project={project} /></div>
        </>
      )}
      {offline && !drawer && (
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
