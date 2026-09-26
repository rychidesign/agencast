// §2.2 Záložka Scénáře: mřížka karet scénářů.
import { Plus } from "lucide-react";
import { enc, useApi } from "../api";
import { LastRun } from "../components/RunBadge";
import { IconChain } from "../components/TypeIcon";
import { CliLine, EmptyState, Menu, Skeleton, StatusChip } from "../components/ui";
import { formatWhen, runScenario, runStartedAt, utcTitle } from "../format";
import { t } from "../i18n";
import { href, navigate } from "../router";
import type { Project, RunListItem, Scenario, ScenarioSummary } from "../types";

/** Příkaz spuštění z CLI; povinné vstupy bez `default` jako `-i jmeno=…`. */
export function runCommand(root: string, s: ScenarioSummary): string {
  const inputs = Object.entries(s.inputs ?? {})
    .filter(([, v]) => v.required && v.default === undefined)
    .map(([k]) => ` -i ${k}=…`)
    .join("");
  return `agencast --project ${root} run ${s.name}${inputs}`;
}

export function ScenariosTab({ project }: { project: Project }) {
  const runs = useApi<{ runs: RunListItem[] }>(`/projects/${enc(project.name)}/runs`);
  const lastRun = (name: string) => runs.data?.runs.find((r) => r.status !== "queued" && runScenario(r) === name);
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4">
      <li className="flex min-h-52 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-zinc-600 p-5 text-zinc-300">
        <Plus className="size-6" aria-hidden />
        <p className="text-sm">{t("scenarios.new")}</p>
        <CliLine cmd={`agencast --project ${project.root} new scenario <jméno>`} className="w-full" />
      </li>
      {project.scenarios.map((s) => (
        <ScenarioCard key={s.name} project={project} scenario={s} lastRun={runs.data ? lastRun(s.name) ?? null : undefined} />
      ))}
      {!project.scenarios.length && <li><EmptyState text={t("scenarios.empty")} /></li>}
    </ul>
  );
}

function ScenarioCard({ project, scenario: s, lastRun }: {
  project: Project; scenario: ScenarioSummary; lastRun: RunListItem | null | undefined;
}) {
  // ponytail: jeden GET na scénář kvůli řetězci ikon; až API dá typy kroků v přehledu, odpadne (nalezy-api.md).
  const detail = useApi<Scenario>(`/projects/${enc(project.name)}/scenarios/${enc(s.name)}`);
  const open = href(project.name, "scenare", s.name);
  const agents = project.links.scenario_agent.filter(([sc]) => sc === s.name).map(([, a]) => a);
  const nIn = Object.keys(s.inputs ?? {}).length;
  const nOut = Object.keys(s.outputs ?? {}).length;
  const meta = [
    t("count.steps", { n: s.steps_count }),
    agents.join(", "),
    nIn ? t("count.inputs", { n: nIn }) : "",
    nOut ? t("count.outputs", { n: nOut }) : "",
    s.callable ? t("scenario.callable") : "",
  ].filter(Boolean);
  const menu = [
    { label: t("common.open"), onSelect: () => navigate(open) },
    { label: t("scenarios.runsOf"), onSelect: () => navigate(href(project.name, "behy", undefined, { scenar: s.name })) },
    { label: t("scenarios.copyRun"), onSelect: () => navigator.clipboard.writeText(runCommand(project.root, s)) },
  ];
  const when = lastRun ? lastRun.finished_at ?? runStartedAt(lastRun) : null;
  return (
    <li className="relative flex min-h-52 flex-col rounded-xl bg-zinc-800/60 p-5 hover:bg-zinc-800">
      <div className="flex flex-wrap items-center gap-3">
        {detail.data ? <IconChain types={detail.data.steps.map((st) => st.type)} /> : <Skeleton className="h-8 w-40" />}
        <div className="relative z-10 ml-auto flex items-center gap-1 whitespace-nowrap">
          {s.errors.length > 0 ? (
            <StatusChip status="failed">{t("validation.count", { n: s.errors.length })}</StatusChip>
          ) : (
            lastRun !== undefined && <LastRun run={lastRun ?? undefined} />
          )}
          <Menu items={menu} label={t("common.menuFor", { name: s.name })} />
        </div>
      </div>
      <h2 className="mt-4 text-lg leading-snug font-semibold">
        <a href={open} className="after:absolute after:inset-0 after:rounded-xl">{s.description || s.name}</a>
      </h2>
      <p className="mt-1 text-[13px] text-zinc-400">{meta.join(" · ")}</p>
      <div className="mt-auto flex items-center justify-between pt-4 text-[13px] text-zinc-400">
        <span className="font-mono">{s.name}.yaml</span>
        <span title={utcTitle(when)}>{lastRun === undefined ? "" : when ? formatWhen(when) : t("runs.none")}</span>
      </div>
    </li>
  );
}
