// Step panel in the run viewer (§2.5): tabs depend on the step type.
import { ExternalLink, FileText } from "lucide-react";
import { useState, type ReactNode } from "react";
import { enc, getText, useApi } from "../api";
import { formatCost, formatDuration } from "../format";
import { locale, t } from "../i18n";
import { setQuery } from "../router";
import type { RunEvent, RunStep, RunStepDetail, StepType } from "../types";
import { PanelShell } from "./StepPanel";
import { FileViewer, runFilePath } from "./RunFiles";
import { CodeBlock, ErrorText, Loading, StatusChip, type Status } from "./ui";

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

const Empty = () => <p className="text-sm text-fg-muted">{t("rpanel.empty")}</p>;

/** Model response: the message text, otherwise the whole JSON body. */
function ResponseView({ path, name }: { path: string; name: string }) {
  const res = useApi<string>(path, undefined, getText);
  if (res.error) return <ErrorText error={res.error} />;
  if (res.data === undefined) return <Loading rows={3} />;
  let shown = res.data;
  try {
    const body = JSON.parse(res.data);
    const msg = body?.choices?.[0]?.message;
    shown = typeof msg?.content === "string" && msg.content ? msg.content : JSON.stringify(msg ?? body, null, 2);
  } catch { /* not JSON — show the text */ }
  return <CodeBlock title={name} text={shown} />;
}

/** Jev answers: probabilities as a bar (0–1), other values as text. */
function JevAnswers({ answers = {} }: { answers?: Record<string, unknown> }) {
  if (!Object.keys(answers).length) return <Empty />;
  return (
    <dl className="space-y-2">
      {Object.entries(answers).map(([k, v]) => (
        <div key={k} className="grid grid-cols-[8rem_4rem_1fr] items-center gap-3 text-sm">
          <dt className="truncate font-mono">{k}</dt>
          <dd className="font-mono tabular-nums">{typeof v === "number" ? v.toLocaleString(locale, { maximumFractionDigits: 3 }) : String(v)}</dd>
          <dd aria-hidden>
            {typeof v === "number" && v >= 0 && v <= 1 && (
              <span className="block h-1.5 overflow-hidden rounded-full bg-nested"><span className="block h-full bg-accent" style={{ width: `${v * 100}%` }} /></span>
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
        <li key={i} className="rounded-control bg-nested px-3 py-2">
          {e.type === "error" ? (
            <p className="text-error"><span className="font-mono">{String(e.class)}</span>: {String(e.message)}{e.will_retry ? " ↻" : ""}</p>
          ) : (
            <>
              <p className="font-mono">
                {t("rpanel.attempt", { n: String(e.attempt ?? 1) })}{e.turn != null && ` · ${t("rpanel.turn", { n: String(e.turn) })}`}
                {" · "}{e.alias ? `${e.alias} → ` : ""}{String(e.response_model ?? e.model)}
              </p>
              <p className="text-fg-muted">
                {[e.provider, e.finish_reason && `finish_reason ${e.finish_reason}${e.native_finish_reason ? ` (${e.native_finish_reason})` : ""}`,
                  e.structured_output, e.http_status && `HTTP ${e.http_status}`].filter(Boolean).join(" · ")}
              </p>
              <p className="text-fg-muted">{formatDuration(e.duration_s as number)} · {usage(e)}</p>
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
          <li key={i} className={`rounded-control px-3 py-2 ${flag ? "bg-error/10" : "bg-nested"}`}>
            <p className="font-mono">{t("rpanel.turn", { n: String(e.turn) })} · {String(e.server)}.{String(e.tool)}</p>
            <p className="text-fg-muted">
              {flag && <span className="text-error">{flag} · </span>}
              {formatDuration(e.duration_s as number)}
              {typeof e.call_file === "string" && (
                <> · <button type="button" className="underline" onClick={() => setQuery({ tab: "files", file: e.call_file as string })}>{e.call_file}</button></>
              )}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export function RunStepPanel({ project, runId, path, kind, rs, onClose }: {
  project: string; runId: string; path: string; kind: StepType | null; rs?: RunStep; onClose: () => void;
}) {
  const [tab, setTab] = useState<PanelTab>();
  // Events, output and files of one step; a running step is re-read (the panel is keyed by the step status).
  const detail = useApi<RunStepDetail>(rs ? `/projects/${enc(project)}/runs/${enc(runId)}/steps/${path.split("/").map(enc).join("/")}` : null,
    (d) => (d.status === "running" ? 2000 : null));
  const d = detail.data;
  const own = d?.events ?? [];
  const files = d?.files ?? [];
  const dir = rs?.dir ? `${rs.dir}/` : "";
  const tabs = kind ? TABS[kind] : ["files" as PanelTab];
  const active = tab && tabs.includes(tab) ? tab : tabs[0];
  const responses = files.filter((f) => /calls\/\d+\.response\.json$/.test(f)).sort();
  const status: Status = rs ? (rs.continued ? "warning" : rs.status) : "none";

  let body: ReactNode = <Empty />;
  if (active === "prompt" && files.includes(dir + "prompt.md")) body = <FileViewer project={project} runId={runId} path={dir + "prompt.md"} name="prompt.md" />;
  if (active === "output" && d?.output != null)
    body = <CodeBlock title="output.json" text={JSON.stringify(d.output, null, 2)} foot={`JSON · ${t("code.readOnly")}`} />;
  if (active === "response")
    body = kind === "jev" ? <JevAnswers answers={rs?.answers} />
      : responses.length ? <ResponseView path={runFilePath(project, runId, responses.at(-1)!)} name={responses.at(-1)!.slice(dir.length)} /> : <Empty />;
  if (active === "calls") body = <Calls events={own} />;
  if (active === "tools") body = <Tools events={own} />;
  if (active === "image") {
    const imgs = files.filter((f) => /\.(png|jpe?g|webp)$/i.test(f));
    body = imgs.length ? <div className="space-y-3">{imgs.map((f) => <FileViewer key={f} project={project} runId={runId} path={f} />)}</div> : <Empty />;
  }
  if (active === "files")
    body = files.length ? (
      <ul className="space-y-2">
        {files.map((f) => (
          <li key={f}>
            <button type="button" className="flex h-[52px] w-full items-center gap-3 rounded-control bg-nested p-3 text-left hover:bg-surface-hover" onClick={() => setQuery({ tab: "files", file: f })}>
              <FileText className="size-4 shrink-0 text-fg-secondary" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-fg-secondary">{f.slice(dir.length)}</span>
              <ExternalLink className="size-4 shrink-0 text-fg-secondary" aria-hidden />
            </button>
          </li>
        ))}
      </ul>
    ) : <Empty />;

  return (
    <PanelShell id="run-step-title" eyebrow={`${rs?.nn ? t("panel.step", { n: rs.nn }) : ""} · ${kind ?? "?"}`.replace(/^ · /, "")}
      title={path} onClose={onClose}>
      <div className="space-y-5">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-fg-secondary">
          <StatusChip status={status}>{rs ? t(`rstatus.${rs.status}`) : t("run.notReached")}</StatusChip>
          {(rs?.duration_s != null || rs?.cost_usd != null) && (
            <span className="tabular-nums">{[rs.duration_s != null && formatDuration(rs.duration_s), rs.cost_usd != null && `${formatCost(rs.cost_usd)} USD`].filter(Boolean).join(" · ")}</span>
          )}
          {rs?.turns != null && <span>{t("rpanel.turns", { turns: rs.turns, tools: rs.tool_calls ?? 0 })}</span>}
        </p>
        {rs?.status === "skipped" && (
          <p className="text-sm text-fg-secondary">
            {t("run.skipped", { reason: rs.reason ?? rs.reason_code ?? "" })}
            {rs.default_used && ` · ${t("run.defaultUsed")}`}
          </p>
        )}
        {status === "warning" && <p className="text-sm text-warning">{t("run.warning")}{rs?.default_used && ` · ${t("run.defaultUsed")}`}</p>}
        {rs?.error && <ErrorText error={{ message: `${rs.error.class}: ${rs.error.message}` }} />}
        {detail.error && <ErrorText error={detail.error} />}
        {rs && (
          <>
            <div role="tablist" aria-label={t("rpanel.tabs")} className="flex flex-wrap gap-x-6 border-b border-line">
                {tabs.map((k) => (
                  <button key={k} type="button" role="tab" aria-selected={k === active} onClick={() => setTab(k)}
                    className={`-mb-px h-11 border-b-2 text-[13px] ${k === active ? "border-accent text-fg" : "border-transparent text-fg-muted hover:text-fg"}`}>
                    {t(TAB_KEY[k])}{k === "calls" ? ` (${rs.calls?.length ?? 0})` : ""}
                  </button>
                ))}
            </div>
            <div role="tabpanel">{d ? body : <Loading rows={3} />}</div>
          </>
        )}
      </div>
    </PanelShell>
  );
}
