// §2.6 Seznam běhů s filtry; obnovuje se každých 5 s, dokud něco běží nebo čeká (§4.8).
// Scénář filtruje server (`?scenario=`), stav a hledání klient; starší stránky bere přes `before`.
// Fidelity §8: filtrační karta, záhlaví sloupců, řádky jako karty 80 px.
import { Activity, ChevronDown, ChevronRight, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { enc, useApi } from "../api";
import { inputCls } from "../components/form";
import { RUN_STATUS } from "../components/RunBadge";
import { btn, EmptyState, ErrorText, Skeleton, StatusIcon } from "../components/ui";
import {
  failReason, formatCost, formatDuration, formatElapsed, formatWhen, isLive, runScenario, runStartedAt, utcTitle,
} from "../format";
import { t } from "../i18n";
import { href, setQuery, useLocation } from "../router";
import type { Project, RunListItem, RunState } from "../types";
import type { SectionHeader } from "./Project";

export const RUNS_POLL_MS = 5000;
export const RUNS_PAGE = 50;

const FILTERS: RunState[] = ["running", "queued", "interrupted", "succeeded", "failed", "dry_run"];

/** Barva textu stavu v řádku (stav je vždy i slovem, barva jen zvýrazní). */
const STATE_COLOR: Record<RunState, string> = {
  running: "text-running", succeeded: "text-success", failed: "text-error", interrupted: "text-warning",
  cancelled: "text-warning", queued: "text-fg-secondary", dry_run: "text-fg-secondary",
};

export function RunsTab({ project, header }: { project: string; header: SectionHeader }) {
  const { query } = useLocation();
  const base = `/projects/${enc(project)}`;
  const scenario = query.get("scenar") ?? "";
  const state = query.get("stav") ?? "";
  const [search, setSearch] = useState("");
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
  const needle = search.trim().toLowerCase();
  const shown = all.filter((r) => (!state || r.state === state)
    && (!needle || runScenario(r).toLowerCase().includes(needle) || r.run_id.toLowerCase().includes(needle)));
  const nRunning = all.filter((r) => r.state === "running").length;
  const nQueued = all.filter((r) => r.state === "queued").length;
  return (
    <>
      {header({
        meta: (nRunning > 0 || nQueued > 0) && (
          <span className="inline-flex items-center gap-2 rounded-full bg-nested px-2.5 py-[7px] font-mono text-xs font-medium text-running" aria-live="polite">
            <Activity className="size-3.5" aria-hidden />{t("runs.live", { running: nRunning, queued: nQueued })}
          </span>
        ),
      })}
      <div className="space-y-4">
        {/* návrh 04 (změřeno z .pen): filtry radius 14, padding 12, mezera 10, selecty 210 px; řádek 72 px, radius 8 */}
        <div className="flex flex-wrap gap-2.5 rounded-tile bg-surface p-3 ring-1 ring-line">
          <div className="relative min-w-[min(16rem,100%)] flex-[2]">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-[18px] -translate-y-1/2 text-fg-muted" aria-hidden />
            <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} aria-label={t("runs.search")}
              placeholder={t("runs.search")} className={`${inputCls} pl-10`} />
          </div>
          <select value={state} onChange={(e) => setQuery({ stav: e.target.value || undefined })} aria-label={t("runs.filter.stateLabel")}
            className={`${inputCls.replace("w-full", "w-[210px]")} max-sm:flex-1`}>
            <option value="">{t("runs.filter.allStates")}</option>
            {FILTERS.map((f) => <option key={f} value={f}>{t(`run.state.${f}`)}</option>)}
          </select>
          <select value={scenario} onChange={(e) => setQuery({ scenar: e.target.value || undefined })} aria-label={t("runs.filter.scenarioLabel")}
            className={`${inputCls.replace("w-full", "w-[210px]")} max-sm:flex-1`}>
            <option value="">{t("runs.filter.allScenarios")}</option>
            {scenarios.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        {runs.error && runs.error.status !== 0 && <ErrorText error={runs.error} />}
        {runs.loading && !runs.data && <div role="status" aria-label={t("common.loading")}><Skeleton className="h-[264px] rounded-card" /></div>}
        {runs.data && !shown.length && <EmptyState text={t("runs.empty")} cli={`agencast run ${scenario || "<scénář>"}`} />}
        {shown.length > 0 && (
          <div className="relative -my-2 overflow-x-auto" tabIndex={0} role="region" aria-label={t("project.tab.behy")}>
            <table className="w-full min-w-[46rem] border-separate border-spacing-y-2 text-sm">
              <caption className="sr-only">{t("project.tab.behy")}</caption>
              <thead>
                <tr className="font-mono text-[10px] text-fg-muted uppercase [&>th]:pb-1 [&>th]:font-normal">
                  <th className="pr-4 pl-[58px] text-left">{t("runs.col.scenarioId")}</th>
                  <th className="pr-4 text-left">{t("runs.col.state")}</th>
                  <th className="pr-4 text-left">{t("runs.col.when")}</th>
                  <th className="pr-4 text-right">{t("runs.col.duration")}</th>
                  <th className="pr-4 text-right">{t("runs.col.price")}</th>
                  <th><span className="sr-only">{t("common.open")}</span></th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => <RunRow key={r.run_id} project={project} run={r} />)}
              </tbody>
            </table>
          </div>
        )}
        {nextBefore && (
          <button type="button" className={btn.secondary} disabled={page.loading} onClick={() => setBefore(nextBefore)}>
            <ChevronDown className="size-4" aria-hidden />{t("runs.more")}
          </button>
        )}
      </div>
    </>
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
  const reason = state === "failed" ? failReason(r.status) : "";
  const note = [r.fake ? t("run.fake") : "", r.callback ?? ""].filter(Boolean).join(" · ");
  // běžící běh ukazuje čas od startu; obnoví se s pollingem seznamu (5 s)
  const duration = r.duration_s != null ? formatDuration(r.duration_s) : state === "running" ? formatElapsed(when) : "–";
  return (
    <tr data-testid={`run-row-${r.run_id}`} title={r.run_id}
      className="relative h-[72px] [&>td]:bg-surface hover:[&>td]:bg-surface-hover">
      <td className="rounded-l-control py-3 pr-4 pl-5">
        <div className="flex items-center gap-[18px]">
          <StatusIcon status={RUN_STATUS[state]} label="" className="size-5" />
          <div className="min-w-0">
            <a href={href(project, "behy", r.run_id)} className="block truncate text-sm font-semibold text-fg after:absolute after:inset-0">
              {runScenario(r) || r.run_id}
            </a>
            <p className="mt-1 truncate font-mono text-[11px] leading-4 text-fg-muted">{r.run_id}{note && ` · ${note}`}</p>
          </div>
        </div>
      </td>
      <td className={`w-[145px] pr-4 text-xs whitespace-nowrap ${STATE_COLOR[state]}`}>{reason ? t("run.failedIn", { reason }) : t(`run.state.${state}`)}</td>
      <td className="w-[145px] pr-4 font-mono text-[11px] whitespace-nowrap text-fg-secondary" title={utcTitle(when)}>{what}</td>
      <td className="pr-4 text-right font-mono text-xs whitespace-nowrap text-fg-secondary">{duration}</td>
      <td className="pr-4 text-right font-mono text-xs whitespace-nowrap text-fg-secondary">{r.cost_usd != null ? `${formatCost(r.cost_usd)} USD` : "–"}</td>
      <td className="w-10 rounded-r-control pr-5"><ChevronRight className="size-4 text-fg-secondary" aria-hidden /></td>
    </tr>
  );
}
