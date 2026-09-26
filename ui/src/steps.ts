// Co ukázat na kartě kroku (§2.3 tabulka „Hodnota podle typu“) — jen z polí, která vrátilo API.
import { t } from "./i18n";
import type { Step } from "./types";

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : {});
const str = (v: unknown) => (typeof v === "string" ? v : "");
/** Víc řádků do jednoho (karta má jeden řádek s výpustkou). */
const line = (s: string) => s.replace(/\s+/g, " ").trim();
const quote = (s: string) => (s ? `„${line(s)}“` : "");
const keys = (v: unknown) => Object.keys(obj(v)).join(", ");

/** Druhý řádek pilulky; prázdný text = krok ještě nemá hodnotu („doplň v panelu“). */
export function stepValue(step: Step): string {
  const body = step.type ? step.fields[step.type] : undefined;
  const b = obj(body);
  switch (step.type) {
    case "ask":
    case "task": {
      const prompt = quote(str(b.prompt));
      return b.agent ? `${str(b.agent)}: ${prompt}`.trim() : prompt;
    }
    case "jev": {
      const qs = Object.values(obj(b.questions)).map(obj);
      if (!qs.length) return "";
      const first = [quote(str(qs[0].instructions)), str(qs[0].type)].filter(Boolean).join(" · ");
      return qs.length > 1 ? `${first}; ${t("step.value.moreQuestions", { n: qs.length - 1 })}` : first;
    }
    case "image":
      return [str(b.model), str(b.aspect_ratio), quote(str(b.prompt))].filter(Boolean).join(" · ");
    case "call": {
      if (!b.scenario) return "";
      return `→ ${str(b.scenario)} · ${t("step.value.inputs", { n: Object.keys(obj(b.inputs)).length })}`;
    }
    case "set":
    case "output":
      return keys(body);
    case "fail":
      return line(str(body));
    case "parallel":
      return Object.keys(step.branches ?? {}).join(" ∥ ");
    case "switch": {
      const cases = Object.keys(step.cases ?? {});
      if (step.default?.length) cases.push(t("step.switch.else"));
      return `${t("step.value.by", { value: str(b.value) })}: ${cases.join(", ")}`;
    }
    default:
      return "";
  }
}

/** Kroky ve stromu v pořadí souboru (hloubkově). */
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

/** Z kterých kroků krok čte (čipy „Čte z“). */
export const readsFrom = (step: Step) => [...new Set(step.refs.map(refStep))];

/** Které kroky čtou výstup kroku `id` (čipy „Výstup čtou“). */
export const readBy = (all: Step[], id: string) => all.filter((s) => s.refs.some((r) => refStep(r) === id)).map((s) => s.id);

/** Pole společná všem typům (spec scenario §3), ostatní klíče `fields` jsou tělo typu. */
export const RELIABILITY = ["timeout", "budget_usd", "retry", "on_error", "default"] as const;
