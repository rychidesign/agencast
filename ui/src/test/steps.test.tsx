import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HeaderCard, StepCard, type ListCtx } from "../components/StepCards";
import { IconChain } from "../components/TypeIcon";
import { readBy, readsFrom, stepValue } from "../steps";
import type { Step, StepType } from "../types";

afterEach(cleanup);

const step = (type: StepType, fields: Record<string, unknown>, extra: Partial<Step> = {}): Step => ({
  nn: 1, address: ["steps", 0], id: `${type}_1`, type, when: null, fields, refs: [], ...extra,
});

// Tvary `fields` jako z GET …/scenarios/<s> (ig-post, tutorial-03/04, ukazka-call).
const CASES: [Step, string][] = [
  [step("ask", { ask: { agent: "copywriter", prompt: "Napiš IG příspěvek\nna téma: {{ inputs.tema }}" } }),
    "copywriter: „Napiš IG příspěvek na téma: {{ inputs.tema }}“"],
  [step("task", { task: { agent: "publisher", prompt: "Zveřejni" } }), "publisher: „Zveřejni“"],
  [step("jev", { jev: { state: "x", questions: {
    on_brand: { type: "noul", instructions: "Odpovídá text tónu?" }, druha: { type: "noul", instructions: "?" } } } }),
    "„Odpovídá text tónu?“ · noul; +1 otázka"],
  [step("image", { image: { model: "gemini-image", prompt: "{{ steps.p.popis }}", aspect_ratio: "4:5" } }),
    "gemini-image · 4:5 · „{{ steps.p.popis }}“"],
  [step("image", { image: { model: "gemini-image", aspect_ratio: "{{ inputs.pomer }}", quality: "high", resolution: "1K" } }),
    "gemini-image · {{ inputs.pomer }} · high · 1K"],
  [step("call", { call: { scenario: "ig-text", inputs: { text: "a", b: "c" } } }), "→ ig-text · 2 vstupy"],
  [step("set", { set: { slogan: "a + b", procenta: "round(x)" } }), "slogan, procenta"],
  [step("fail", { fail: "Text neodpovídá značce" }), "Text neodpovídá značce"],
  [step("parallel", { budget_usd: 0.15 }, { branches: { kratka: [], dlouha: [] } }), "kratka ∥ dlouha"],
  [step("switch", { switch: { value: "steps.kontrola.druh" } }, { cases: { produkt: [], akce: [] }, default: [step("fail", { fail: "x" })] }),
    "podle steps.kontrola.druh: produkt, akce, jinak"],
  [step("output", { output: { caption: "{{ a }}", hashtags: "{{ b }}", image: "{{ c }}" } }), "caption, hashtags, image"],
];

describe("hodnota na kartě podle typu (§2.3)", () => {
  it.each(CASES.map(([s, v]) => [s.type, s, v] as const))("%s", (_, s, value) => expect(stepValue(s)).toBe(value));

  it("switch bez default neukazuje „jinak“", () =>
    expect(stepValue(step("switch", { switch: { value: "v" } }, { cases: { a: [] }, default: [] }))).toBe("podle v: a"));

  it("krok bez hodnoty = prázdný text (karta ukáže „doplň v panelu“)", () =>
    expect(stepValue(step("ask", { ask: {} }))).toBe(""));
});

describe("StepCard", () => {
  const ctx: ListCtx = { project: "p", onSelect: () => {}, errors: new Map() };

  it.each(CASES.map(([s, v]) => [s.type, s, v] as const))("%s: eyebrow TYP · id a hodnota", (type, s, value) => {
    render(<StepCard step={s} ctx={ctx} />);
    const card = screen.getByRole("button");
    expect(card.textContent).toContain(`${type} · ${type}_1`);
    expect(screen.getByText(value)).toBeTruthy();
  });

  it("zástupný text, podmínka a chyba validace", () => {
    const s = step("ask", { ask: {} }, { id: "copy", when: "inputs.x == 1" });
    const errors = new Map([["copy", [{ message: "agent „fotograf“ neexistuje\n  detail" }]]]);
    render(<StepCard step={s} ctx={{ ...ctx, errors }} />);
    expect(screen.getByText("doplň v panelu")).toBeTruthy();
    expect(screen.getByText("když inputs.x == 1")).toBeTruthy();
    expect(screen.getByText("agent „fotograf“ neexistuje")).toBeTruthy();
  });

  it("vybraná karta i hlavička mají akcentový prstenec bez offsetu", () => {
    render(<>
      <StepCard step={step("ask", { ask: {} })} ctx={{ ...ctx, selected: "ask_1" }} />
      <HeaderCard inputs={null} outputs={null} selected onSelect={() => {}} />
    </>);
    for (const card of screen.getAllByRole("button")) {
      expect(card.className).toContain("ring-2 ring-accent");
      expect(card.className).not.toContain("ring-offset");
      expect(card.getAttribute("aria-pressed")).toBe("true");
    }
  });
});

describe("IconChain", () => {
  const types: StepType[] = ["ask", "jev", "fail", "ask", "jev", "fail", "image", "output"];
  it("nejvýš 5 ikon, pak +N", () => {
    const { container } = render(<IconChain types={types} />);
    expect(container.querySelectorAll("svg")).toHaveLength(5);
    expect(screen.getByText("+3")).toBeTruthy();
  });
  it("do 5 bez čipu", () => {
    render(<IconChain types={["ask", "output"]} />);
    expect(screen.queryByText(/^\+/)).toBeNull();
  });
  it("ikony jsou v kolečkách bez modrých čtverců", () => {
    const { container } = render(<IconChain types={["ask"]} />);
    expect(container.querySelector("li span.bg-nested.rounded-full.text-type")).toBeTruthy();
    expect(container.innerHTML).not.toContain("bg-blue");
  });
});

describe("čte z / výstup čtou", () => {
  const a = step("ask", {}, { id: "copy" });
  const b = step("jev", {}, { id: "kontrola", refs: ["steps.copy.caption"] });
  const c = step("fail", {}, { id: "stop", refs: ["steps.kontrola.on_brand", "steps.copy.caption"] });
  it("z refs", () => {
    expect(readsFrom(c)).toEqual(["kontrola", "copy"]);
    expect(readBy([a, b, c], "copy")).toEqual(["kontrola", "stop"]);
  });
});
