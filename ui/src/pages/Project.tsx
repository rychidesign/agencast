// §2.2 Přehled projektu: hlavička + záložky Scénáře · Agenti · Config · Skilly · Běhy.
import { ArrowLeft, RefreshCw } from "lucide-react";
import { useState } from "react";
import { enc, useApi, type Loaded } from "../api";
import { ErrorList, ErrorText, Loading, TabLinks } from "../components/ui";
import { formatCost, formatMoney } from "../format";
import { t } from "../i18n";
import { href, TABS, type Tab } from "../router";
import type { ErrorItem, Project, Spend } from "../types";
import { AgentsTab, SkillsTab } from "./Agents";
import { ConfigTab } from "./Config";
import { RunsTab } from "./Runs";
import { ScenariosTab } from "./Scenarios";


/** Všechny chyby validace projektu (projekt + soubory). */
export const allErrors = (p: Project): ErrorItem[] => [
  ...p.errors,
  ...[...p.scenarios, ...p.agents, ...p.skills].flatMap((x) => x.errors),
];

/** Odkaz z chyby na soubor a krok (`file` = cesta ve `workflows/`). */
export function errorHref(project: string, e: ErrorItem): string | undefined {
  const m = /^(scenarios|agents|skills)\/([^/]+?)(?:\.yaml|\.md|\/SKILL\.md)$/.exec(e.file ?? "");
  if (m?.[1] === "scenarios") return href(project, "scenare", m[2], { krok: e.step });
  if (m?.[1] === "agents") return href(project, "agenti", m[2]);
  if (m?.[1] === "skills") return href(project, "skilly", m[2]);
  if (e.file === "config.yaml" || e.file === "mcp.yaml") return href(project, "config");
  return undefined;
}

export function ProjectPage({ project, tab, item }: { project: string; tab: Tab; item?: string }) {
  const [gen, setGen] = useState(0);
  const detail = useApi<Project>(`/projects/${enc(project)}`);
  const reload = () => (detail.reload(), setGen(gen + 1));
  const p = detail.data;
  return (
    <main className="mx-auto max-w-6xl p-4 sm:p-8" key={gen}>
      <ProjectHeader name={project} detail={detail} onReload={reload} />
      <TabLinks
        label={t("project.tabs")} active={tab}
        tabs={TABS.map((k) => ({ key: k, label: t(`project.tab.${k}`), href: href(project, k) }))}
      />
      <div className="mt-6">
        {detail.error?.status === 422 && (
          <div role="alert" className="mb-6 space-y-2 rounded-xl bg-zinc-800/60 p-4">
            <p className="text-sm text-rose-400">{t("server.config", { error: detail.error.message })}</p>
            <ul className="list-inside list-disc font-mono text-[13px] text-zinc-300">
              {detail.error.details.map((d) => <li key={d}>{d}</li>)}
            </ul>
            {tab !== "config" && <a className="text-sm underline" href={href(project, "config")}>{t("server.openConfig")}</a>}
          </div>
        )}
        {detail.error && detail.error.status !== 422 && detail.error.status !== 0 && <ErrorText error={detail.error} />}
        {tab === "config" && (p || detail.error) && <ConfigTab name={project} project={p} onChanged={detail.reload} />}
        {tab === "behy" && <RunsTab project={project} />}
        {!p ? (
          tab !== "behy" && !detail.error && <Loading rows={4} />
        ) : (
          <>
            {tab === "scenare" && <ScenariosTab project={p} onChanged={detail.reload} />}
            {tab === "agenti" && <AgentsTab project={p} selected={item} onChanged={detail.reload} />}
            {tab === "skilly" && <SkillsTab project={p} selected={item} onChanged={detail.reload} />}
          </>
        )}
      </div>
    </main>
  );
}

function ProjectHeader({ name, detail, onReload }: { name: string; detail: Loaded<Project>; onReload: () => void }) {
  const p = detail.data;
  const spend = useApi<Spend>(`/projects/${enc(name)}/spend`);
  const daily = Number(p?.limits.daily_budget_usd) || 0;
  const runBudget = p?.limits.run_budget_usd;
  const errors = p ? allErrors(p) : [];
  return (
    <header className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2">
      <a href="#/" className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100">
        <ArrowLeft className="size-4" aria-hidden /> {t("projects.title")}
      </a>
      <h1 className="text-lg font-semibold">{name}</h1>
      {p && <span className="font-mono text-[13px] text-zinc-400">{p.root}</span>}
      {spend.data && (
        <span className="inline-flex items-center gap-2 text-sm">
          <span className="font-mono">
            {t("spend.today", { usd: formatCost(spend.data.total_usd) })}
            {daily > 0 && ` / ${formatMoney(daily)} USD`}
          </span>
          {daily > 0 && (
            <span className="h-1.5 w-20 overflow-hidden rounded-full bg-zinc-800" aria-hidden>
              <span className="block h-full bg-zinc-300" style={{ width: `${Math.min(100, (spend.data.total_usd / daily) * 100)}%` }} />
            </span>
          )}
        </span>
      )}
      {typeof runBudget === "number" && (
        <span className="text-sm text-zinc-400">
          {t("project.limits", { usd: formatMoney(runBudget), time: String(p?.limits.run_timeout ?? "–") })}
        </span>
      )}
      {errors.length > 0 && (
        <details className="relative text-sm">
          <summary className="cursor-pointer text-rose-400">{t("validation.count", { n: errors.length })}</summary>
          <div className="absolute z-20 mt-2 w-[36rem] max-w-[90vw] rounded-xl bg-zinc-800 p-4 ring-1 ring-zinc-700">
            <ErrorList errors={errors} hrefFor={(e) => errorHref(name, e)} />
          </div>
        </details>
      )}
      <button type="button" onClick={onReload} className="ml-auto grid size-8 place-items-center rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
        aria-label={t("common.reload")} title={t("common.reload")}>
        <RefreshCw className="size-4" aria-hidden />
      </button>
    </header>
  );
}
