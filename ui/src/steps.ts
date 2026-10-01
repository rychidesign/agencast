// What to show on a step card (§2.3 "Value by type" table, fidelity §6) — only from fields the API returned.
import { t } from "./i18n";
import type { Step } from "./types";

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : {});
const str = (v: unknown) => (typeof v === "string" ? v : "");

/** The `type · detail` line of the pill (fidelity §6): who does the work and with what; the prompt and the condition stay in the panel. */
export function stepDetail(step: Step): string {
  const b = obj(step.type ? step.fields[step.type] : undefined);
  const join = (...xs: string[]) => xs.filter(Boolean).join(" · ");
  switch (step.type) {
    case "ask":
    case "task":
      return str(b.agent);
    case "jev": {
      const qs = Object.values(obj(b.questions)).map(obj);
      return qs.length ? join(str(qs[0].type), qs.length > 1 ? t("step.value.moreQuestions", { n: qs.length - 1 }) : "") : "";
    }
    case "image":
      return join(str(b.model), str(b.aspect_ratio), str(b.quality), str(b.resolution));
    case "call":
      return b.scenario ? join(str(b.scenario), t("step.value.inputs", { n: Object.keys(obj(b.inputs)).length })) : "";
    case "parallel":
      return t("step.parallel.meta", { n: Object.keys(step.branches ?? {}).length });
    default:
      return "";
  }
}

/** Steps of the tree in file order (depth-first). */
export function flatten(steps: Step[]): Step[] {
  return steps.flatMap((s) => [
    s,
    ...flatten(Object.values(s.branches ?? {}).flat()),
    ...flatten(Object.values(s.cases ?? {}).flat()),
    ...flatten(s.default ?? []),
  ]);
}

/** `steps.copy.caption` → `copy`. */
const refStep = (ref: string) => ref.split(".")[1];

/** Which steps a step reads from (the "Reads from" chips). */
export const readsFrom = (step: Step) => [...new Set(step.refs.map(refStep))];

/** Which steps read the output of step `id` (the "Read by" chips). */
export const readBy = (all: Step[], id: string) => all.filter((s) => s.refs.some((r) => refStep(r) === id)).map((s) => s.id);
