// §2.6 Seznam běhů s filtry; obnovuje se každých 5 s, dokud něco běží nebo čeká (§4.8).
// Scénář filtruje server (`?scenario=`), stav klient; starší stránky bere přes `before`.
import { useEffect, useState } from "react";
import { enc, useApi } from "../api";
import { inputCls } from "../components/form";
import { RUN_STATUS } from "../components/RunBadge";
import { btn, EmptyState, ErrorText, Skeleton, StatusBadge, StatusIcon } from "../components/ui";
import {
  failReason, formatCost, formatDuration, formatWhen, isLive, runScenario, runStartedAt, utcTitle,
} from "../format";
import { t } from "../i18n";
import { href, setQuery, useLocation } from "../router";
import type { Project, RunListItem, RunState } from "../types";

export const RUNS_POLL_MS = 5000;
export const RUNS_PAGE = 50;

const selectCls = `${inputCls} w-auto!`;

const FILTERS: RunState[] = ["running", "queued", "interrupted", "succeeded", "failed", "dry_run"];

export function RunsTab({ project }: { project: string }) {
  const { query } = useLocation();
  const base = `/projects/${enc(project)}`;
  const scenario = query.get("scenar") ?? "";
  const state = query.get("stav") ?? "";
  const [before, setBefore] = useState<string>();
  const [olderRuns, setOlderRuns] = useState<RunListItem[]>([]);
  useEffect(() => { setBefore(undefined); setOlderRuns([]); }, [base, scenario]);
  const qs = new URLSearchParams({ ...(scenario ? { scenario } : {}), limit: String(RUNS_PAGE) });
  const runs = useApi<{ runs: RunListItem[]; next_before?: string }>(`${base}/runs?${qs}`, (d) => (d.runs.some((r) => isLive(r.state)) ? RUNS_POLL_MS : null));
  const pageQs = new URLSearchParams({ ...(scenario ? { scenario } : {}), limit: String(RUNS_PAGE), ...(before ? { before } : {}) });
  const page = useApi<{ runs: RunListItem[]; next_before?: string }>(before ? `${base}/runs?${pageQs}` : null);
  useEffect(() => {
    if (!before || !page.data) return;
    setOlderRuns((old) => {
      const seen = new Set([...(runs.data?.runs ?? []), ...old].map((r) => r.run_id));
      return [...old, ...page.data!.runs.filter((r) => !seen.has(r.run_id))];
    });
  }, [before, page.data, runs.data]);
  const detail = useApi<Project>(base);
  const first = runs.data?.runs ?? [];
  const all = [...first, ...olderRuns.filter((r) => !first.some((f) => f.run_id === r.run_id))];
  const nextBefore = before ? page.data?.next_before : runs.data?.next_before;
  const scenarios = [...new Set([...(detail.data?.scenarios.map((s) => s.name) ?? []), ...all.map(runScenario), ...(scenario ? [scenario] : [])])]
    .filter(Boolean).sort();
  const shown = all.filter((r) => !state || r.state === state);
  const nRunning = all.filter((r) => r.state === "running").length;
  const nQueued = all.filter((r) => r.state === "queued").length;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <label className="inline-flex items-center gap-2 text-fg-secondary">
          {t("runs.filter.scenario")}
          <select value={scenario} onChange={(e) => setQuery({ scenar: e.target.value || undefined })}
            className={selectCls}>
            <option value="">{t("runs.filter.all")}</option>
            {scenarios.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="inline-flex items-center gap-2 text-fg-secondary">
          {t("runs.filter.state")}
          <select value={state} onChange={(e) => setQuery({ stav: e.target.value || undefined })}
            className={selectCls}>
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
      {runs.loading && !runs.data && <div role="status" aria-label={t("common.loading")}><Skeleton className="h-[220px] rounded-card" /></div>}
      {runs.data && !shown.length && <EmptyState text={t("runs.empty")} cli={`agencast run ${scenario || "<scénář>"}`} />}
      {shown.length > 0 && (
        <div className="overflow-x-auto rounded-card bg-surface" tabIndex={0} role="region" aria-label={t("project.tab.behy")}>
        <table className="w-full min-w-[40rem] text-sm">
          <caption className="sr-only">{t("project.tab.behy")}</caption>
          <thead className="sr-only">
            <tr><th>{t("runs.col.state")}</th><th>{t("runs.col.scenario")}</th><th>{t("runs.col.when")}</th>
              <th>{t("runs.col.duration")}</th><th>{t("runs.col.cost")}</th><th>{t("runs.col.note")}</th></tr>
          </thead>
          <tbody>
            {shown.map((r) => <RunRow key={r.run_id} project={project} run={r} />)}
          </tbody>
        </table>
        </div>
      )}
      {nextBefore && (
        <button type="button" className={btn.secondary} disabled={page.loading} onClick={() => setBefore(nextBefore)}>{t("runs.more")}</button>
      )}
    </div>
  );
}

function RunRow({ project, run: r }: { project: string; run: RunListItem }) {
  const { state } = r;
  const when = runStartedAt(r);
  let what: string;
  if (state === "running")
    what = r.current_step
      ? t("runs.runningStep", { n: r.current_nn ?? (r.steps_done ?? 0) + 1, total: r.steps_total ?? "?", step: r.current_step })
      : t("run.state.running");
  else if (state === "queued") what = t("runs.queued", { n: r.queue_position ?? "?" });
  else what = formatWhen(when);
  const note = [
    state === "failed" ? failReason(r.status) : "",
    r.fake ? t("run.fake") : "",
    r.callback ?? "",
  ].filter(Boolean).join(" · ");
  return (
    <tr data-testid={`run-row-${r.run_id}`} title={r.run_id} className="relative border-t border-line first:border-t-0 hover:bg-surface-hover">
      <td className="py-2.5 pr-4 pl-4 whitespace-nowrap"><StatusBadge status={RUN_STATUS[state]}>{t(`run.state.${state}`)}</StatusBadge></td>
      <td className="pr-4 font-mono text-[13px]">
        <a href={href(project, "behy", r.run_id)} className="after:absolute after:inset-0">{runScenario(r) || r.run_id}</a>
      </td>
      <td className="pr-4 whitespace-nowrap text-fg-secondary" title={utcTitle(when)}>{what}</td>
      <td className="pr-4 text-right font-mono text-[13px] whitespace-nowrap">{r.duration_s != null ? formatDuration(r.duration_s) : ""}</td>
      <td className="pr-4 text-right font-mono text-[13px] whitespace-nowrap">{r.cost_usd != null ? formatCost(r.cost_usd) : ""}</td>
      <td className="pr-4 text-fg-muted">{note}</td>
    </tr>
  );
}
