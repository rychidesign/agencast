// Údaje běhu po krocích z `GET …/runs/<id>` (`steps`: stav, čas, cena, chyba, volání, odpovědi Jev).
import { t } from "./i18n";
import type { RunStep, Step, StepType } from "./types";

export interface RunCtx {
  steps: Map<string, RunStep>;
  /** Kroky volaného scénáře mají cestu `navrh/copy`; tady prefix `navrh/`. */
  prefix: string;
  /** Teď (ms) pro tikající čas běžícího kroku. */
  now: number;
  /** Stromy volaných scénářů ze snímku běhu (`callees`). */
  callees: Record<string, Step[]>;
}

const num = (v: unknown) => (typeof v === "number" ? v.toLocaleString("cs", { maximumFractionDigits: 2 }) : String(v));

/** Druhý řádek karty v prohlížeči běhu; prázdný = ukázat hodnotu z editoru. */
export function runValue(kind: StepType | null, rs: RunStep | undefined): string {
  if (!rs) return "";
  if (rs.status === "skipped") return t("run.skipped", { reason: rs.reason ?? rs.reason_code ?? "" });
  if (rs.status === "failed" && rs.error) return rs.error.message;
  if (kind === "jev") return Object.entries(rs.answers ?? {}).map(([k, v]) => `${k} = ${num(v)}`).join(", ");
  const last = rs.calls?.[rs.calls.length - 1];
  if ((kind === "ask" || kind === "task" || kind === "image") && last) return last.alias ? `${last.alias} → ${last.model}` : last.model;
  return "";
}

/** Přímí potomci kroku `call` v záznamu (`navrh/copy`, ne `navrh/x/y`). */
export function callChildren(ctx: RunCtx, path: string): RunStep[] {
  const prefix = `${path}/`;
  return [...ctx.steps.values()].filter((s) => s.step.startsWith(prefix) && !s.step.slice(prefix.length).includes("/"));
}
