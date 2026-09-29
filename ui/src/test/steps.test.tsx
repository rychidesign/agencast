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

// `fields` shapes as from GET …/scenarios/<s> (ig-post, tutorial-03/04, demo-call): [step, title, third line].
const CASES: [Step, string, string][] = [
  [step("ask", { ask: { agent: "copywriter", prompt: "Write an IG post\nabout: {{ inputs.topic }}" } }),
    "“Write an IG post about: {{ inputs.topic }}”", "copywriter"],
  [step("task", { task: { agent: "publisher", prompt: "Publish" } }), "“Publish”", "publisher"],
  [step("jev", { jev: { state: "x", questions: {
    on_brand: { type: "noul", instructions: "Does the text match the tone?" }, second: { type: "noul", instructions: "?" } } } }),
    "“Does the text match the tone?”", "noul · +1 question"],
  [step("image", { image: { model: "gemini-image", prompt: "{{ steps.p.description }}", aspect_ratio: "4:5" } }),
    "“{{ steps.p.description }}”", "gemini-image · 4:5"],
  [step("call", { call: { scenario: "ig-text", inputs: { text: "a", b: "c" } } }), "→ ig-text", "2 inputs"],
  [step("set", { set: { slogan: "a + b", percent: "round(x)" } }), "slogan, percent", ""],
  [step("fail", { fail: "Text is off-brand" }), "Text is off-brand", ""],
  [step("parallel", { budget_usd: 0.15 }, { branches: { short: [], long: [] } }), "short ∥ long", "2 branches, run in parallel"],
  [step("switch", { switch: { value: "steps.check.kind" } }, { cases: { product: [], action: [] }, default: [step("fail", { fail: "x" })] }),
    "by steps.check.kind: product, action, otherwise", ""],
  [step("output", { output: { caption: "{{ a }}", hashtags: "{{ b }}", image: "{{ c }}" } }), "caption, hashtags, image", ""],
];

describe("card title and third line by type (fidelity §6)", () => {
  it.each(CASES.map(([s, title, detail]) => [s.type, s, title, detail] as const))("%s", (_, s, title, detail) =>
    expect(stepLines(s)).toEqual({ title, detail }));

  it("image without a prompt: empty title, model and parameters in the third line", () =>
    expect(stepLines(step("image", { image: { model: "gemini-image", aspect_ratio: "{{ inputs.aspect_ratio }}", quality: "high", resolution: "1K" } })))
      .toEqual({ title: "", detail: "gemini-image · {{ inputs.aspect_ratio }} · high · 1K" }));

  it("switch without default does not show “otherwise”", () =>
    expect(stepLines(step("switch", { switch: { value: "v" } }, { cases: { a: [] }, default: [] })).title).toBe("by v: a"));

  it("step without a value = empty title (the card shows “fill in the panel”)", () =>
    expect(stepLines(step("ask", { ask: {} }))).toEqual({ title: "", detail: "" }));
});

describe("StepCard", () => {
  const ctx: ListCtx = { project: "p", onSelect: () => {}, errors: new Map() };

  // sizes measured from .pen (design 05): type mono 11 `type`, title 15 semibold, third line mono 12 `fg-secondary`,
  // 40 px circle filled with the type color
  it.each(CASES.map(([s, title, detail]) => [s.type, s, title, detail] as const))("%s: type · id line in lowercase, title, third line", (type, s, title, detail) => {
    render(<StepCard step={s} ctx={ctx} />);
    const card = screen.getByRole("button");
    expect(screen.getByText(`${type} · ${type}_1`).parentElement!.className).toContain("font-mono text-[11px] leading-4 text-type");
    expect(screen.getByText(title).className).toContain("text-[15px] leading-[22px]");
    expect(screen.getByText(title).className).toContain("font-semibold");
    if (detail) expect(screen.getByText(detail).className).toContain("font-mono text-xs leading-[17px] text-fg-secondary");
    expect(card.className).toContain("min-h-24");
    expect(card.querySelector(".size-10.rounded-full.bg-type\\/7 svg.text-type")).toBeTruthy();
  });

  it("placeholder, condition in the third line and a validation error", () => {
    const s = step("ask", { ask: { agent: "writer" } }, { id: "copy", when: "inputs.x == 1" });
    const errors = new Map([["copy", [{ message: "agent 'photographer' does not exist\n  detail" }]]]);
    render(<StepCard step={s} ctx={{ ...ctx, errors }} />);
    expect(screen.getByText("fill in the panel")).toBeTruthy();
    expect(screen.getByText("writer · when inputs.x == 1")).toBeTruthy();
    expect(screen.getByText("agent 'photographer' does not exist")).toBeTruthy();
  });

  it("selected card = surface-active fill (no border), a selected header also gets a ring (design 05 / 09)", () => {
    render(<>
      <StepCard step={step("ask", { ask: {} })} ctx={{ ...ctx, selected: "ask_1" }} />
      <HeaderCard inputs={null} outputs={null} selected onSelect={() => {}} />
    </>);
    const [card, header] = screen.getAllByRole("button");
    for (const c of [card, header]) {
      expect(c.className).toContain("bg-surface-active");
      expect(c.className).not.toContain("ring-offset");
      expect(c.getAttribute("aria-pressed")).toBe("true");
    }
    expect(card.className).not.toContain("ring-1");
    expect(header.className).toContain("ring-1 ring-accent");
  });
});

describe("HeaderCard", () => {
  it("shows inputs row by row with required flag and type, outputs below", () => {
    const { container } = render(<HeaderCard selected={false} onSelect={() => {}}
      inputs={{ web_name: { type: "string", required: true, description: "Website name" }, keywords: { default: [] } }}
      outputs={{ report: { type: "string" } }} />);
    const rows = [...container.querySelectorAll("span.bg-nested")];
    expect(rows.map((r) => r.textContent)).toEqual(["web_namerequiredstring", "keywords"]);
    expect(rows[0].getAttribute("title")).toBe("Website name");
    expect(screen.getByText("1 output: report")).toBeTruthy();
  });

  it("says so when there are no inputs and outputs", () => {
    render(<HeaderCard inputs={null} outputs={null} selected={false} onSelect={() => {}} />);
    expect(screen.getByText("no inputs")).toBeTruthy();
    expect(screen.getByText("no outputs")).toBeTruthy();
  });
});

describe("IconChain", () => {
  const types: StepType[] = ["ask", "jev", "fail", "ask", "jev", "fail", "image", "output"];
  it("at most 5 icons, then +N", () => {
    const { container } = render(<IconChain types={types} />);
    expect(container.querySelectorAll("svg")).toHaveLength(5);
    expect(screen.getByText("+3")).toBeTruthy();
  });
  it("up to 5 without a chip", () => {
    render(<IconChain types={["ask", "output"]} />);
    expect(screen.queryByText(/^\+/)).toBeNull();
  });
  it("plain text-type icons without circles and arrows", () => {
    const { container } = render(<IconChain types={["ask", "jev"]} />);
    expect(container.querySelector("ol.text-type")).toBeTruthy();
    expect(container.querySelector(".rounded-full")).toBeNull();
    expect(container.textContent).not.toContain("→");
  });
});

describe("reads from / output read by", () => {
  const a = step("ask", {}, { id: "copy" });
  const b = step("jev", {}, { id: "check", refs: ["steps.copy.caption"] });
  const c = step("fail", {}, { id: "stop", refs: ["steps.check.on_brand", "steps.copy.caption"] });
  it("from refs", () => {
    expect(readsFrom(c)).toEqual(["check", "copy"]);
    expect(readBy([a, b, c], "copy")).toEqual(["check", "stop"]);
  });
});
