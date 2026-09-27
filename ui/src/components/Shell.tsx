// Rozložení (redesign G5, G6, G14): sidebar 232 px + hlavní oblast; pod 1024 px horní lišta.
import { Blocks, Bot, History, Layers2, Settings2, Workflow, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { API_BASE, enc, useApi } from "../api";
import { formatMoney } from "../format";
import { t } from "../i18n";
import { href, type Tab } from "../router";
import type { Project, Spend } from "../types";
import { BackLink } from "./PageHeader";

const NAV: [Tab, LucideIcon][] = [["scenare", Workflow], ["agenti", Bot], ["behy", History], ["skilly", Blocks], ["config", Settings2]];

export function Shell({ project, tab, offline, children }: { project?: string; tab?: Tab; offline?: boolean; children: ReactNode }) {
  return (
    <div className="min-h-screen lg:flex">
      <Sidebar project={project} tab={tab} offline={offline} />
      <main className="mx-auto w-full max-w-[1200px] min-w-0 px-4 pt-6 pb-16 sm:px-8 lg:pt-8">{children}</main>
    </div>
  );
}

export function Sidebar({ project, tab, offline }: { project?: string; tab?: Tab; offline?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-sidebar px-4 py-2 sm:px-8 lg:sticky lg:top-0 lg:h-screen lg:w-[232px] lg:shrink-0 lg:flex-col lg:flex-nowrap lg:items-stretch lg:gap-5 lg:border-r lg:border-b-0 lg:px-5 lg:py-7">
      <a href="#/" className="flex h-11 items-center gap-2.5 text-[22px] font-semibold tracking-tight">
        <Layers2 className="size-6 text-type" aria-hidden />agencast
      </a>
      {project && (
        <>
          <div className="hidden lg:block"><BackLink href="#/">{t("projects.title")}</BackLink></div>
          <p className="min-w-0 truncate font-semibold lg:border-t lg:border-line lg:pt-5" title={project}>{project}</p>
          <nav aria-label={t("project.tabs")}
            className="-mx-4 flex w-[calc(100%+2rem)] gap-1 overflow-x-auto px-4 sm:-mx-8 sm:w-[calc(100%+4rem)] sm:px-8 lg:mx-0 lg:w-auto lg:flex-col lg:overflow-visible lg:px-0">
            {NAV.map(([k, Icon]) => (
              <a key={k} href={href(project, k)} aria-current={k === tab ? "page" : undefined}
                className={`flex h-11 shrink-0 items-center gap-3 rounded-control px-3.5 text-sm font-medium ${k === tab ? "bg-surface text-fg" : "text-fg-secondary hover:bg-surface-hover hover:text-fg"}`}>
                <Icon className="size-4" aria-hidden />{t(`project.tab.${k}`)}
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
    <div className="space-y-2">
      <p className="text-xs text-fg-muted">{t("spend.label")}</p>
      <p className="font-mono text-xs" data-testid="spend-today">
        {formatMoney(total)}{daily > 0 && ` / ${formatMoney(daily)}`} USD
      </p>
      {daily > 0 && (
        <div className="h-[3px] overflow-hidden rounded-full bg-nested" aria-hidden>
          <div className={`h-full ${total > daily ? "bg-error" : "bg-success"}`} style={{ width: `${Math.min(100, (total / daily) * 100)}%` }} />
        </div>
      )}
    </div>
  );
}
