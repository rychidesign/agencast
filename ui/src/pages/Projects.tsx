// §2.1 Seznam projektů (karty).
import { Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { enc, useApi } from "../api";
import { CliLine, ErrorText, Menu, Skeleton } from "../components/ui";
import { formatCost } from "../format";
import { t } from "../i18n";
import { href, navigate } from "../router";
import type { Project, ProjectRef, RunListItem, Spend } from "../types";
import { LastRun } from "../components/RunBadge";

export function ProjectsPage() {
  const [gen, setGen] = useState(0);
  const list = useApi<{ projects: ProjectRef[] }>("/projects");
  return (
    <main className="mx-auto max-w-6xl p-8">
      <header className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("projects.title")}</h1>
          <p className="text-sm text-zinc-400">{t("projects.subtitle")}</p>
        </div>
        <button type="button" className="grid size-8 place-items-center rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          onClick={() => (list.reload(), setGen(gen + 1))} aria-label={t("common.reload")} title={t("common.reload")}>
          <RefreshCw className="size-4" aria-hidden />
        </button>
      </header>
      {list.error && list.error.status !== 0 && <ErrorText error={list.error} />}
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4">
        <li className="flex min-h-44 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-zinc-600 p-5 text-zinc-300">
          <Plus className="size-6" aria-hidden />
          <p className="text-sm">{t("projects.add")}</p>
          <CliLine cmd="agencast projects add <cesta>" className="w-full" />
        </li>
        {list.loading && !list.data && [0, 1].map((i) => <li key={i}><Skeleton className="h-44 rounded-xl" /></li>)}
        {list.data?.projects.map((p) => <ProjectCard key={`${p.name}-${gen}`} project={p} />)}
      </ul>
    </main>
  );
}

function ProjectCard({ project }: { project: ProjectRef }) {
  const base = `/projects/${enc(project.name)}`;
  // Nedostupný projekt vrací 404 s důvodem — ten ukážeme místo patičky.
  const detail = useApi<Project>(base);
  const spend = useApi<Spend>(project.available ? `${base}/spend` : null);
  const runs = useApi<{ runs: RunListItem[] }>(project.available ? `${base}/runs` : null);
  const open = href(project.name);
  const menu = [
    { label: t("common.open"), onSelect: () => navigate(open) },
    { label: t("projects.copyPath"), onSelect: () => navigator.clipboard.writeText(project.root) },
  ];
  const p = detail.data;
  return (
    <li className={`relative flex min-h-44 flex-col rounded-xl p-5 ${project.available ? "bg-zinc-800/60 hover:bg-zinc-800" : "border border-dashed border-zinc-600 opacity-50"}`}>
      <div className="flex items-center justify-between text-xs text-zinc-400">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className={`size-2 rounded-full ${project.available ? "bg-emerald-400" : "ring-1 ring-zinc-400"}`} />
          {project.available ? t("projects.available") : t("projects.unavailable")}
        </span>
        <div className="relative z-10"><Menu items={menu} label={t("common.menuFor", { name: project.name })} /></div>
      </div>
      <h2 className="mt-2 text-lg font-semibold">
        <a href={open} className="after:absolute after:inset-0 after:rounded-xl">{project.name}</a>
      </h2>
      <p className="truncate font-mono text-[13px] text-zinc-400" title={project.root}>{project.root}</p>
      <div className="mt-auto pt-4 text-[13px] text-zinc-300">
        {!project.available || detail.error ? (
          <p className="text-zinc-300">{detail.error?.message ?? t("projects.unavailable")}</p>
        ) : !p ? (
          <Skeleton className="h-4 w-2/3" />
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {t("count.scenarios", { n: p.scenarios.length })} · {t("count.agents", { n: p.agents.length })}
            </span>
            <span className="inline-flex items-center gap-2">
              {spend.data && <span className="font-mono">{t("spend.today", { usd: formatCost(spend.data.total_usd) })}</span>}
              {runs.data && <LastRun run={runs.data.runs.find((r) => r.status !== "queued")} />}
            </span>
          </div>
        )}
      </div>
    </li>
  );
}
