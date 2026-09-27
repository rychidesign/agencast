import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HeaderCard, StepCard, type ListCtx } from "../components/StepCards";
import { IconChain } from "../components/TypeIcon";
import { readBy, readsFrom, stepLines } from "../steps";
import type { Step, StepType } from "../types";

afterEach(cleanup);

const step = (type: StepType, fields: Record<string, unknown>, extra: Partial<Step> = {}): Step => ({
  nn: 1, address: ["steps", 0], id: `${type}_1`, type, when: null, fields, refs: [], ...extra,
});

// Tvary `fields` jako z GET …/scenarios/<s> (ig-post, tutorial-03/04, ukazka-call): [krok, titul, třetí řádek].
const CASES: [Step, string, string][] = [
  [step("ask", { ask: { agent: "copywriter", prompt: "Napiš IG příspěvek\nna téma: {{ inputs.tema }}" } }),
    "„Napiš IG příspěvek na téma: {{ inputs.tema }}“", "copywriter"],
  [step("task", { task: { agent: "publisher", prompt: "Zveřejni" } }), "„Zveřejni“", "publisher"],
  [step("jev", { jev: { state: "x", questions: {
    on_brand: { type: "noul", instructions: "Odpovídá text tónu?" }, druha: { type: "noul", instructions: "?" } } } }),
    "„Odpovídá text tónu?“", "noul · +1 otázka"],
  [step("image", { image: { model: "gemini-image", prompt: "{{ steps.p.popis }}", aspect_ratio: "4:5" } }),
    "„{{ steps.p.popis }}“", "gemini-image · 4:5"],
  [step("call", { call: { scenario: "ig-text", inputs: { text: "a", b: "c" } } }), "→ ig-text", "2 vstupy"],
  [step("set", { set: { slogan: "a + b", procenta: "round(x)" } }), "slogan, procenta", ""],
  [step("fail", { fail: "Text neodpovídá značce" }), "Text neodpovídá značce", ""],
  [step("parallel", { budget_usd: 0.15 }, { branches: { kratka: [], dlouha: [] } }), "kratka ∥ dlouha", "2 větve, běží zároveň"],
  [step("switch", { switch: { value: "steps.kontrola.druh" } }, { cases: { produkt: [], akce: [] }, default: [step("fail", { fail: "x" })] }),
    "podle steps.kontrola.druh: produkt, akce, jinak", ""],
  [step("output", { output: { caption: "{{ a }}", hashtags: "{{ b }}", image: "{{ c }}" } }), "caption, hashtags, image", ""],
];

describe("titul a třetí řádek karty podle typu (fidelity §6)", () => {
  it.each(CASES.map(([s, title, detail]) => [s.type, s, title, detail] as const))("%s", (_, s, title, detail) =>
    expect(stepLines(s)).toEqual({ title, detail }));

  it("image bez promptu: titul prázdný, model a parametry ve třetím řádku", () =>
    expect(stepLines(step("image", { image: { model: "gemini-image", aspect_ratio: "{{ inputs.pomer }}", quality: "high", resolution: "1K" } })))
      .toEqual({ title: "", detail: "gemini-image · {{ inputs.pomer }} · high · 1K" }));

  it("switch bez default neukazuje „jinak“", () =>
    expect(stepLines(step("switch", { switch: { value: "v" } }, { cases: { a: [] }, default: [] })).title).toBe("podle v: a"));

  it("krok bez hodnoty = prázdný titul (karta ukáže „doplň v panelu“)", () =>
    expect(stepLines(step("ask", { ask: {} }))).toEqual({ title: "", detail: "" }));
});

describe("StepCard", () => {
  const ctx: ListCtx = { project: "p", onSelect: () => {}, errors: new Map() };

  it.each(CASES.map(([s, title, detail]) => [s.type, s, title, detail] as const))("%s: řádek typ · id malými, titul, třetí řádek", (type, s, title, detail) => {
    render(<StepCard step={s} ctx={ctx} />);
    const card = screen.getByRole("button");
    expect(screen.getByText(`${type} · ${type}_1`).parentElement!.className).toContain("font-mono text-xs text-type");
    expect(screen.getByText(title).className).toContain("text-base font-semibold");
    if (detail) expect(screen.getByText(detail).className).toContain("font-mono text-xs text-fg-muted");
    expect(card.className).toContain("min-h-24");
    expect(card.querySelector(".size-10.rounded-full.bg-nested svg.text-type")).toBeTruthy();
  });

  it("zástupný text, podmínka ve třetím řádku a chyba validace", () => {
    const s = step("ask", { ask: { agent: "pisatel" } }, { id: "copy", when: "inputs.x == 1" });
    const errors = new Map([["copy", [{ message: "agent „fotograf“ neexistuje\n  detail" }]]]);
    render(<StepCard step={s} ctx={{ ...ctx, errors }} />);
    expect(screen.getByText("doplň v panelu")).toBeTruthy();
    expect(screen.getByText("pisatel · když inputs.x == 1")).toBeTruthy();
    expect(screen.getByText("agent „fotograf“ neexistuje")).toBeTruthy();
  });

  it("vybraná karta i hlavička: surface-active a prstenec 1 px accent bez offsetu", () => {
    render(<>
      <StepCard step={step("ask", { ask: {} })} ctx={{ ...ctx, selected: "ask_1" }} />
      <HeaderCard inputs={null} outputs={null} selected onSelect={() => {}} />
    </>);
    for (const card of screen.getAllByRole("button")) {
      expect(card.className).toContain("bg-surface-active");
      expect(card.className).toContain("ring-1 ring-accent");
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
  it("prosté ikony text-type bez koleček a šipek", () => {
    const { container } = render(<IconChain types={["ask", "jev"]} />);
    expect(container.querySelector("ol.text-type")).toBeTruthy();
    expect(container.querySelector(".rounded-full")).toBeNull();
    expect(container.textContent).not.toContain("→");
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
