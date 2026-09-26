// Panel kroku v prohlížeči běhu (§2.5): záložky podle typu kroku.
import { useState, type ReactNode } from "react";
import { getText, useApi } from "../api";
import { formatCost, formatDuration } from "../format";
import { t } from "../i18n";
import { setQuery } from "../router";
import { continued, eventsOf, stepDir, stepFiles } from "../run";
import type { RunEvent, RunStep, StepType } from "../types";
import { PanelShell } from "./StepPanel";
import { FileViewer, runFilePath } from "./RunFiles";
import { ErrorText, Loading, StatusBadge, type Status } from "./ui";

type PanelTab = "prompt" | "response" | "output" | "calls" | "tools" | "image" | "files";

const TABS: Record<StepType, PanelTab[]> = {
  ask: ["prompt", "response", "output", "calls", "files"],
  task: ["prompt", "response", "output", "calls", "tools", "files"],
  jev: ["response", "output", "calls", "files"],
  image: ["image", "prompt", "calls", "files"],
  call: ["output", "files"], set: ["output", "files"], output: ["output", "files"],
  fail: ["files"], parallel: ["files"], switch: ["output", "files"],
};

const TAB_KEY: Record<PanelTab, string> = {
  prompt: "rpanel.prompt", response: "rpanel.response", output: "rpanel.output", calls: "rpanel.calls",
  tools: "rpanel.tools", image: "rpanel.image", files: "rpanel.files",
};

const Empty = () => <p className="text-sm text-zinc-400">{t("rpanel.empty")}</p>;

/** Odpověď modelu: text zprávy, jinak celé JSON tělo. */
function ResponseView({ path }: { path: string }) {
  const res = useApi<string>(path, undefined, getText);
  if (res.error) return <ErrorText error={res.error} />;
  if (res.data === undefined) return <Loading rows={3} />;
  let shown = res.data;
  try {
    const body = JSON.parse(res.data);
    const msg = body?.choices?.[0]?.message;
    shown = typeof msg?.content === "string" && msg.content ? msg.content : JSON.stringify(msg ?? body, null, 2);
  } catch { /* není JSON — ukážeme text */ }
  return <pre className="font-mono text-[13px] whitespace-pre-wrap break-words">{shown}</pre>;
}

/** Odpovědi Jev s pravděpodobností jako pruh (0–1), jiné hodnoty textem. */
function JevAnswers({ call }: { call: RunEvent | undefined }) {
  const answers = (call?.answers ?? {}) as Record<string, unknown>;
  if (!Object.keys(answers).length) return <Empty />;
  return (
    <dl className="space-y-2">
      {Object.entries(answers).map(([k, v]) => (
        <div key={k} className="grid grid-cols-[8rem_4rem_1fr] items-center gap-3 text-sm">
          <dt className="truncate font-mono">{k}</dt>
          <dd className="font-mono tabular-nums">{typeof v === "number" ? v.toLocaleString("cs", { maximumFractionDigits: 3 }) : String(v)}</dd>
          <dd aria-hidden>
            {typeof v === "number" && v >= 0 && v <= 1 && (
              <span className="block h-1.5 overflow-hidden rounded-full bg-zinc-900"><span className="block h-full bg-zinc-300" style={{ width: `${v * 100}%` }} /></span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const usage = (e: RunEvent) => {
  const u = (e.usage ?? {}) as { input_tokens?: number; output_tokens?: number; cost_usd?: number | null };
  return `${t("rpanel.tokens", { input: u.input_tokens ?? "–", output: u.output_tokens ?? "–" })} · ${formatCost(u.cost_usd)} USD`;
};

function Calls({ events }: { events: RunEvent[] }) {
  const calls = events.filter((e) => e.type === "model_call" || e.type === "jev_call" || e.type === "error");
  if (!calls.length) return <Empty />;
  return (
    <ol className="space-y-3 text-[13px]">
      {calls.map((e, i) => (
        <li key={i} className="rounded-lg bg-zinc-900 p-3">
          {e.type === "error" ? (
            <p className="text-rose-400"><span className="font-mono">{String(e.class)}</span>: {String(e.message)}{e.will_retry ? " ↻" : ""}</p>
          ) : (
            <>
              <p className="font-mono">
                {t("rpanel.attempt", { n: String(e.attempt ?? 1) })}{e.turn != null && ` · ${t("rpanel.turn", { n: String(e.turn) })}`}
                {" · "}{e.alias ? `${e.alias} → ` : ""}{String(e.response_model ?? e.model)}
              </p>
              <p className="text-zinc-400">
                {[e.provider, e.finish_reason && `finish_reason ${e.finish_reason}${e.native_finish_reason ? ` (${e.native_finish_reason})` : ""}`,
                  e.structured_output, e.http_status && `HTTP ${e.http_status}`].filter(Boolean).join(" · ")}
              </p>
              <p className="text-zinc-400">{formatDuration(e.duration_s as number)} · {usage(e)}</p>
            </>
          )}
        </li>
      ))}
    </ol>
  );
}

function Tools({ events }: { events: RunEvent[] }) {
  const calls = events.filter((e) => e.type === "tool_call");
  if (!calls.length) return <Empty />;
  return (
    <ol className="space-y-2 text-[13px]">
      {calls.map((e, i) => {
        const flag = e.allowed === false ? t("rpanel.toolDenied") : e.invalid_args ? t("rpanel.toolInvalid") : e.is_error ? t("rpanel.toolError") : "";
        return (
          <li key={i} className={`rounded-lg p-3 ${flag ? "bg-rose-500/10" : "bg-zinc-900"}`}>
            <p className="font-mono">{t("rpanel.turn", { n: String(e.turn) })} · {String(e.server)}.{String(e.tool)}</p>
            <p className="text-zinc-400">
              {flag && <span className="text-rose-400">{flag} · </span>}
              {formatDuration(e.duration_s as number)}
              {typeof e.call_file === "string" && (
                <> · <button type="button" className="underline" onClick={() => setQuery({ zalozka: "soubory", soubor: e.call_file as string })}>{e.call_file}</button></>
              )}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export function RunStepPanel({ project, runId, path, kind, nn, rs, events, files, onClose }: {
  project: string; runId: string; path: string; kind: StepType | null; nn?: number; rs?: RunStep;
  events: RunEvent[]; files: string[]; onClose: () => void;
}) {
  const [tab, setTab] = useState<PanelTab>();
  const own = events.filter((e) => e.step === path);
  const dir = stepDir(files, path);
  const mine = dir ? stepFiles(files, dir) : [];
  const tabs = kind ? TABS[kind] : ["files" as PanelTab];
  const active = tab && tabs.includes(tab) ? tab : tabs[0];
  const file = (name: string) => (dir && files.includes(dir + name) ? runFilePath(project, runId, dir + name) : undefined);
  const responses = mine.filter((f) => /calls\/\d+\.response\.json$/.test(f)).sort();
  const skipped = eventsOf(events, path, "step_skipped")[0];
  const errors = eventsOf(events, path, "error").filter((e) => !e.will_retry);
  const status: Status = rs ? (continued(events, path) ? "warning" : rs.status) : "none";

  let body: ReactNode = <Empty />;
  if (active === "prompt" && file("prompt.md")) body = <FileViewer project={project} runId={runId} path={dir + "prompt.md"} />;
  if (active === "output" && file("output.json")) body = <FileViewer project={project} runId={runId} path={dir + "output.json"} />;
  if (active === "response")
    body = kind === "jev" ? <JevAnswers call={eventsOf(events, path, "jev_call").pop()} />
      : responses.length ? <ResponseView path={runFilePath(project, runId, responses[responses.length - 1])} /> : <Empty />;
  if (active === "calls") body = <Calls events={own} />;
  if (active === "tools") body = <Tools events={own} />;
  if (active === "image") {
    const imgs = mine.filter((f) => /\.(png|jpe?g|webp)$/i.test(f));
    body = imgs.length ? <div className="space-y-3">{imgs.map((f) => <FileViewer key={f} project={project} runId={runId} path={f} />)}</div> : <Empty />;
  }
  if (active === "files")
    body = mine.length ? (
      <ul className="space-y-1">
        {mine.map((f) => (
          <li key={f}>
            <button type="button" className="font-mono text-[13px] underline" onClick={() => setQuery({ zalozka: "soubory", soubor: f })}>{f.slice(dir!.length)}</button>
          </li>
        ))}
      </ul>
    ) : <Empty />;

  // Číslo kroku ve volaném scénáři známe jen ze složky záznamu (`steps/02-ton/steps/01-kontrola/`).
  const number = nn ?? (dir ? Number(/(\d+)-[^/]+\/$/.exec(dir)?.[1]) : undefined);

  return (
    <PanelShell id="run-step-title" eyebrow={`${number ? t("panel.step", { n: number }) : ""} · ${kind ?? "?"}`.replace(/^ · /, "")}
      title={<span className="font-mono">{path}</span>} onClose={onClose}>
      <div className="space-y-4">
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <StatusBadge status={status}>{rs ? t(`rstatus.${rs.status}`) : t("run.notReached")}</StatusBadge>
          {rs?.duration_s != null && <span className="font-mono">{formatDuration(rs.duration_s)}</span>}
          {rs?.cost_usd != null && <span className="font-mono">{formatCost(rs.cost_usd)} USD</span>}
        </p>
        {skipped && (
          <p className="text-sm text-zinc-300">
            {t("run.skipped", { reason: String(skipped.reason ?? skipped.reason_code ?? "") })}
            {skipped.default_used === true && ` · ${t("run.defaultUsed")}`}
          </p>
        )}
        {status === "warning" && <p className="text-sm text-amber-400">{t("run.warning")}</p>}
        {errors.map((e, i) => <ErrorText key={i} error={{ message: `${e.class}: ${e.message}` }} />)}
        {rs && (
          <>
            <div role="tablist" aria-label={t("run.tabs")} className="flex flex-wrap gap-1">
                {tabs.map((k) => (
                  <button key={k} type="button" role="tab" aria-selected={k === active} onClick={() => setTab(k)}
                    className={`rounded-full px-3 py-1 text-sm ${k === active ? "bg-zinc-700 text-zinc-100" : "text-zinc-400 hover:text-zinc-100"}`}>
                    {t(TAB_KEY[k])}{k === "calls" ? ` (${own.filter((e) => e.type.endsWith("_call") && e.type !== "tool_call").length})` : ""}
                  </button>
                ))}
            </div>
            <div role="tabpanel">{body}</div>
          </>
        )}
      </div>
    </PanelShell>
  );
}
