// What to show on a step card (§2.3 "Value by type" table, fidelity §6) — only from fields the API returned.
import { t } from "./i18n";
import type { Step } from "./types";

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : {});
const str = (v: unknown) => (typeof v === "string" ? v : "");
/** Join several lines into one (card rows are ellipsized). */
const line = (s: string) => s.replace(/\s+/g, " ").trim();
const quote = (s: string) => (s ? t("common.quoted", { text: line(s) }) : "");
const keys = (v: unknown) => Object.keys(obj(v)).join(", ");

/** Title and third line of the pill (fidelity §6); an empty title = the step has no value yet ("fill in the panel"). */
export function stepLines(step: Step): { title: string; detail: string } {
  const body = step.type ? step.fields[step.type] : undefined;
  const b = obj(body);
  const join = (...xs: string[]) => xs.filter(Boolean).join(" · ");
  switch (step.type) {
    case "ask":
    case "task":
      return { title: quote(str(b.prompt)), detail: str(b.agent) };
    case "jev": {
      const qs = Object.values(obj(b.questions)).map(obj);
      if (!qs.length) return { title: "", detail: "" };
      return {
        title: quote(str(qs[0].instructions)),
        detail: join(str(qs[0].type), qs.length > 1 ? t("step.value.moreQuestions", { n: qs.length - 1 }) : ""),
      };
    }
    case "image":
      return { title: quote(str(b.prompt)), detail: join(str(b.model), str(b.aspect_ratio), str(b.quality), str(b.resolution)) };
    case "call":
      return b.scenario
        ? { title: `→ ${str(b.scenario)}`, detail: t("step.value.inputs", { n: Object.keys(obj(b.inputs)).length }) }
        : { title: "", detail: "" };
    case "set":
    case "output":
      return { title: keys(body), detail: "" };
    case "fail":
      return { title: line(str(body)), detail: "" };
    case "parallel": {
      const names = Object.keys(step.branches ?? {});
      return { title: names.join(" ∥ "), detail: t("step.parallel.meta", { n: names.length }) };
    }
    case "switch": {
      const cases = Object.keys(step.cases ?? {});
      if (step.default?.length) cases.push(t("step.switch.else"));
      return { title: `${t("step.value.by", { value: str(b.value) })}: ${cases.join(", ")}`, detail: "" };
    }
    default:
      return { title: "", detail: "" };
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
