import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { StepPanel } from "../components/StepPanel";
import type { WStep } from "../edit";
import type { Project } from "../types";

afterEach(cleanup);

it("image parameters accept templates and offer variables", () => {
  const step: WStep = { uid: "photo", nn: 1, address: ["steps", 0], id: "photo", type: "image", when: null,
    fields: { image: { model: "gemini-image", prompt: "Coffee", aspect_ratio: "{{ inputs.aspect_ratio }}" } }, refs: [] };
  const project: Project = { name: "p", root: "/tmp/p", models: { "gemini-image": "test/image" }, limits: {},
    scenarios: [], agents: [], skills: [], mcp_servers: [], env: {}, errors: [],
    links: { scenario_agent: [], scenario_step_agent: [], scenario_scenario: [], agent_skill: [], agent_server: [] } };
  const change = vi.fn();
  render(<StepPanel step={step} steps={[step]} header={{ description: "", callable: false, outputs: null,
    inputs: { aspect_ratio: { type: "string", default: "4:5" } } }} project={project} scenario="s" errors={[]}
    onClose={vi.fn()} onSelect={vi.fn()} edit={{ change, retype: vi.fn(), remove: vi.fn(), rename: vi.fn() }} />);
  // PanelShell: the eyebrow “STEP 1 · image” names the panel, the title is the step id (not mono, like the card), the type is a form field
  const panel = screen.getByRole("complementary", { name: "STEP 1 · image" });
  expect(within(panel).getAllByText("photo")[0].className).not.toContain("font-mono");
  expect((screen.getByRole("combobox", { name: "Step type" }) as HTMLSelectElement).value).toBe("image");
  for (const [label, field, placeholder] of [["Aspect ratio", "aspect_ratio", "4:5"], ["Quality", "quality", "medium"], ["Resolution", "resolution", "1K"]]) {
    const input = screen.getByRole("combobox", { name: label }) as HTMLInputElement;
    expect(input.placeholder).toBe(placeholder);
    fireEvent.change(input, { target: { value: "{{inputs.aspect_ratio}}" } });
    const update = change.mock.lastCall![0] as (s: WStep) => WStep;
    expect((update(step).fields.image as Record<string, string>)[field]).toBe("{{inputs.aspect_ratio}}");
    fireEvent.click(within(input.parentElement!).getByRole("button", { name: "Insert variable" }));
    expect(screen.getByRole("menuitem", { name: "inputs.aspect_ratio" })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  }
});
