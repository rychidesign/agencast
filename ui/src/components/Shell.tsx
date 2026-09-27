// Rozložení (redesign G5, G6, G14): sidebar 232 px + hlavní oblast; pod 1024 px horní lišta.
import { ArrowLeft, Blocks, Bot, History, Layers2, Settings2, Workflow, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { API_BASE, enc, useApi } from "../api";
import { formatMoney } from "../format";
import { t } from "../i18n";
import { href, type Tab } from "../router";
import type { Project, Spend } from "../types";

const NAV: [Tab, LucideIcon][] = [["scenare", Workflow], ["agenti", Bot], ["behy", History], ["skilly", Blocks], ["config", Settings2]];

export function Shell({ project, tab, back, offline, children }: { project?: string; tab?: Tab; back?: boolean; offline?: boolean; children: ReactNode }) {
  return (
    <div className="min-h-screen lg:flex">
      <Sidebar project={project} tab={tab} back={back || !!project} offline={offline} />
      <main className="mx-auto w-full max-w-[1240px] min-w-0 px-4 pt-6 pb-16 sm:px-8 lg:pt-8">{children}</main>
    </div>
  );
}

/** Fidelity §3: 232 px, padding 28 20, značka 25/22 px, „← Projekty“ 44 px, oddělovač, položky 44 px, dole útrata. */
export function Sidebar({ project, tab, back, offline }: { project?: string; tab?: Tab; back?: boolean; offline?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-sidebar px-4 py-2 sm:px-8 lg:sticky lg:top-0 lg:h-screen lg:w-[232px] lg:shrink-0 lg:flex-col lg:flex-nowrap lg:items-stretch lg:gap-[22px] lg:overflow-y-auto lg:border-r lg:border-b-0 lg:px-5 lg:py-7">
      <a href="#/" className="flex h-11 items-center gap-2.5 text-[22px] font-semibold tracking-[-0.7px] lg:h-8">
        <Layers2 className="size-[25px] text-type" aria-hidden />agencast
      </a>
      {back && (
        <div className="hidden lg:block">
          <a href="#/" className="flex h-11 items-center gap-3 rounded-control px-3.5 text-sm font-medium text-fg-secondary hover:bg-surface-hover hover:text-fg">
            <ArrowLeft className="size-4" aria-hidden />{t("projects.title")}
          </a>
          <div className="mt-[22px] h-px bg-line" aria-hidden />
        </div>
      )}
      {project && (
        <>
          <p className="min-w-0 truncate text-sm font-semibold lg:-mb-2 lg:px-3.5" title={project}>{project}</p>
          <nav aria-label={t("project.tabs")}
            className="-mx-4 flex w-[calc(100%+2rem)] gap-1.5 overflow-x-auto px-4 sm:-mx-8 sm:w-[calc(100%+4rem)] sm:px-8 lg:mx-0 lg:w-auto lg:flex-col lg:overflow-visible lg:px-0">
            {NAV.map(([k, Icon]) => (
              <a key={k} href={href(project, k)} aria-current={k === tab ? "page" : undefined}
                className={`group flex h-11 shrink-0 items-center gap-3 rounded-control px-3.5 text-sm font-medium ${k === tab ? "bg-surface-active text-fg" : "text-fg-secondary hover:bg-surface-hover hover:text-fg"}`}>
                <Icon className={`size-4 ${k === tab ? "text-fg" : "text-fg-muted group-hover:text-fg"}`} aria-hidden />{t(`project.tab.${k}`)}
              </a>
            ))}
          </nav>
          <div className="hidden lg:mt-auto lg:block"><SpendToday project={project} /></div>
        </>
      )}
      {offline && (
        <p role="alert" data-testid="server-bar" className={`w-full text-sm text-warning ${project ? "" : "lg:mt-auto"}`}>
          {t("server.offline", { host: API_BASE || location.host })}
        </p>
      )}
    </div>
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
        {formatMoney(total)}{daily > 0 && ` / ${formatMoney(daily)}`} USD
      </p>
      {daily > 0 && (
        <div className="h-[3px] overflow-hidden rounded-full bg-track" aria-hidden>
          <div className={`h-full ${total > daily ? "bg-error" : "bg-success"}`} style={{ width: `${Math.min(100, (total / daily) * 100)}%` }} />
        </div>
      )}
    </div>
  );
}
