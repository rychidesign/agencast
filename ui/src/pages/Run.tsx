// §2.5 Detail běhu: karty se stavem, časem a cenou; záložky Kroky · Souhrn · Report · Soubory; živý běh (§4.8).
import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { enc, getText, useApi } from "../api";
import { Markdown } from "../components/Markdown";
import { RUN_STATUS } from "../components/RunBadge";
import { FilesTab, ReportTab } from "../components/RunFiles";
import { RunStepPanel } from "../components/RunStepPanel";
import { onColumnKey, StepList, type ListCtx } from "../components/StepCards";
import { EmptyState, ErrorText, Loading, StatusBadge, TabLinks } from "../components/ui";
import { failReason, formatCost, formatDuration, isLive, runScenario } from "../format";
import { t } from "../i18n";
import { href, setQuery, useLocation } from "../router";
import type { RunCtx } from "../run";
import { flatten } from "../steps";
import type { Run, Step } from "../types";
import { closeOnEsc, errorsByStep, PanelSlot, useScrollToCard } from "./Scenario";

/** §4.8: dokud běh čeká nebo běží, každé 2 s, po 2 min každých 5 s. */
export const pollDelay = (elapsedMs: number) => (elapsedMs > 120_000 ? 5000 : 2000);

const RUN_TABS = ["kroky", "souhrn", "report", "soubory"] as const;

export function RunPage({ project, runId }: { project: string; runId: string }) {
  const { query } = useLocation();
  const base = `/projects/${enc(project)}`;
  const runPath = `${base}/runs/${enc(runId)}`;
  const opened = useRef(Date.now());
  const fresh = query.get("spusteno") === "1";
  const loaded = useApi<Run>(
    runPath,
    // Ostrý běh spuštěný z GUI (`?spusteno=1`): než vznikne events.jsonl, API ho krátce hlásí jako
    // `dry_run` (nalezy-api.md, bod 15) — prvních 15 s se proto čte dál. Přerušený běh se nečte.
    (d) => (isLive(d.state) || (fresh && d.state === "dry_run" && Date.now() - opened.current < 15_000)
      ? pollDelay(Date.now() - opened.current) : null),
  );
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

  const selected = query.get("krok") ?? undefined;
  const tab = (RUN_TABS as readonly string[]).includes(query.get("zalozka") ?? "") ? query.get("zalozka")! : "kroky";
  const [follow, setFollow] = useState(false);

  // Kroky: strom ze snímku scénáře (`tree`); bez souboru scénáře rovný seznam ze záznamu běhu.
  const steps: Step[] = useMemo(() => {
    if (run?.tree?.length) return run.tree;
    return (run?.steps ?? []).filter((s) => !s.step.includes("/")).map((s, i) => ({
      nn: s.nn ?? i + 1, address: [], id: s.step, type: s.kind, when: null, fields: {}, refs: [],
    }));
  }, [run?.tree, run?.steps]);
  const all = useMemo(() => flatten(steps), [steps]);
  // Krok bez konce v běhu, který už neběží (pád, restart `serve`), ukážeme jako přerušený, ne „běží“ (nalezy-api.md bod 22).
  const runSteps = useMemo(() => new Map((run?.steps ?? []).map((s) =>
    [s.step, !live && s.status === "running" ? { ...s, status: "interrupted" as const } : s])), [run?.steps, live]);
  const running = [...runSteps.values()].filter((s) => s.status === "running").pop()?.step;
  const ctxRun: RunCtx = { steps: runSteps, prefix: "", now, callees: run?.callees ?? {} };
  const ctx: ListCtx = {
    project, selected, errors: errorsByStep([]), run: ctxRun,
    onSelect: (key) => setQuery({ krok: key === selected ? undefined : key }),
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

  return (
    <main className="min-h-screen" onKeyDown={closeOnEsc(selected)}>
      <header className="sticky top-0 z-10 space-y-2 bg-zinc-900/95 px-8 py-4">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <a href={href(project, "behy")} className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100">
            <ArrowLeft className="size-4" aria-hidden /> {t("run.back", { project })}
          </a>
          <h1 className="text-lg font-semibold">
            {run && <a href={href(project, "scenare", runScenario(run))} className="font-mono hover:underline">{runScenario(run)}</a>}
            <span className="ml-2 font-mono text-sm font-normal text-zinc-400">{runId}</span>
          </h1>
          {run && state && (
            <StatusBadge status={RUN_STATUS[state]}>
              {state === "failed" ? t("run.failedIn", { reason: failReason(run.status) }) : t(`run.state.${state}`)}
            </StatusBadge>
          )}
          {run?.fake && <span className="rounded-full bg-zinc-800 px-2 text-xs text-zinc-300">{t("run.fake")}</span>}
          {run && (
            <span className="ml-auto font-mono text-sm">
              {run.duration_s != null && formatDuration(run.duration_s)}
              {run.cost_usd != null && ` · ${formatCost(run.cost_usd)} USD`}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          {Object.keys(parsedInputs).length > 0 && (
            <p className="min-w-0 truncate text-sm text-zinc-400">
              {t("run.inputs")}{" "}
              {Object.entries(parsedInputs).map(([k, v]) => (
                <span key={k} className="mr-3 text-zinc-200"><span className="font-mono">{k}</span> = „{typeof v === "string" ? v : JSON.stringify(v)}“</span>
              ))}
            </p>
          )}
          <TabLinks label={t("run.tabs")} active={tab}
            tabs={RUN_TABS.map((k) => ({ key: k, label: t(`run.tab.${k}`), href: href(project, "behy", runId, { zalozka: k === "kroky" ? undefined : k }) }))} />
          {live && (
            <label className="ml-auto inline-flex items-center gap-2 text-sm">
              <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> {t("run.follow")}
            </label>
          )}
        </div>
        <p className="sr-only" aria-live="polite">{running ? t("run.stepRunning", { step: running }) : ""}</p>
        {state === "interrupted" && <p className="text-sm text-amber-400">{t("run.interruptedHint")}</p>}
        {wasLive.current && !live && state && (
          <p role="status" className="rounded-lg bg-zinc-800 px-3 py-2 text-sm">
            <StatusBadge status={RUN_STATUS[state]}>{t("run.finished", { state: t(`run.state.${state}`) })}</StatusBadge>
          </p>
        )}
      </header>

      <div className="px-8 pb-16">
        {loaded.error && loaded.error.status !== 0 && <ErrorText error={loaded.error} />}
        {!run && !loaded.error && <div className="mx-auto max-w-[640px] pt-6"><Loading rows={4} pill /></div>}
        {run && tab === "kroky" && (
          state === "queued" ? <EmptyState text={t("run.queuedHint")} />
          : state === "dry_run" ? (
            <div className="space-y-3 pt-4">
              <p className="text-sm text-zinc-300">{t("run.dryRun")}</p>
              <Summary path={`${runPath}/files/plan.md`} has={!!run.files?.includes("plan.md")} />
            </div>
          ) : (
            <div className="flex justify-center gap-6 pt-6">
              <section className="w-full max-w-[640px]" aria-label={t("step.list")} onKeyDown={onColumnKey}>
                {!run.tree?.length ? <p className="mb-4 text-sm text-zinc-400">{t("run.scenarioMissing", { name: runScenario(run) })}</p>
                  : run.tree_source === "current" && <p className="mb-4 text-[13px] text-zinc-400">{t("run.treeCurrent")}</p>}
                <StepList steps={steps} ctx={ctx} />
              </section>
              {selected && sel && (
                <PanelSlot>
                  <RunStepPanel key={`${selected}:${sel.rs?.status}`} project={project} runId={runId} path={selected} rs={sel.rs}
                    kind={sel.step?.type ?? sel.rs?.kind ?? null} onClose={() => setQuery({ krok: undefined })} />
                </PanelSlot>
              )}
            </div>
          )
        )}
        {run && tab === "souhrn" && <div className="mx-auto max-w-4xl pt-4"><Summary key={run.status} path={`${runPath}/files/summary.md`} has={!!run.files?.includes("summary.md")} /></div>}
        {run && tab === "report" && (run.files?.includes("report.html") ? <div className="pt-4"><ReportTab key={run.status} project={project} runId={runId} /></div> : <EmptyState text={t("run.noFile")} />)}
        {run && tab === "soubory" && <div className="pt-4"><FilesTab project={project} runId={runId} files={run.files ?? []} current={query.get("soubor") ?? undefined} /></div>}
      </div>
    </main>
  );
}

function Summary({ path, has }: { path: string; has: boolean }) {
  const md = useApi<string>(has ? path : null, undefined, getText);
  if (!has) return <EmptyState text={t("run.noFile")} />;
  if (md.error) return <ErrorText error={md.error} />;
  return md.data === undefined ? <Loading rows={6} /> : <Markdown text={md.data} />;
}
