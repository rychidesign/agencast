// §2.5 Run detail (fidelity §8: mono title 32 + ↗, run_id below it, INPUTS as a card): cards with status, time and cost; tabs Steps · Summary · Report · Files; live run (§4.8).
import { ArrowUpRight, Clock, ExternalLink, FileText } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { enc, getText, useApi } from "../api";
import { Markdown } from "../components/Markdown";
import { RUN_STATUS } from "../components/RunBadge";
import { FilesTab, ReportTab } from "../components/RunFiles";
import { RunStepPanel } from "../components/RunStepPanel";
import { onColumnKey, StepList, type ListCtx } from "../components/StepCards";
import { PageHeader } from "../components/PageHeader";
import { btn, EmptyState, ErrorText, Loading, StatusChip, TabLinks } from "../components/ui";
import { failReason, formatCost, formatDuration, isLive, runScenario } from "../format";
import { t } from "../i18n";
import { href, setQuery, useLocation } from "../router";
import type { RunCtx } from "../run";
import { flatten } from "../steps";
import type { Run, Step } from "../types";
import { closeOnEsc, errorsByStep, PanelSlot, useScrollToCard } from "./Scenario";

/** §4.8: while the run is queued or running, every 2 s, after 2 min every 5 s. */
export const pollDelay = (elapsedMs: number) => (elapsedMs > 120_000 ? 5000 : 2000);

const RUN_TABS = ["steps", "summary", "report", "files"] as const;

const show = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

export function RunPage({ project, runId }: { project: string; runId: string }) {
  const { query } = useLocation();
  const base = `/projects/${enc(project)}`;
  const runPath = `${base}/runs/${enc(runId)}`;
  const opened = useRef(Date.now());
  // A fresh run has been `queued` → `running` right away since 0.8.0 (api-findings.md item 15); an interrupted one is not polled.
  const loaded = useApi<Run>(runPath, (d) => (isLive(d.state) ? pollDelay(Date.now() - opened.current) : null));
  const run = loaded.data;
  const inputs = useApi<string>(run?.files?.includes("inputs.json") ? `${runPath}/files/inputs.json` : null, undefined, getText);

  const state = run?.state;
  const live = !!state && isLive(state);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [live]);
  const wasLive = useRef(false);
  if (live) wasLive.current = true;

  const selected = query.get("step") ?? undefined;
  const tab = (RUN_TABS as readonly string[]).includes(query.get("tab") ?? "") ? query.get("tab")! : "steps";
  const [follow, setFollow] = useState(false);

  // Steps: tree from the scenario snapshot (`tree`); without a scenario file a flat list from the run record.
  const steps: Step[] = useMemo(() => {
    if (run?.tree?.length) return run.tree;
    return (run?.steps ?? []).filter((s) => !s.step.includes("/")).map((s, i) => ({
      nn: s.nn ?? i + 1, address: [], id: s.step, type: s.kind, when: null, fields: {}, refs: [],
    }));
  }, [run?.tree, run?.steps]);
  const all = useMemo(() => flatten(steps), [steps]);
  // A step without an end in a run that is no longer running (crash, `serve` restart) is shown as interrupted, not "running" (api-findings.md item 22).
  const runSteps = useMemo(() => new Map((run?.steps ?? []).map((s) =>
    [s.step, !live && s.status === "running" ? { ...s, status: "interrupted" as const } : s])), [run?.steps, live]);
  const running = [...runSteps.values()].filter((s) => s.status === "running").pop()?.step;
  const ctxRun: RunCtx = { steps: runSteps, prefix: "", now, callees: run?.callees ?? {} };
  const ctx: ListCtx = {
    project, selected, errors: errorsByStep([]), run: ctxRun,
    onSelect: (key) => setQuery({ step: key === selected ? undefined : key }),
  };
  useScrollToCard(follow && live ? running : selected);

  const parsedInputs = useMemo(() => {
    try {
      return inputs.data ? (JSON.parse(inputs.data) as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }, [inputs.data]);
  const sel = selected ? { rs: runSteps.get(selected), step: selected.includes("/") ? undefined : all.find((s) => s.id === selected) } : undefined;

  const inputEntries = Object.entries(parsedInputs);
  return (
    <div onKeyDown={closeOnEsc(selected)}>
      <PageHeader sticky
        back={{ href: href(project, "runs"), label: t("project.tab.runs") }}
        title={run && (
          <a href={href(project, "scenarios", runScenario(run))} className="font-mono hover:underline md:text-[26px] md:leading-[39px]">
            {runScenario(run)}<ArrowUpRight className="ml-3 inline size-5 shrink-0 align-[-2px]" aria-hidden />
          </a>
        )}
        detail={runId}
        actions={run && <>
          {state && (
            <span data-testid="run-state">
              <StatusChip status={RUN_STATUS[state]}>
                {state === "failed" ? t("run.failedIn", { reason: failReason(run.status) }) : t(`run.state.${state}`)}
              </StatusChip>
            </span>
          )}
          {run.fake && <span className="rounded-full bg-nested px-3 py-1.5 font-mono text-xs text-fg-secondary">{t("run.fake")}</span>}
          {(run.duration_s != null || run.cost_usd != null) && (
            <span className="font-mono text-[13px] whitespace-nowrap text-fg-secondary">
              {run.duration_s != null && <span data-testid="run-duration">{formatDuration(run.duration_s)}</span>}
              {run.duration_s != null && run.cost_usd != null && " · "}
              {run.cost_usd != null && <span data-testid="run-cost">{formatCost(run.cost_usd)} USD</span>}
            </span>
          )}
          <a className={`${btn.secondary} max-md:hidden`} href={href(project, "scenarios", runScenario(run))}>
            <ExternalLink className="size-4" aria-hidden />{t("run.openScenario")}
          </a>
        </>}>
        {inputEntries.length > 0 && (
          // design 12 (measured from .pen): `nested` r8 p14 gap 12, label 10 uppercase, values mono 12
          <p className="flex w-full items-center gap-3 truncate rounded-control bg-nested p-3.5 font-mono text-xs leading-[18px] text-fg-secondary"
            title={inputEntries.map(([k, v]) => `${k} = ${show(v)}`).join("\n")}>
            <span className="font-sans text-[10px] leading-[15px] tracking-[0.08em] text-fg-muted uppercase">{t("run.inputs")}</span>
            <span className="truncate">{inputEntries.map(([k, v]) => `${k} = ${t("common.quoted", { text: show(v) })}`).join(" · ")}</span>
          </p>
        )}
        {!loaded.error && (
          // tabs underlined across the full width, "follow run" on the right on the same line (design V3 / RunTabs)
          <div className="flex w-full flex-wrap items-center gap-x-4 border-b border-line [&>nav]:border-b-0">
            <TabLinks label={t("run.tabs")} active={tab}
              tabs={RUN_TABS.map((k) => ({ key: k, label: t(`run.tab.${k}`), href: href(project, "runs", runId, { tab: k === "steps" ? undefined : k }) }))} />
            {live && (
              <label className="ml-auto inline-flex min-h-11 items-center gap-2.5 text-[13px] text-fg-secondary">
                <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> {t("run.follow")}
              </label>
            )}
          </div>
        )}
        {state === "interrupted" && <p className="w-full text-sm text-warning">{t("run.interruptedHint")}</p>}
        <p className="sr-only" aria-live="polite">{running ? t("run.stepRunning", { step: running }) : ""}</p>
        <p role="status" className="sr-only">
          {wasLive.current && !live && state ? t("run.finished", { state: t(`run.state.${state}`) }) : ""}
        </p>
      </PageHeader>

      <div>
        {loaded.error && loaded.error.status !== 0 && <ErrorText error={loaded.error} />}
        {!run && !loaded.error && <div className="mx-auto max-w-[676px]"><Loading rows={4} pill /></div>}
        {run && tab === "steps" && (
          state === "queued" ? (
            <div className="space-y-6">
              {run.queue_position != null && <p className="flex items-center gap-3 font-mono text-xs text-neutral"><Clock className="size-4" aria-hidden />{t("runs.queued", { n: run.queue_position })}</p>}
              <EmptyState tall icon={Clock} text={t("run.queuedHint")} hint={t("run.queuedWhen")} />
            </div>
          ) : state === "dry_run" ? (
            // design 16: status row 12 `neutral`, plan in a `surface` card r12 p24 with eyebrow
            <div className="space-y-6">
              <p className="flex items-center gap-3 text-xs text-neutral"><FileText className="size-4" aria-hidden />{t("run.dryRun")}</p>
              <section className="space-y-5 rounded-card bg-surface p-6" aria-labelledby="plan-title">
                <p id="plan-title" className="text-[11px] tracking-[0.08em] text-fg-muted uppercase">{t("run.planTitle")}</p>
                <Summary path={`${runPath}/files/plan.md`} has={!!run.files?.includes("plan.md")} />
              </section>
            </div>
          ) : (
            // design 12 (measured from .pen): column up to 676, gap 28, step panel 520
            <div className="flex justify-center gap-7">
              <section className="w-full max-w-[676px] min-w-0" aria-label={t("step.list")} onKeyDown={onColumnKey}>
                {!run.tree?.length ? <p className="mb-4 text-sm text-fg-muted">{t("run.scenarioMissing", { name: runScenario(run) })}</p>
                  : run.tree_source === "current" && <p className="mb-4 text-[13px] text-fg-muted">{t("run.treeCurrent")}</p>}
                <StepList steps={steps} ctx={ctx} />
              </section>
              {selected && sel && (
                <PanelSlot wide>
                  <RunStepPanel key={`${selected}:${sel.rs?.status}`} project={project} runId={runId} path={selected} rs={sel.rs} runFiles={run.files} live={live}
                    kind={sel.step?.type ?? sel.rs?.kind ?? null} onClose={() => setQuery({ step: undefined })} />
                </PanelSlot>
              )}
            </div>
          )
        )}
        {run && tab === "summary" && <div className="mx-auto max-w-4xl"><Summary key={run.status} path={`${runPath}/files/summary.md`} has={!!run.files?.includes("summary.md")} /></div>}
        {run && tab === "report" && (run.files?.includes("report.html") ? <div><ReportTab key={run.status} project={project} runId={runId} /></div> : <EmptyState text={t("run.noFile")} />)}
        {run && tab === "files" && <div><FilesTab project={project} runId={runId} files={run.files ?? []} current={query.get("file") ?? undefined} /></div>}
      </div>
    </div>
  );
}

function Summary({ path, has }: { path: string; has: boolean }) {
  const md = useApi<string>(has ? path : null, undefined, getText);
  if (!has) return <EmptyState text={t("run.noFile")} />;
  if (md.error) return <ErrorText error={md.error} />;
  return md.data === undefined ? <Loading rows={6} /> : <Markdown text={md.data} />;
}
