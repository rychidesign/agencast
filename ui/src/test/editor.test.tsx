// Scenario editor, YAML mode, starting a run and the agent form against a fake API (fetch mock).
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import { App } from "../App";
import { filterTypes, TypePicker } from "../components/TypePicker";
import { runInputs } from "../components/RunPanel";
import type { Project, Scenario } from "../types";

const TEXT = "version: 1\nname: s\n# comment\nsteps:\n  - id: copy\n    ask: {agent: copywriter, prompt: hello}\n  - id: out\n    output: {text: x}\n";

const scenario = (etag = "e0"): Scenario => ({
  name: "s", etag, description: "Test", inputs: { topic: { type: "string", required: true } },
  outputs: { text: { type: "string" } }, callable: false, steps_count: 2, types: ["ask", "output"], last_run: null, errors: [],
  steps: [
    { nn: 1, address: ["steps", 0], id: "copy", type: "ask", when: null, fields: { ask: { agent: "copywriter", prompt: "hello" } }, refs: [], agent: "copywriter" },
    { nn: 2, address: ["steps", 1], id: "out", type: "output", when: null, fields: { output: { text: "{{ steps.copy.text }}" } }, refs: ["steps.copy.text"] },
  ],
});

const project: Project = {
  name: "p", root: "/tmp/p", models: { smart: "anthropic/claude-haiku-4.5" },
  limits: { run_budget_usd: 1, run_timeout: "1h", daily_budget_usd: 5 },
  scenarios: [{ ...scenario(), steps: undefined } as unknown as Scenario],
  agents: [
    { name: "copywriter", etag: "a0", description: "Writes", model: "smart", model_id: null, skills: [], mcp: [], tools: {}, errors: [] },
    { name: "publisher", etag: "a1", description: "Publishes", model: "smart", model_id: null, skills: [], mcp: [], tools: {}, errors: [] },
  ],
  skills: [], errors: [],
  mcp_servers: [{ name: "instagram", type: "http", agents: ["publisher"], tools: ["publish_media"], scenarios: null },
    { name: "weather", type: "http", agents: ["publisher"], tools: null, scenarios: null }],
  links: { scenario_agent: [["s", "copywriter"]], scenario_step_agent: [["s", "copy", "copywriter"]], scenario_scenario: [], agent_skill: [], agent_server: [] },
  env: { OPENROUTER_API_KEY: true },
};

type Handler = (method: string, url: string, body: Record<string, unknown>) => [number, unknown] | undefined;
let calls: { method: string; url: string; body: Record<string, unknown> }[];
let etag: string;
let text: string;
let extra: Handler | undefined;

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  calls = [];
  etag = "e0";
  text = TEXT;
  extra = undefined;
  localStorage.clear();
  sessionStorage.clear();
  saveToken("t");
  vi.stubGlobal("fetch", vi.fn(async (u: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const url = u.replace(/^https?:\/\/[^/]+/, "");
    const body = init.body ? JSON.parse(String(init.body)) : {};
    if (method !== "GET" && method !== "HEAD" && !url.endsWith("/render")) calls.push({ method, url, body });
    const hit = extra?.(method, url, body);
    if (hit) return json(...hit);
    if (method === "HEAD") return new Response(null, { status: 200, headers: { ETag: `"${etag}"` } });
    if (url.endsWith("/render")) return json(200, { text, tree: [], errors: [] });
    if (url === "/projects/p") return json(200, project);
    if (url === "/projects/p/scenarios/s") return json(200, scenario(etag));
    if (url.startsWith("/projects/p/files/")) {
      const path = url.slice("/projects/p/files/".length);
      if (path.startsWith("agents/"))
        return json(200, { path, etag: "a1", text: "---\n…", errors: [], frontmatter: { version: 1, name: "publisher", description: "Publishes", model: "smart", limits: { budget_usd: 0.2 } }, body: "You are the admin.\n" });
      return json(200, { path, etag, text, errors: [] });
    }
    if (url === "/projects/p/validate") return json(200, { errors: [] });
    if (url === "/projects/p/spend") return json(200, { day: "x", total_usd: 0.42, runs: [] });
    if (url.endsWith("/scenarios/s/batch")) {
      etag = `e${Number(etag.slice(1)) + 1}`;
      return json(200, { etag, errors: [] });
    }
    return json(404, { error: `unknown ${method} ${url}` });
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function openEditor(hash = "#/p/p/scenarios/s") {
  location.hash = hash;
  await act(async () => void render(<App />));
  if (!hash.includes("mode=yaml")) await screen.findByRole("button", { name: /Step 1: ask copy/ });
}

const save = async () => {
  await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Save" })));
};

describe("TypePicker", () => {
  it("typing filters, arrows and Enter pick, Esc closes", () => {
    expect(filterTypes("j")).toEqual(["jev"]);
    expect(filterTypes("s")).toEqual(["switch", "set"]);
    expect(filterTypes("gener")).toEqual(["image"]);
    const pick = vi.fn();
    const close = vi.fn();
    render(<TypePicker onPick={pick} onClose={close} paste="check" />);
    const list = screen.getByRole("listbox");
    expect(screen.getAllByRole("option")[0].textContent).toBe("Paste “check” here");
    expect(screen.queryByText("output")).toBeNull();
    fireEvent.keyDown(list, { key: "s" });
    fireEvent.keyDown(list, { key: "e" });
    expect(screen.getAllByRole("option").map((o) => o.textContent?.slice(0, 3))).toEqual(["set"]);
    fireEvent.keyDown(list, { key: "Backspace" });
    fireEvent.keyDown(list, { key: "ArrowDown" });
    fireEvent.keyDown(list, { key: "Enter" });
    expect(pick).toHaveBeenCalledWith("set");
    fireEvent.keyDown(list, { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });
});

describe("scenario editor", () => {
  it("rename sends the etag and the new name, reloads files and navigates", async () => {
    extra = (method, url) => (method === "POST" && url === "/projects/p/scenarios/s/rename"
      ? [200, { name: "t", etag: "e1", changed: ["scenarios/t.yaml", "scenarios/caller.yaml"], errors: [] }]
      : undefined);
    await openEditor();
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename" }));
    const dialog = screen.getByRole("dialog", { name: "Rename scenario “s”?" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /Name/ }), { target: { value: "t" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Rename" }));

    expect(calls).toContainEqual({
      method: "POST", url: "/projects/p/scenarios/s/rename", body: { etag: "e0", name: "t" },
    });
    expect(await screen.findByRole("heading", { name: "t" })).toBeTruthy();
    expect(location.hash).toBe("#/p/p/scenarios/t");
    expect(await screen.findByText("Updated: scenarios/t.yaml, scenarios/caller.yaml")).toBeTruthy();
  });

  it("inserting a step: + → type → panel; Save = one batch with the etag, then Saved", async () => {
    await openEditor();
    fireEvent.click(screen.getAllByRole("button", { name: "Insert step after copy" })[0]); // between copy and out
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "f" });
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Enter" });
    const panel = await screen.findByRole("complementary");
    fireEvent.change(within(panel).getByRole("combobox", { name: /Message/ }), { target: { value: "End" } });
    expect(screen.getByText("Unsaved")).toBeTruthy();
    await save();
    expect(calls).toEqual([{
      method: "POST", url: "/projects/p/scenarios/s/batch",
      body: { etag: "e0", ops: [{ op: "add_step", after: ["steps", 0], step: { id: "fail_1", fail: "End" } }] },
    }]);
    expect(await screen.findByText(/Saved ✓/)).toBeTruthy();
  });

  it("move with Alt+↓, delete with the Delete key and undo", async () => {
    await openEditor();
    fireEvent.click(screen.getAllByRole("button", { name: "Insert step after copy" })[0]);
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Enter" }); // ask_1 after copy
    const copy = screen.getByRole("button", { name: /Step 1: ask copy/ });
    fireEvent.keyDown(copy, { key: "ArrowDown", altKey: true });
    expect(screen.getByRole("button", { name: /Step 2: ask copy/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Undo" }));
    expect(screen.getByRole("button", { name: /Step 1: ask copy/ })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("button", { name: /ask ask_1/ }), { key: "Delete" });
    expect(screen.queryByRole("button", { name: /ask ask_1/ })).toBeNull();
    // out reads copy → deleting asks first
    fireEvent.keyDown(screen.getByRole("button", { name: /ask copy/ }), { key: "Delete" });
    expect(screen.getByRole("dialog").textContent).toContain("is read by out");
    fireEvent.click(screen.getByRole("button", { name: "Delete anyway" }));
    await save();
    expect(calls).toEqual([{ method: "POST", url: "/projects/p/scenarios/s/batch", body: { etag: "e0", ops: [{ op: "delete_step", address: ["steps", 0] }] } }]);
  });

  it("409 → ConflictBar; Keep mine → Save asks before overwriting and sends the current etag", async () => {
    await openEditor();
    extra = (_m, u, b) => (u.endsWith("/batch") && b.etag === "e0" ? [409, { error: "changed", etag: "e5" }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: /Step 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "new" } });
    await save();
    expect(screen.getByRole("alert").textContent).toContain("The file changed on disk");
    etag = "e5";
    await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Keep mine" })));
    await save();
    await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Overwrite the version on disk" })));
    expect(calls.map((c) => [c.method, c.body.etag])).toEqual([["POST", "e0"], ["POST", "e5"]]);
    expect(calls[1].body.ops).toEqual([{ op: "update_step", address: ["steps", 0], fields: { ask: { prompt: "new" } } }]);
  });

  it("422 → error on the card and on the field, nothing written, stays Unsaved", async () => {
    await openEditor();
    const err = { message: "s.yaml: step 'copy', ask.prompt: step 'missing' does not exist", file: "scenarios/s.yaml", step: "copy", field: "ask.prompt" };
    extra = (_m, u) => (u.endsWith("/batch") ? [422, { error: "failed validation", errors: [err] }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: /Step 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "{{ steps.missing.text }}" } });
    await save();
    expect(screen.getByText(/failed validation \(1 error\)/)).toBeTruthy();
    expect(screen.getAllByText(/step 'missing' does not exist/).length).toBe(2); // under the card and under the field
    expect(screen.getByRole("combobox", { name: /Prompt/ }).getAttribute("aria-invalid")).toBe("true");
  });

  it("a batch operation error (422 with op) shows on the card of the step the operation targets", async () => {
    await openEditor();
    extra = (_m, u) => (u.endsWith("/batch")
      ? [422, { error: "batch operation 0 cannot be applied", op: 0, errors: [{ message: "ops[0] update_step: step address does not exist", step: "copy", field: "ask.prompt" }] }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: /Step 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "other" } });
    await save();
    expect(screen.getByText(/failed validation \(1 error\)/)).toBeTruthy();
    const card = screen.getByRole("button", { name: /Step 1: ask copy/ }).closest("li")!;
    expect(card.textContent).toContain("ops[0] update_step");
    expect(screen.getByRole("complementary").textContent).toContain("ops[0] update_step");
  });

  it("live validation in Form mode: render 500 ms after a change, error on the card before Save", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await openEditor();
    const err = { message: "step 'missing' does not exist", file: "scenarios/s.yaml", step: "copy", field: "ask.prompt" };
    extra = (_m, u) => (u.endsWith("/render") ? [200, { text, tree: [], errors: [err] }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: /Step 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "{{ steps.missing.text }}" } });
    expect(screen.queryAllByText(/step 'missing' does not exist/).length).toBe(0);
    await act(async () => void (await vi.advanceTimersByTimeAsync(600)));
    expect(screen.getAllByText(/step 'missing' does not exist/).length).toBe(2);
    expect(calls).toEqual([]); // nothing was written
  });

  it("renaming a step that is read asks and saves rename_step with rewritten references", async () => {
    await openEditor("#/p/p/scenarios/s?step=copy");
    const id = await screen.findByRole("textbox", { name: "Name (id)" });
    fireEvent.change(id, { target: { value: "text" } });
    fireEvent.blur(id);
    expect(screen.getByRole("dialog").textContent).toContain("Rewrite references in 1 step?");
    fireEvent.click(screen.getByRole("button", { name: "Rename and rewrite references" }));
    expect(screen.getByRole("button", { name: /Step 1: ask text/ })).toBeTruthy();
    await save();
    expect(calls[0].body.ops).toEqual([
      { op: "rename_step", address: ["steps", 0], new_id: "text", rename_refs: true },
      { op: "update_step", address: ["steps", 1], fields: { output: { text: "{{ steps.text.text }}" } } },
    ]);
  });

  it("the draft survives a page reload (localStorage with the same etag)", async () => {
    await openEditor();
    fireEvent.click(screen.getByRole("button", { name: /Step 1: ask copy/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Prompt/ }), { target: { value: "work in progress" } });
    cleanup();
    await openEditor();
    fireEvent.click(screen.getByRole("button", { name: /Step 1: ask copy/ }));
    expect((screen.getByRole("combobox", { name: /Prompt/ }) as HTMLTextAreaElement).value).toBe("work in progress");
    expect(screen.getByText("Unsaved")).toBeTruthy();
  });
});

describe("YAML mode", () => {
  it("the Back button with an unsaved change shows the same confirmation and restores the hash", async () => {
    const hash = "#/p/p/scenarios/s?step=copy&mode=yaml";
    await openEditor(hash);
    fireEvent.change(screen.getByRole("textbox", { name: "scenarios/s.yaml" }), { target: { value: `${TEXT}# change\n` } });
    expect(screen.getByText("Unsaved")).toBeTruthy();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    await act(async () => {
      location.hash = "#/p/p/agents/publisher";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(confirm).toHaveBeenCalledWith("You have unsaved changes. Leave anyway? Your work in progress stays in this browser.");
    expect(location.hash).toBe(hash);
    expect(screen.getByRole("textbox", { name: "scenarios/s.yaml" })).toBeTruthy();
  });

  it("a syntax error keeps the confirmation dialog; fixing it allows Save via files/", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await openEditor("#/p/p/scenarios/s?step=copy&mode=yaml");
    const area = await screen.findByRole("textbox", { name: "scenarios/s.yaml" });
    extra = (_m, u, b) => (u === "/projects/p/validate" && String(b.text).includes("[")
      ? [200, { errors: [{ message: "line 5: cannot read YAML", file: "scenarios/s.yaml", line: 5 }] }] : undefined);
    fireEvent.change(area, { target: { value: TEXT.replace("  - id: copy", "  - id: [copy") } });
    await act(async () => void (await vi.advanceTimersByTimeAsync(600)));
    const form = screen.getByRole("radio", { name: "Form" });
    expect(form.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(form);
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("radio", { name: /YAML/ }).getAttribute("aria-checked")).toBe("true");
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(area, { target: { value: TEXT.replace("# comment", "# edited") } });
    await act(async () => void (await vi.advanceTimersByTimeAsync(600)));
    expect(form.getAttribute("aria-disabled")).toBeNull();
    extra = (m, u) => (m === "PUT" && u.startsWith("/projects/p/files/") ? [200, { etag: "e1", errors: [] }] : undefined);
    await save();
    expect(calls.filter((c) => c.method === "PUT")).toEqual([
      { method: "PUT", url: "/projects/p/files/scenarios/s.yaml", body: { text: TEXT.replace("# comment", "# edited"), etag: "e0" } },
    ]);
  });
});

describe("starting a run from the GUI", () => {
  it("required inputs and defaults", () => {
    const specs = { topic: { type: "string", required: true }, language: { type: "string", default: "en" }, n: { type: "integer", default: 2 } };
    expect(runInputs(specs, { language: "en", n: 2 })).toEqual({ inputs: { language: "en", n: 2 }, missing: ["topic"] });
    expect(runInputs(specs, { topic: "coffee", language: "", n: 3 })).toEqual({ inputs: { topic: "coffee", n: 3 }, missing: [] });
  });

  it("form: required input, limits before a live run, POST without a callback and navigation to the run", async () => {
    await openEditor();
    extra = (m, u) => (m === "POST" && u === "/projects/p/runs" ? [202, { run_id: "20260926-120000-s-ab12", queue_position: 1 }] : undefined);
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    const panel = screen.getByRole("complementary");
    fireEvent.click(within(panel).getByRole("button", { name: "Start dry run" }));
    expect(within(panel).getByText("Required input.")).toBeTruthy();
    expect(calls).toEqual([]);
    fireEvent.change(within(panel).getByRole("textbox", { name: /topic/ }), { target: { value: "coffee" } });
    await act(async () => void fireEvent.click(within(panel).getByRole("radio", { name: /Live run/ })));
    expect(within(panel).getByText("1.00 USD")).toBeTruthy();
    expect(await within(panel).findByText(/0.42 \/ /)).toBeTruthy();
    await act(async () => void fireEvent.click(within(panel).getByRole("button", { name: "Start live run" })));
    expect(calls).toEqual([{ method: "POST", url: "/projects/p/runs", body: { scenario: "s", inputs: { topic: "coffee" } } }]);
    expect(location.hash).toBe("#/p/p/runs/20260926-120000-s-ab12");
  });
});

describe("agent form", () => {
  it("MCP only for allowed servers; a checked server → max_turns required and in the patch", async () => {
    location.hash = "#/p/p/agents/publisher";
    await act(async () => void render(<App />));
    const ig = await screen.findByRole("checkbox", { name: /instagram/ });
    // EditorBar (G1–G4): one Save in the section header, Rename and Delete (last, in red) in the ⋯ menu
    expect(screen.getAllByRole("heading", { level: 1 }).map((h) => h.textContent)).toEqual(["Agents"]);
    expect(screen.getAllByRole("button", { name: "Save" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Actions for publisher" }));
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Reload", "Rename", "Delete"]);
    expect(screen.getByRole("menuitem", { name: "Delete" }).className).toContain("text-error");
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    const turns = screen.getByRole("spinbutton", { name: /max_turns/ });
    expect(turns.getAttribute("aria-required")).toBe("false");
    fireEvent.click(ig);
    expect(turns.getAttribute("aria-required")).toBe("true");
    expect(screen.getByText("Required: the agent has an MCP server.")).toBeTruthy();
    fireEvent.change(turns, { target: { value: "6" } });
    extra = (m) => (m === "PUT" ? [200, { etag: "a2", errors: [] }] : undefined);
    await save();
    expect(calls).toEqual([{
      method: "PUT", url: "/projects/p/agents/publisher",
      body: { etag: "a1", frontmatter: { mcp: ["instagram"], tools: { instagram: ["publish_media"] }, limits: { max_turns: 6 } } },
    }]);
  });

  // a server without an owner allowlist has nothing to tick: ticking it must not write `tools.<server>: []`
  it.each([["", undefined], ["forecast, alerts, ", ["forecast", "alerts"]]])("an unrestricted server: tool names typed as %j", async (typed, list) => {
    location.hash = "#/p/p/agents/publisher";
    await act(async () => void render(<App />));
    const weather = await screen.findByRole("checkbox", { name: /weather/ });
    expect(weather.closest("label")!.textContent).toContain("not restricted by the owner");
    expect(screen.getByRole("checkbox", { name: /instagram/ }).closest("label")!.textContent).toContain("1 tool");
    fireEvent.click(weather);
    fireEvent.change(screen.getByRole("spinbutton", { name: /max_turns/ }), { target: { value: "4" } });
    const names = screen.getByRole("textbox", { name: /Tools of weather/ }) as HTMLInputElement;
    fireEvent.change(names, { target: { value: "x" } });
    fireEvent.change(names, { target: { value: typed } });
    expect(names.value).toBe(typed);  // the text stays as typed (trailing comma) until the field is left
    extra = (m) => (m === "PUT" ? [200, { etag: "a2", errors: [] }] : undefined);
    await save();
    expect(calls).toEqual([{
      method: "PUT", url: "/projects/p/agents/publisher",
      body: { etag: "a1", frontmatter: { mcp: ["weather"], ...(list && { tools: { weather: list } }), limits: { max_turns: 4 } } },
    }]);
  });
});
