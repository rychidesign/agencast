// Údaje běhu po krocích: z `GET …/runs/<id>` (stav, čas, cena) a z events.jsonl (volání, odpovědi Jev,
// chyby) — events.jsonl je strojový log určený i pro GUI (run-record.md), API ho vydává jako soubor.
import { t } from "./i18n";
import type { RunEvent, RunStep, StepType } from "./types";

export interface RunCtx {
  steps: Map<string, RunStep>;
  events: RunEvent[];
  /** Kroky volaného scénáře mají cestu `navrh/copy`; tady prefix `navrh/`. */
  prefix: string;
  /** Teď (ms) pro tikající čas běžícího kroku. */
  now: number;
}

export const parseEvents = (text: string): RunEvent[] =>
  text.split("\n").flatMap((l) => {
    try {
      return l.trim() ? [JSON.parse(l) as RunEvent] : [];
    } catch {
      return []; // řádek, který běh právě zapisuje
    }
  });

export const eventsOf = (events: RunEvent[], path: string, type?: string) =>
  events.filter((e) => e.step === path && (!type || e.type === type));

const num = (v: unknown) => (typeof v === "number" ? v.toLocaleString("cs", { maximumFractionDigits: 2 }) : String(v));

/** Druhý řádek karty v prohlížeči běhu; prázdný = ukázat hodnotu z editoru. */
export function runValue(kind: StepType | null, path: string, ctx: RunCtx): string {
  const rs = ctx.steps.get(path);
  if (!rs) return "";
  if (rs.status === "skipped") return t("run.skipped", { reason: rs.reason ?? rs.reason_code ?? "" });
  const errors = eventsOf(ctx.events, path, "error");
  if (rs.status === "failed" && errors.length) return String(errors[errors.length - 1].message ?? "");
  if (kind === "jev") {
    const calls = eventsOf(ctx.events, path, "jev_call");
    const answers = (calls[calls.length - 1]?.answers ?? {}) as Record<string, unknown>;
    return Object.entries(answers).map(([k, v]) => `${k} = ${num(v)}`).join(", ");
  }
  if (kind === "ask" || kind === "task" || kind === "image") {
    const calls = eventsOf(ctx.events, path, "model_call");
    const last = calls[calls.length - 1];
    return last ? `${last.alias} → ${last.model}` : "";
  }
  return "";
}

/** Varování: krok selhal s `on_error: continue`. */
export const continued = (events: RunEvent[], path: string) =>
  eventsOf(events, path, "step_finished").some((e) => e.continued === true);

/** Přímí potomci kroku `call` v záznamu (`navrh/copy`, ne `navrh/x/y`). */
export function callChildren(ctx: RunCtx, path: string): RunStep[] {
  const prefix = `${path}/`;
  return [...ctx.steps.values()].filter((s) => s.step.startsWith(prefix) && !s.step.slice(prefix.length).includes("/"));
}

/** Složka kroku ve složce běhu: `steps/<nn>-<id>/`, u `call` vnořeně (`steps/02-ton/steps/01-kontrola/`). */
export function stepDir(files: string[], path: string): string | undefined {
  const re = new RegExp(`^${path.split("/").map((id) => `steps/\\d+-${id}/`).join("")}`);
  const hit = files.find((f) => re.test(f));
  return hit?.match(re)?.[0];
}

/** Soubory přímo ve složce kroku (bez vnořených `steps/` volaného scénáře). */
export const stepFiles = (files: string[], dir: string) =>
  files.filter((f) => f.startsWith(dir) && !f.slice(dir.length).startsWith("steps/"));
