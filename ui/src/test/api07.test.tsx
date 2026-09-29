// Using API 0.7.0 (ui part 3): `state`, `steps` and the step panel from the API, tree snapshot, cards without N+1,
// run list filter and limit, collapsing a container, `call` breadcrumbs.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveToken } from "../api";
import { App } from "../App";
import { StepList, type ListCtx } from "../components/StepCards";
import { ProjectsPage } from "../pages/Projects";
import { RunPage } from "../pages/Run";
import { RUNS_PAGE, RunsTab } from "../pages/Runs";
import { ScenariosTab } from "../pages/Scenarios";
import { Trail } from "../pages/Scenario";
import type { Project, Run, RunListItem, RunStep, Step } from "../types";

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

let fetch: ReturnType<typeof vi.fn>;
/** `url` without the origin → [status, body]; nothing = 404. */
function serve(route: (url: string) => unknown) {
  fetch = vi.fn((u: string) => {
    const url = u.replace(/^https?:\/\/[^/]+/, "");
    const body = route(url);
    return body === undefined ? json(404, { error: `unknown ${url}` }) : json(200, body);
  });
  vi.stubGlobal("fetch", fetch);
}
const urls = () => fetch.mock.calls.map(([u]) => String(u).replace(/^https?:\/\/[^/]+/, ""));

beforeEach(() => {
  location.hash = "#/";
  localStorage.clear();
  saveToken("t");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const step = (nn: number, id: string, type: Step["type"], extra: Partial<Step> = {}): Step => ({
  nn, address: ["steps", nn - 1], id, type, when: null, fields: {}, refs: [], ...extra,
});
const rs = (step: string, kind: RunStep["kind"], status: RunStep["status"], extra: Partial<RunStep> = {}): RunStep => ({
  step, kind, status, nn: 1, dir: null, error: null, continued: false, default_used: false, calls: [], ...extra,
});

const RUN_ID = "20260926-123940-demo-call-2442";
const baseRun: Run = {
  run_id: RUN_ID, status: "running", state: "running", scenario: "demo-call", fake: true,
  tree: [step(1, "copy", "ask"), step(2, "tone", "call", { call: "tone-check" }), step(3, "stop", "fail")],
  callees: { "tone-check": [step(1, "check", "jev"), step(2, "result", "set")] },
  tree_source: "snapshot", files: [],
  steps: [
    rs("copy", "ask", "succeeded", { dir: "steps/01-copy", calls: [{ attempt: 1, alias: "smart", model: "anthropic/claude-haiku-4.5",
      input_tokens: 100, output_tokens: 20, cost_usd: 0.0001, finish_reason: "stop", structured_output: "native_schema", duration_s: 0 }] }),
    rs("tone", "call", "succeeded", { nn: 2, dir: "steps/02-tone" }),
    rs("tone/check", "jev", "succeeded", { dir: "steps/02-tone/steps/01-check", answers: { on_brand: 0.5 } }),
    rs("tone/result", "set", "succeeded", { nn: 2 }),
    rs("stop", "fail", "failed", { nn: 3, error: { class: "fail", message: "Text is off-brand (on_brand = 0.5)" } }),
  ],
};

describe("run detail", () => {
  it("polls while running; stops at interrupted and shows the label", async () => {
    vi.useFakeTimers();
    const steps = [rs("copy", "ask", "running", { started_at: "2026-09-26T12:39:40.986Z" })];
    let run: Run = { ...baseRun, steps };
    serve((url) => (url === `/projects/p/runs/${RUN_ID}` ? run : undefined));
    const runCalls = () => urls().filter((u) => u === `/projects/p/runs/${RUN_ID}`).length;

    await act(async () => render(<RunPage project="p" runId={RUN_ID} />));
    expect(runCalls()).toBe(1);
    await act(async () => void (await vi.advanceTimersByTimeAsync(2000)));
    expect(runCalls()).toBe(2);

    expect(screen.getByRole("button", { name: /^Step 1: ask copy — running/ })).toBeTruthy();
    run = { ...baseRun, steps, status: "interrupted", state: "interrupted" };
    await act(async () => void (await vi.advanceTimersByTimeAsync(2000)));
    expect(runCalls()).toBe(3);
    expect(screen.getAllByText("interrupted").length).toBeGreaterThan(0);
    // a step without an end no longer pulses as “running”
    expect(screen.getByRole("button", { name: /^Step 1: ask copy — interrupted/ })).toBeTruthy();

    await act(async () => void (await vi.advanceTimersByTimeAsync(20_000)));
    expect(runCalls()).toBe(3);
    // events.jsonl is no longer fetched
    expect(urls().some((u) => u.includes("events.jsonl"))).toBe(false);
  });

  it("cards from the snapshot (tree, callees) and step data from steps; panel from …/steps/<path>", async () => {
    const done: Run = { ...baseRun, status: "failed (fail in stop)", state: "failed" };
    serve((url) => {
      if (url === `/projects/p/runs/${RUN_ID}`) return done;
      if (url === `/projects/p/runs/${RUN_ID}/steps/tone/check`)
        return { ...done.steps![2], events: [], output: { on_brand: 0.5 }, files: ["steps/02-tone/steps/01-check/output.json"] };
    });
    await act(async () => render(<RunPage project="p" runId={RUN_ID} />));
    expect(screen.getByText("fake run")).toBeTruthy();
    expect(screen.getByText("smart → anthropic/claude-haiku-4.5")).toBeTruthy();
    expect(screen.getByText("on_brand = 0.5")).toBeTruthy();
    expect(screen.getByText("Text is off-brand (on_brand = 0.5)")).toBeTruthy();
    // nested card of the called scenario from the snapshot (type set, not a pseudo-step from the record)
    expect(screen.getByRole("button", { name: /^Step 2: set result/ })).toBeTruthy();
    expect(screen.queryByText(/snapshot from the time of the run is missing/)).toBeNull();
    expect(urls().some((u) => u.includes("/scenarios/"))).toBe(false);

    await act(async () => fireEvent.click(screen.getByRole("button", { name: /^Step 1: jev check/ })));
    expect(urls()).toContain(`/projects/p/runs/${RUN_ID}/steps/tone/check`);
    const panel = screen.getByRole("complementary", { name: /1 · jev$/i });
    await act(async () => fireEvent.click(within(panel).getByRole("tab", { name: "Output" })));
    expect(within(panel).getByText(/"on_brand": 0.5/)).toBeTruthy();
  });

  it("tree_source current → note that the snapshot is missing", async () => {
    serve((url) => (url === `/projects/p/runs/${RUN_ID}` ? { ...baseRun, state: "succeeded", tree_source: "current", callees: {} } : undefined));
    await act(async () => render(<RunPage project="p" runId={RUN_ID} />));
    expect(screen.getByText(/snapshot from the time of the run is missing/)).toBeTruthy();
  });
});

describe("cards without N+1", () => {
  const project = {
    name: "p", root: "/r", limits: {}, agents: [], skills: [], errors: [],
    links: { scenario_agent: [], scenario_step_agent: [], scenario_scenario: [], agent_skill: [], agent_server: [] },
    scenarios: [
      { name: "a", etag: "", description: "A", inputs: null, outputs: null, callable: false, steps_count: 2, errors: [],
        types: ["ask", "output"], last_run: { run_id: "20260926-091502-a-3c1f", state: "failed", started_at: "2026-09-26T09:15:02.000Z", finished_at: "2026-09-26T09:15:20.000Z", cost_usd: 0 } },
      { name: "b", etag: "", description: "B", inputs: null, outputs: null, callable: false, steps_count: 1, errors: [],
        types: ["jev"], last_run: null },
    ],
  } as unknown as Project;

  it("Scenarios tab: types and last run from GET /projects/<p>, no further request", async () => {
    serve(() => undefined);
    await act(async () => render(<ScenariosTab project={project} header={() => null} onChanged={() => {}} />));
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getAllByText("no runs").length).toBe(1); // the only time chip, on card b
    expect(screen.getByText("failed", { selector: ".sr-only", exact: false })).toBeTruthy();
  });

  it("projects: counts, spend and the unavailability reason from the registry, no per-card requests", async () => {
    serve((url) => {
      if (url === "/projects") return {
        registry: "/home/x/.config/agencast/projects.yaml",
        projects: [
          { name: "p", root: "/r", available: true, counts: { scenarios: 2, agents: 3 }, spend_today_usd: 0, last_run: { run_id: "20260926-091502-a-3c1f", state: "running", started_at: "2026-09-26T09:15:02.000Z", finished_at: null, cost_usd: null } },
          { name: "q", root: "/q", available: false, counts: { scenarios: 0, agents: 0 }, spend_today_usd: 0, reason: "missing /q/workflows/config.yaml" },
        ],
      };
      if (url === "/projects/p") return project;
      if (url === "/projects/p/spend") return { day: "x", total_usd: 0, runs: [] };
    });
    await act(async () => render(<ProjectsPage />));
    expect(screen.getByText("/home/x/.config/agencast/projects.yaml")).toBeTruthy();
    expect(screen.getByText("missing /q/workflows/config.yaml")).toBeTruthy();
    expect(screen.getByText("running", { selector: ".sr-only", exact: false })).toBeTruthy();
    expect(urls()).toEqual(["/projects"]);
  });
});

describe("run list", () => {
  const item = (i: number, extra: Partial<RunListItem> = {}): RunListItem => ({
    run_id: `20260926-0915${String(i).padStart(2, "0")}-ig-post-3c1f`, status: "succeeded", state: "succeeded", scenario: "ig-post", ...extra,
  });

  it("scenario goes to ?scenario=, limit and Load more; queue, fake run, interrupted", async () => {
    const requests: string[] = [];
    serve((url) => {
      if (url.startsWith("/projects/p/runs?")) {
        requests.push(url);
        const first = Array.from({ length: RUNS_PAGE }, (_, i) => item(RUNS_PAGE - i, i === 0 ? { state: "queued", status: "queued", queue_position: 2 }
          : i === 1 ? { state: "interrupted", status: "interrupted" } : i === 2 ? { fake: true } : {}));
        return new URLSearchParams(url.split("?")[1]).has("before")
          ? { runs: [item(0)] }
          : { runs: first, next_before: first.at(-1)!.run_id };
      }
      if (url === "/projects/p") return { limits: {}, scenarios: [{ name: "ig-post" }, { name: "other" }] };
      if (url === "/projects/p/spend") return { day: "x", total_usd: 0, runs: [] };
    });
    location.hash = "#/p/p/runs?scenario=ig-post";
    await act(async () => render(<RunsTab project="p" header={(x) => x?.meta} />));
    expect(urls()).toContain(`/projects/p/runs?scenario=ig-post&limit=${RUNS_PAGE}`);
    expect(screen.getByText("queued (#2)")).toBeTruthy();
    expect(screen.getAllByText("interrupted").length).toBeGreaterThan(0);
    expect(screen.getByText(/ · fake run$/)).toBeTruthy();
    expect(screen.getByRole("option", { name: "other" })).toBeTruthy();

    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Load more" })));
    expect(requests).toEqual([
      `/projects/p/runs?scenario=ig-post&limit=${RUNS_PAGE}`,
      `/projects/p/runs?scenario=ig-post&limit=${RUNS_PAGE}&before=${item(1).run_id}`,
    ]);
    expect(screen.getAllByRole("row").length).toBe(RUNS_PAGE + 2);

    // the client filters by status
    await act(async () => {
      location.hash = "#/p/p/runs?scenario=ig-post&status=interrupted";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(screen.getAllByRole("row").length).toBe(2); // header + interrupted
  });
});

describe("containers and call in the editor", () => {
  const ctx: ListCtx = { project: "p", onSelect: () => {}, errors: new Map(), scenario: "ig-post", trail: "" };

  it("collapsing a container hides its contents and shows the step count", () => {
    const par = step(1, "both", "parallel", { branches: { a: [step(1, "x", "ask")], b: [step(1, "y", "ask"), step(2, "z", "set")] } });
    render(<StepList steps={[par]} ctx={ctx} />);
    expect(screen.getByRole("button", { name: /: ask y/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Collapse both" }));
    expect(screen.queryByRole("button", { name: /: ask y/ })).toBeNull();
    expect(screen.getByText("3 steps")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Expand both" }));
    expect(screen.getByRole("button", { name: /: ask y/ })).toBeTruthy();
  });

  it("open on a call carries the path; breadcrumbs ig-post › draft › ig-text lead back to the card", () => {
    const call = step(1, "draft", "call", { call: "ig-text" });
    render(<StepList steps={[call]} ctx={ctx} />);
    expect(screen.getByRole("link", { name: /ig-text open/ }).getAttribute("href")).toBe("#/p/p/scenarios/ig-text?from=ig-post%3Adraft");
    cleanup();

    render(<Trail project="p" trail="ig-post:draft,ig-text:x" />);
    const nav = screen.getByRole("navigation", { name: "Call path" });
    expect(nav.textContent).toBe("ig-post › draft › ig-text › x › ");
    expect(within(nav).getByRole("link", { name: "ig-post" }).getAttribute("href")).toBe("#/p/p/scenarios/ig-post?step=draft");
    expect(within(nav).getByRole("link", { name: "ig-text" }).getAttribute("href")).toBe("#/p/p/scenarios/ig-text?step=x&from=ig-post%3Adraft");
  });
});

describe("broken config", () => {
  const dup = { message: "config.yaml, line 20: duplicate key 'runs_dir' (first on line 18)", file: "config.yaml", line: 20 };
  const broken = (url: string, init?: RequestInit) => {
    if (url === "/projects/p") return json(422, { error: "project 'p' failed validation", details: [dup.message], errors: [dup] });
    if (url === "/projects/p/files/config.yaml") return json(200, { path: "config.yaml", etag: "c", text: "a: 1\n", errors: [dup] });
    if (url === "/projects/p/validate" && init?.method === "POST") return json(200, { errors: [dup] });
    if (url.startsWith("/projects/p/runs?")) return json(200, { runs: [{ run_id: RUN_ID, status: "succeeded", state: "succeeded", scenario: "demo-call" }] });
    if (url === "/projects/p/spend") return json(200, { day: "x", total_usd: 0, runs: [] });
    return json(404, { error: "not found" });
  };
  const stub = () => vi.stubGlobal("fetch", vi.fn((u: string, init?: RequestInit) => broken(u.replace(/^https?:\/\/[^/]+/, ""), init)));

  it("Config YAML mode shows the error with its line; the Runs tab works", async () => {
    stub();
    location.hash = "#/p/p/config";
    await act(async () => render(<App />));
    expect(await screen.findByText(/line 20 · config.yaml, line 20: duplicate key/)).toBeTruthy();
    cleanup();

    location.hash = "#/p/p/runs";
    await act(async () => render(<App />));
    expect(await screen.findByTestId(`run-row-${RUN_ID}`)).toBeTruthy(); // run_id only in the row `title` (G9)
  });
});
