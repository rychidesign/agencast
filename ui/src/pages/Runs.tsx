// §2.6 Seznam běhů s filtry; obnovuje se každých 5 s, dokud něco běží nebo čeká (§4.8).
import { enc, useApi } from "../api";
import { RUN_STATUS } from "../components/RunBadge";
import { EmptyState, ErrorText, Loading, StatusIcon } from "../components/ui";
import {
  failReason, formatCost, formatDuration, formatMoney, formatWhen, isLive, runScenario, runStartedAt, runState, utcTitle,
  type RunState,
} from "../format";
import { t } from "../i18n";
import { href, setQuery, useLocation } from "../router";
import type { Project, RunListItem, Spend } from "../types";

export const RUNS_POLL_MS = 5000;

const FILTERS: RunState[] = ["running", "queued", "succeeded", "failed", "dry-run"];

export function RunsTab({ project }: { project: string }) {
  const { query } = useLocation();
  const base = `/projects/${enc(project)}`;
  const runs = useApi<{ runs: RunListItem[] }>(`${base}/runs`, (d) => (d.runs.some((r) => isLive(r.status)) ? RUNS_POLL_MS : null));
  const spend = useApi<Spend>(`${base}/spend`);
  const detail = useApi<Project>(base);
  const scenario = query.get("scenar") ?? "";
  const state = query.get("stav") ?? "";
  const all = runs.data?.runs ?? [];
  const scenarios = [...new Set(all.map(runScenario))].sort();
  const shown = all.filter((r) => (!scenario || runScenario(r) === scenario) && (!state || runState(r.status) === state));
  const nRunning = all.filter((r) => runState(r.status) === "running").length;
  const nQueued = all.filter((r) => r.status === "queued").length;
  const daily = Number(detail.data?.limits.daily_budget_usd) || 0;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        {spend.data && (
          <span className="font-mono">
            {t("spend.today", { usd: formatCost(spend.data.total_usd) })}{daily > 0 && ` / ${formatMoney(daily)} USD`}
          </span>
        )}
        <label className="inline-flex items-center gap-2 text-zinc-400">
          {t("runs.filter.scenario")}
          <select value={scenario} onChange={(e) => setQuery({ scenar: e.target.value || undefined })}
            className="h-8 rounded-lg bg-zinc-800 px-2 text-zinc-100">
            <option value="">{t("runs.filter.all")}</option>
            {[...new Set([...scenarios, ...(scenario ? [scenario] : [])])].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="inline-flex items-center gap-2 text-zinc-400">
          {t("runs.filter.state")}
          <select value={state} onChange={(e) => setQuery({ stav: e.target.value || undefined })}
            className="h-8 rounded-lg bg-zinc-800 px-2 text-zinc-100">
            <option value="">{t("runs.filter.all")}</option>
            {FILTERS.map((f) => <option key={f} value={f}>{t(`run.state.${f}`)}</option>)}
          </select>
        </label>
        {(nRunning > 0 || nQueued > 0) && (
          <span className="ml-auto inline-flex items-center gap-1.5" aria-live="polite">
            <StatusIcon status="running" label="" />
            {t("runs.live", { running: nRunning, queued: nQueued })}
          </span>
        )}
      </div>
      {runs.error && runs.error.status !== 0 && <ErrorText error={runs.error} />}
      {runs.loading && !runs.data && <Loading rows={5} />}
      {runs.data && !shown.length && <EmptyState text={t("runs.empty")} cli={`agencast run ${scenario || "<scénář>"}`} />}
      {shown.length > 0 && (
        <table className="w-full text-sm">
          <caption className="sr-only">{t("project.tab.behy")}</caption>
          <thead className="sr-only">
            <tr><th>{t("runs.col.state")}</th><th>run_id</th><th>{t("runs.col.scenario")}</th><th>{t("runs.col.when")}</th>
              <th>{t("runs.col.duration")}</th><th>{t("runs.col.cost")}</th><th>{t("runs.col.note")}</th></tr>
          </thead>
          <tbody>
            {shown.map((r) => <RunRow key={r.run_id} project={project} run={r} queuePos={all.filter((x) => x.status === "queued").indexOf(r)} />)}
          </tbody>
        </table>
      )}
    </div>
  );
}

function RunRow({ project, run: r, queuePos }: { project: string; run: RunListItem; queuePos: number }) {
  const state = runState(r.status);
  const when = runStartedAt(r);
  let what: string;
  if (state === "running")
    what = r.current_step ? t("runs.runningStep", { step: r.current_step, total: r.steps_total ?? "?" }) : t("run.state.running");
  else if (state === "queued") what = t("runs.queued", { n: queuePos + 1 });
  else what = formatWhen(when);
  const note = [state === "failed" ? failReason(r.status) : "", state === "dry-run" ? t("run.state.dry-run") : "", r.callback ?? ""]
    .filter(Boolean).join(" · ");
  return (
    <tr className="relative hover:bg-zinc-800/60">
      <td className="w-8 py-2 pl-3"><StatusIcon status={RUN_STATUS[state]} label={t(`run.state.${state}`)} /></td>
      <td className="py-2 pr-4 font-mono text-[13px]">
        <a href={href(project, "behy", r.run_id)} className="after:absolute after:inset-0">{r.run_id}</a>
      </td>
      <td className="pr-4 font-mono text-[13px] text-zinc-300">{runScenario(r)}</td>
      <td className="pr-4 text-zinc-300" title={utcTitle(when)}>{what}</td>
      <td className="pr-4 text-right font-mono text-[13px]">{r.duration_s != null ? formatDuration(r.duration_s) : ""}</td>
      <td className="pr-4 text-right font-mono text-[13px]">{r.cost_usd != null ? formatCost(r.cost_usd) : ""}</td>
      <td className="pr-3 text-zinc-400">{note}</td>
    </tr>
  );
}
