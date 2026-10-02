// MCP controls: the task step narrows the agent's servers and tools (StepPanel); the Config cards describe a server and are
// read-only (mcp.yaml is the owner's file on the server); the notice of an untrusted project; tool calls in the run viewer.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import { PageHeader } from "../components/PageHeader";
import { FilesTab } from "../components/RunFiles";
import { RunPanel } from "../components/RunPanel";
import { RunStepPanel } from "../components/RunStepPanel";
import { StepPanel } from "../components/StepPanel";
import type { WStep } from "../edit";
import { ConfigTab } from "../pages/Config";
import type { Project } from "../types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const project: Project = {
  name: "p", root: "/tmp/p", models: { smart: "anthropic/claude-haiku-4.5" }, limits: {}, scenarios: [], skills: [],
  agents: [{ name: "tester", etag: "a0", description: "Tests", model: "smart", model_id: null, skills: [], errors: [],
    mcp: ["testkit", "weather"], tools: { testkit: ["red_pixel", "broken"], weather: ["forecast"] } }],
  mcp_servers: [
    { name: "testkit", type: "stdio", transport: "stdio", description: "Test server", agents: ["tester"], tools: ["red_pixel", "broken"], scenarios: null, env_missing: [] },
    { name: "weather", type: "http", transport: "sse", description: "Forecasts", agents: ["tester"], tools: null, scenarios: null, env_missing: ["WEATHER_TOKEN"] },
  ],
  links: { scenario_agent: [], scenario_step_agent: [], scenario_scenario: [], agent_skill: [], agent_server: [] },
  env: { WEATHER_TOKEN: false }, errors: [],
};

/** The panel of one task step; `task()` = the step body after the clicks so far. */
function taskPanel(extra: Record<string, unknown> = {}) {
  let step: WStep = { uid: "probe", nn: 1, address: ["steps", 0], id: "probe", type: "task", when: null,
    fields: { task: { agent: "tester", prompt: "x", ...extra } }, refs: [] };
  const view = () => (
    <StepPanel step={step} steps={[step]} header={{ description: "", callable: false, inputs: null, outputs: null }} project={project}
      scenario="s" errors={[]} onClose={vi.fn()} onSelect={vi.fn()}
      edit={{ change: (fn) => (step = fn(step), rerender(view())), retype: vi.fn(), remove: vi.fn(), rename: vi.fn() }} />
  );
  const { rerender } = render(view());
  const box = (name: string | RegExp, server?: string) =>
    within(server ? screen.getByRole("group", { name: `Tools of ${server}` }) : screen.getByRole("group", { name: "MCP servers" }))
      .getByRole("checkbox", { name }) as HTMLInputElement;
  return { box, task: () => step.fields.task };
}

it("task step: without mcp/tools everything the agent has is ticked; unticking narrows, a full selection is not written", () => {
  const { box, task } = taskPanel();
  expect(["testkit", "weather"].map((s) => box(s).checked)).toEqual([true, true]);
  expect([box("red_pixel", "testkit"), box("broken", "testkit"), box("forecast", "weather")].map((b) => b.checked)).toEqual([true, true, true]);

  fireEvent.click(box("broken", "testkit"));
  expect(task()).toEqual({ agent: "tester", prompt: "x", tools: { testkit: ["red_pixel"] } });
  expect(box("red_pixel", "testkit").disabled).toBe(true);  // no tool left would mean "all of the agent's tools"
  fireEvent.click(box("weather"));
  expect(task()).toEqual({ agent: "tester", prompt: "x", mcp: ["testkit"], tools: { testkit: ["red_pixel"] } });
  fireEvent.click(box("testkit"));  // the last server: an empty list, not "all servers"; its narrowed tools go with it
  expect(task()).toEqual({ agent: "tester", prompt: "x", mcp: [] });
  fireEvent.click(box("weather"));
  fireEvent.click(box("testkit"));
  expect(task()).toEqual({ agent: "tester", prompt: "x" });
});

it("task step: names the agent does not have stay visible and can be removed", () => {
  const { box, task } = taskPanel({ mcp: ["testkit", "ghost"], tools: { testkit: ["red_pixel", "typo"] } });
  expect([box(/ghost/).checked, box(/typo/, "testkit").checked, box("broken", "testkit").checked, box("weather").checked]).toEqual([true, true, false, false]);
  expect(box(/typo/, "testkit").parentElement!.textContent).toContain("(not allowed by the agent)");
  fireEvent.click(box(/typo/, "testkit"));
  fireEvent.click(box(/ghost/));
  expect(task()).toEqual({ agent: "tester", prompt: "x", mcp: ["testkit"], tools: { testkit: ["red_pixel"] } });
});

it("task step: a lone tool the agent does not have is not locked as the last one", () => {
  const { box, task } = taskPanel({ tools: { testkit: ["ghost"] } });
  expect([box(/ghost/, "testkit").checked, box(/ghost/, "testkit").disabled]).toEqual([true, false]);
  fireEvent.click(box(/ghost/, "testkit"));  // back to the agent's tools
  expect(task()).toEqual({ agent: "tester", prompt: "x" });
});

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

/** `fetch` of a server that knows config.yaml and, like the real one since 0.18.0, answers 404 for mcp.yaml; returns the requested paths. */
function stubServer(routes: Record<string, unknown> = {}) {
  const urls: string[] = [];
  saveToken("t");
  vi.stubGlobal("fetch", vi.fn((u: string) => {
    const url = u.replace(/^https?:\/\/[^/]+/, "");
    urls.push(url);
    if (url === "/projects/p/files/config.yaml") return json(200, { path: "config.yaml", etag: "c1", text: "version: 1\n", data: { version: 1 }, errors: [] });
    return url in routes ? json(200, routes[url]) : json(404, { error: `not found ${url}` });
  }));
  return urls;
}

const config = (p: Project) => act(async () => render(<ConfigTab name="p" project={p} header={(x) => <PageHeader title="Config" {...x} />} />));

it("Config: a server card shows the description, the real transport, unrestricted tools and a missing variable", async () => {
  stubServer();
  await config(project);
  const card = (await screen.findByText("Forecasts")).closest("li")!;
  expect(card.textContent).toContain("sse");
  expect(card.textContent).toContain("not restricted by the owner");
  expect(card.textContent).toContain("WEATHER_TOKEN");
  expect(within(card).getByText("missing on the server")).toBeTruthy();
  const local = screen.getByText("Test server").closest("li")!;
  expect(local.textContent).toContain("red_pixel, broken");
  expect(local.textContent).not.toContain("missing on the server");
});

it("Config: MCP servers are read-only in both modes — mcp.yaml is never requested or offered for editing", async () => {
  const urls = stubServer();
  await config({ ...project, errors: [{ file: "mcp.yaml", message: "mcp.yaml: servers.weather.url: is required" }] });
  const owner = /set up by the project owner in workflows\/mcp\.yaml on the server/;
  await screen.findByText("Forecasts");
  expect(screen.getAllByText(owner)).toHaveLength(1);
  expect(screen.getByText("mcp.yaml: servers.weather.url: is required")).toBeTruthy();  // the file's errors, from the project

  await act(async () => fireEvent.click(screen.getByRole("radio", { name: "YAML" })));
  expect(await screen.findByRole("textbox", { name: "config.yaml" })).toBeTruthy();
  expect(screen.getAllByRole("textbox")).toHaveLength(1);  // config.yaml as text, no second block for mcp.yaml
  expect(screen.getByText("Forecasts")).toBeTruthy();       // the same cards below the text
  expect(screen.getAllByText(owner)).toHaveLength(1);
  expect(screen.queryByText(/YAML mode/)).toBeNull();
  expect(urls.length).toBeGreaterThan(0);
  expect(urls.filter((u) => u.includes("mcp.yaml"))).toEqual([]);
});

it("an untrusted project: Config names the terminal command where there are servers, and offers nothing that changes trust", async () => {
  stubServer();
  await config({ ...project, trusted: false });
  const notice = await screen.findByTestId("untrusted-notice");
  expect(notice.textContent).toContain("agencast projects trust p");
  expect(within(notice).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["Copy command"]);
  cleanup();

  for (const p of [{ ...project, trusted: true }, project, { ...project, trusted: false, mcp_servers: [] }]) {
    await config(p);  // trusted, an older server without the field, and untrusted without servers (every GUI-created project)
    await screen.findByText("MCP servers");
    expect(screen.queryByTestId("untrusted-notice")).toBeNull();
    cleanup();
  }
});

it("an untrusted project: the run form says why a scenario with MCP servers will not start", () => {
  stubServer();
  const blocked = { file: "scenarios/s.yaml", message: "s.yaml: MCP servers (testkit) are disabled — project 'p' (/srv/p) was registered through the API and is not "
    + "trusted to run them (trusted: false in the project registry). The project owner allows them in a terminal: agencast projects trust p" };
  const panel = (errors: { message: string }[]) =>
    render(<RunPanel project={{ ...project, trusted: false }} scenario="s" inputs={null} errors={errors} dirty={false} onClose={vi.fn()} />);
  panel([blocked]);
  const notice = screen.getByTestId("untrusted-notice");
  expect(notice.textContent).toMatch(/neither a run nor a dry run will start.*agencast projects trust p/);
  expect(within(notice).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["Copy command"]);
  cleanup();
  panel([{ message: "s.yaml: steps[0]: agent 'ghost' does not exist" }]);  // a scenario without MCP servers runs as before
  expect(screen.queryByTestId("untrusted-notice")).toBeNull();
});

it("run viewer Tools: a call that did not return shows its error; the server log is linked before the file exists", async () => {
  const call = (n: number, extra: Record<string, unknown>) =>
    ({ ts: "2026-10-01T10:00:00Z", type: "tool_call", step: "probe", turn: n, duration_s: 1, call_file: `steps/01-probe/calls/0${n}.tool.json`, ...extra });
  stubServer({ "/projects/p/runs/r1/steps/probe": {
    step: "probe", kind: "task", status: "failed", output: null, files: [],
    events: [call(1, { server: "testkit", tool: "red_pixel", is_error: false }),
      call(2, { server: "_skills", tool: "load_skill", is_error: false }),
      call(3, { server: "testkit", tool: "broken", is_error: true, error: "tool testkit.broken did not respond within 30 s (may have run)" })],
  } });
  const log = "mcp/testkit.stderr.log";
  const tools = async (runFiles: string[], live: boolean) => {
    cleanup();
    await act(async () => render(<RunStepPanel project="p" runId="r1" path="probe" kind="task" rs={{ step: "probe", kind: "task", status: "failed" }}
      runFiles={runFiles} live={live} onClose={vi.fn()} />));
    fireEvent.click(await screen.findByRole("tab", { name: "Tools" }));
    return within(screen.getByRole("tabpanel"));
  };

  let panel = await tools([], true);  // the server is still running: its log is not in the run yet
  expect(panel.getByText(/did not respond within 30 s \(may have run\)/).closest("li")!.className).toContain("bg-error/10");
  expect(panel.queryByText("tool returned an error")).toBeNull();
  expect(panel.getAllByRole("button", { name: /stderr\.log/ })).toHaveLength(1);  // one per server, none for skills
  fireEvent.click(panel.getByRole("button", { name: log }));
  expect(decodeURIComponent(location.hash)).toContain(`file=${log}`);

  panel = await tools([], false);  // the run ended without a log (a remote server): no dead link
  expect(panel.queryByRole("button", { name: log })).toBeNull();
  panel = await tools([log], false);
  expect(panel.getByRole("button", { name: log })).toBeTruthy();

  // Files with a log that is not there yet: a sentence, and no request that would end with 404
  cleanup();
  const urls = stubServer();
  render(<FilesTab project="p" runId="r1" files={["events.jsonl"]} current={log} />);
  expect(screen.getByText(/written when the server stops/)).toBeTruthy();
  expect(urls).toEqual([]);
});
