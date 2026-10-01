import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HeaderCard, StepCard, type ListCtx } from "../components/StepCards";
import { IconChain } from "../components/TypeIcon";
import { readBy, readsFrom, stepDetail } from "../steps";
import type { Step, StepType } from "../types";

afterEach(cleanup);

const step = (type: StepType, fields: Record<string, unknown>, extra: Partial<Step> = {}): Step => ({
  nn: 1, address: ["steps", 0], id: `${type}_1`, type, when: null, fields, refs: [], ...extra,
});

// `fields` shapes as from GET …/scenarios/<s> (ig-post, tutorial-03/04, demo-call): [step, detail after the type].
const CASES: [Step, string][] = [
  [step("ask", { ask: { agent: "copywriter", prompt: "Write an IG post\nabout: {{ inputs.topic }}" } }), "copywriter"],
  [step("task", { task: { agent: "publisher", prompt: "Publish" } }), "publisher"],
  [step("jev", { jev: { state: "x", questions: {
    on_brand: { type: "noul", instructions: "Does the text match the tone?" }, second: { type: "noul", instructions: "?" } } } }),
    "noul · +1 question"],
  [step("image", { image: { model: "gemini-image", prompt: "{{ steps.p.description }}", aspect_ratio: "4:5" } }), "gemini-image · 4:5"],
  [step("call", { call: { scenario: "ig-text", inputs: { text: "a", b: "c" } } }), "ig-text · 2 inputs"],
  [step("set", { set: { slogan: "a + b", percent: "round(x)" } }), ""],
  [step("fail", { fail: "Text is off-brand" }), ""],
  [step("parallel", { budget_usd: 0.15 }, { branches: { short: [], long: [] } }), "2 branches, run in parallel"],
  [step("switch", { switch: { value: "steps.check.kind" } }, { cases: { product: [], action: [] }, default: [step("fail", { fail: "x" })] }), ""],
  [step("output", { output: { caption: "{{ a }}", hashtags: "{{ b }}", image: "{{ c }}" } }), ""],
];

describe("card detail by type (fidelity §6)", () => {
  it.each(CASES.map(([s, detail]) => [s.type, s, detail] as const))("%s", (_, s, detail) => expect(stepDetail(s)).toBe(detail));

  it("image without a prompt: model and parameters", () =>
    expect(stepDetail(step("image", { image: { model: "gemini-image", aspect_ratio: "{{ inputs.aspect_ratio }}", quality: "high", resolution: "1K" } })))
      .toBe("gemini-image · {{ inputs.aspect_ratio }} · high · 1K"));

  it("empty step = empty detail", () => expect(stepDetail(step("ask", { ask: {} }))).toBe(""));
});

describe("StepCard", () => {
  const ctx: ListCtx = { project: "p", onSelect: () => {}, errors: new Map() };

  // `type · detail` mono 11 `type`, `n. id` as the name (15 semibold, not mono), no prompt; 40 px circle filled with the type color
  it.each(CASES.map(([s, detail]) => [s.type, s, detail] as const))("%s: type · detail line, n. id as the name, no prompt", (type, s, detail) => {
    render(<StepCard step={s} ctx={ctx} />);
    const card = screen.getByRole("button");
    expect(screen.getByText([type, detail].filter(Boolean).join(" · ")).parentElement!.className).toContain("font-mono text-[11px] leading-4 text-type");
    const name = screen.getByText(`${type}_1`, { exact: false });
    expect(name.textContent).toBe(`1. ${type}_1`);
    expect(name.className).toContain("text-[15px] leading-[22px] font-semibold");
    expect(name.className).not.toContain("font-mono");
    expect(card.textContent).not.toMatch(/Write an IG post|Publish|Does the text|off-brand/);
    expect(card.className).toContain("min-h-18");
    expect(card.querySelector(".size-10.rounded-full.bg-type\\/7 svg.text-type")).toBeTruthy();
  });

  it("a condition is only marked (expression in the tooltip), a validation error", () => {
    const s = step("ask", { ask: { agent: "writer" } }, { id: "copy", when: "inputs.x == 1" });
    const errors = new Map([["copy", [{ message: "agent 'photographer' does not exist\n  detail" }]]]);
    render(<StepCard step={s} ctx={{ ...ctx, errors }} />);
    expect(screen.getByText("ask · writer")).toBeTruthy();
    expect(screen.getByText("conditional").getAttribute("title")).toBe("when inputs.x == 1");
    expect(screen.queryByText("when inputs.x == 1")).toBeNull();
    expect(screen.getByRole("button").getAttribute("aria-label")).toBe("Step 1: ask copy, conditional");
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
