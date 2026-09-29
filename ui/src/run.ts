// Per-step run data from `GET …/runs/<id>` (`steps`: status, time, cost, error, calls, Jev answers).
import { locale, t } from "./i18n";
import type { RunStep, Step, StepType } from "./types";

export interface RunCtx {
  steps: Map<string, RunStep>;
  /** Steps of a called scenario have the path `propose/copy`; this is the `propose/` prefix. */
  prefix: string;
  /** Now (ms), for the ticking time of a running step. */
  now: number;
  /** Trees of called scenarios from the run snapshot (`callees`). */
  callees: Record<string, Step[]>;
}

const num = (v: unknown) => (typeof v === "number" ? v.toLocaleString(locale, { maximumFractionDigits: 2 }) : String(v));

/** Second line of a card in the run viewer; empty = show the value from the editor. */
export function runValue(kind: StepType | null, rs: RunStep | undefined): string {
  if (!rs) return "";
  if (rs.status === "skipped") return t("run.skipped", { reason: rs.reason ?? rs.reason_code ?? "" });
  if (rs.status === "failed" && rs.error) return rs.error.message;
  if (kind === "jev") return Object.entries(rs.answers ?? {}).map(([k, v]) => `${k} = ${num(v)}`).join(", ");
  const last = rs.calls?.[rs.calls.length - 1];
  if ((kind === "ask" || kind === "task" || kind === "image") && last) return last.alias ? `${last.alias} → ${last.model}` : last.model;
  return "";
}

/** Direct children of a `call` step in the record (`propose/copy`, not `propose/x/y`). */
export function callChildren(ctx: RunCtx, path: string): RunStep[] {
  const prefix = `${path}/`;
  return [...ctx.steps.values()].filter((s) => s.step.startsWith(prefix) && !s.step.slice(prefix.length).includes("/"));
}
