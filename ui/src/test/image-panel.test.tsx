import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { StepPanel } from "../components/StepPanel";
import type { WStep } from "../edit";
import type { Project } from "../types";

afterEach(cleanup);

it("parametry obrázku přijímají šablony a nabízejí proměnné", () => {
  const step: WStep = { uid: "foto", nn: 1, address: ["steps", 0], id: "foto", type: "image", when: null,
    fields: { image: { model: "gemini-image", prompt: "Káva", aspect_ratio: "{{ inputs.pomer }}" } }, refs: [] };
  const project: Project = { name: "p", root: "/tmp/p", models: { "gemini-image": "test/image" }, limits: {},
    scenarios: [], agents: [], skills: [], mcp_servers: [], env: {}, errors: [],
    links: { scenario_agent: [], scenario_step_agent: [], scenario_scenario: [], agent_skill: [], agent_server: [] } };
  const change = vi.fn();
  render(<StepPanel step={step} steps={[step]} header={{ description: "", callable: false, outputs: null,
    inputs: { pomer: { type: "string", default: "4:5" } } }} project={project} scenario="s" errors={[]}
    onClose={vi.fn()} onSelect={vi.fn()} edit={{ change, retype: vi.fn(), remove: vi.fn(), rename: vi.fn() }} />);
  // PanelShell: eyebrow „KROK 1 · image“ pojmenuje panel, titul je id kroku, typ je pole formuláře
  const panel = screen.getByRole("complementary", { name: "KROK 1 · image" });
  expect(within(panel).getAllByText("foto")[0].className).toContain("font-mono");
  expect((screen.getByRole("combobox", { name: "Typ kroku" }) as HTMLSelectElement).value).toBe("image");
  for (const [label, field, placeholder] of [["Poměr stran", "aspect_ratio", "4:5"], ["Kvalita", "quality", "medium"], ["Rozlišení", "resolution", "1K"]]) {
    const input = screen.getByRole("combobox", { name: label }) as HTMLInputElement;
    expect(input.placeholder).toBe(placeholder);
    fireEvent.change(input, { target: { value: "{{inputs.pomer}}" } });
    const update = change.mock.lastCall![0] as (s: WStep) => WStep;
    expect((update(step).fields.image as Record<string, string>)[field]).toBe("{{inputs.pomer}}");
    fireEvent.click(within(input.parentElement!).getByRole("button", { name: "Vložit proměnnou" }));
    expect(screen.getByRole("menuitem", { name: "inputs.pomer" })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  }
});
