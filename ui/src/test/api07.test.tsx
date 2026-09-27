// Využití API 0.7.0 (ui část 3): `state`, `steps` a panel kroku z API, snímek stromu, karty bez N+1,
// filtr a limit seznamu běhů, sbalení kontejneru, drobečky `call`.
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
/** `url` bez originu → [status, tělo]; nic = 404. */
function serve(route: (url: string) => unknown) {
  fetch = vi.fn((u: string) => {
    const url = u.replace(/^https?:\/\/[^/]+/, "");
    const body = route(url);
    return body === undefined ? json(404, { error: `neznámé ${url}` }) : json(200, body);
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

const RUN_ID = "20260926-123940-ukazka-call-2442";
const baseRun: Run = {
  run_id: RUN_ID, status: "běží", state: "running", scenario: "ukazka-call", fake: true,
  tree: [step(1, "copy", "ask"), step(2, "ton", "call", { call: "kontrola-tonu" }), step(3, "stop", "fail")],
  callees: { "kontrola-tonu": [step(1, "kontrola", "jev"), step(2, "vysledek", "set")] },
  tree_source: "snapshot", files: [],
  steps: [
    rs("copy", "ask", "succeeded", { dir: "steps/01-copy", calls: [{ attempt: 1, alias: "chytry", model: "anthropic/claude-haiku-4.5",
      input_tokens: 100, output_tokens: 20, cost_usd: 0.0001, finish_reason: "stop", structured_output: "native_schema", duration_s: 0 }] }),
    rs("ton", "call", "succeeded", { nn: 2, dir: "steps/02-ton" }),
    rs("ton/kontrola", "jev", "succeeded", { dir: "steps/02-ton/steps/01-kontrola", answers: { on_brand: 0.5 } }),
    rs("ton/vysledek", "set", "succeeded", { nn: 2 }),
    rs("stop", "fail", "failed", { nn: 3, error: { class: "fail", message: "Text neodpovídá značce (on_brand = 0.5)" } }),
  ],
};

describe("detail běhu", () => {
  it("dotazuje se, dokud je running; u interrupted přestane a ukáže štítek", async () => {
    vi.useFakeTimers();
    const steps = [rs("copy", "ask", "running", { started_at: "2026-09-26T12:39:40.986Z" })];
    let run: Run = { ...baseRun, steps };
    serve((url) => (url === `/projects/p/runs/${RUN_ID}` ? run : undefined));
    const runCalls = () => urls().filter((u) => u === `/projects/p/runs/${RUN_ID}`).length;

    await act(async () => render(<RunPage project="p" runId={RUN_ID} />));
    expect(runCalls()).toBe(1);
    await act(async () => void (await vi.advanceTimersByTimeAsync(2000)));
    expect(runCalls()).toBe(2);

    expect(screen.getByRole("button", { name: /^Krok 1: ask copy — běží/ })).toBeTruthy();
    run = { ...baseRun, steps, status: "přerušen", state: "interrupted" };
    await act(async () => void (await vi.advanceTimersByTimeAsync(2000)));
    expect(runCalls()).toBe(3);
    expect(screen.getAllByText("přerušen").length).toBeGreaterThan(0);
    // krok bez konce už nepulzuje jako „běží“
    expect(screen.getByRole("button", { name: /^Krok 1: ask copy — přerušen/ })).toBeTruthy();

    await act(async () => void (await vi.advanceTimersByTimeAsync(20_000)));
    expect(runCalls()).toBe(3);
    // events.jsonl se už nestahuje
    expect(urls().some((u) => u.includes("events.jsonl"))).toBe(false);
  });

  it("karty ze snímku (tree, callees) a údaje kroků ze steps; panel z …/steps/<cesta>", async () => {
    const done: Run = { ...baseRun, status: "failed (fail v stop)", state: "failed" };
    serve((url) => {
      if (url === `/projects/p/runs/${RUN_ID}`) return done;
      if (url === `/projects/p/runs/${RUN_ID}/steps/ton/kontrola`)
        return { ...done.steps![2], events: [], output: { on_brand: 0.5 }, files: ["steps/02-ton/steps/01-kontrola/output.json"] };
    });
    await act(async () => render(<RunPage project="p" runId={RUN_ID} />));
    expect(screen.getByText("falešný běh")).toBeTruthy();
    expect(screen.getByText("chytry → anthropic/claude-haiku-4.5")).toBeTruthy();
    expect(screen.getByText("on_brand = 0,5")).toBeTruthy();
    expect(screen.getByText("Text neodpovídá značce (on_brand = 0.5)")).toBeTruthy();
    // vnořená karta volaného scénáře ze snímku (typ set, ne pseudo-krok ze záznamu)
    expect(screen.getByRole("button", { name: /^Krok 2: set vysledek/ })).toBeTruthy();
    expect(screen.queryByText(/snímek z doby běhu chybí/)).toBeNull();
    expect(urls().some((u) => u.includes("/scenarios/"))).toBe(false);

    await act(async () => fireEvent.click(screen.getByRole("button", { name: /^Krok 1: jev kontrola/ })));
    expect(urls()).toContain(`/projects/p/runs/${RUN_ID}/steps/ton/kontrola`);
    const panel = screen.getByRole("complementary", { name: /1 · jev$/i });
    await act(async () => fireEvent.click(within(panel).getByRole("tab", { name: "Výstup" })));
    expect(within(panel).getByText(/"on_brand": 0.5/)).toBeTruthy();
  });

  it("tree_source current → poznámka, že snímek chybí", async () => {
    serve((url) => (url === `/projects/p/runs/${RUN_ID}` ? { ...baseRun, state: "succeeded", tree_source: "current", callees: {} } : undefined));
    await act(async () => render(<RunPage project="p" runId={RUN_ID} />));
    expect(screen.getByText(/snímek z doby běhu chybí/)).toBeTruthy();
  });
});

describe("karty bez N+1", () => {
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

  it("záložka Scénáře: typy a poslední běh z GET /projects/<p>, žádný další dotaz", async () => {
    serve(() => undefined);
    await act(async () => render(<ScenariosTab project={project} onChanged={() => {}} />));
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getAllByText("bez běhů").length).toBe(2); // čip i patička karty b
    expect(screen.getByText("chyba", { selector: ".sr-only", exact: false })).toBeTruthy();
  });

  it("projekty: počty, útrata i důvod nedostupnosti z registru bez dotazů na karty", async () => {
    serve((url) => {
      if (url === "/projects") return {
        registry: "/home/x/.config/agencast/projects.yaml",
        projects: [
          { name: "p", root: "/r", available: true, counts: { scenarios: 2, agents: 3 }, spend_today_usd: 0, last_run: { run_id: "20260926-091502-a-3c1f", state: "running", started_at: "2026-09-26T09:15:02.000Z", finished_at: null, cost_usd: null } },
          { name: "q", root: "/q", available: false, counts: { scenarios: 0, agents: 0 }, spend_today_usd: 0, reason: "chybí /q/workflows/config.yaml" },
        ],
      };
      if (url === "/projects/p") return project;
      if (url === "/projects/p/spend") return { day: "x", total_usd: 0, runs: [] };
    });
    await act(async () => render(<ProjectsPage />));
    expect(screen.getByText("Registr /home/x/.config/agencast/projects.yaml")).toBeTruthy();
    expect(screen.getByText("chybí /q/workflows/config.yaml")).toBeTruthy();
    expect(screen.getByText("běží", { selector: ".sr-only", exact: false })).toBeTruthy();
    expect(urls()).toEqual(["/projects"]);
  });
});

describe("seznam běhů", () => {
  const item = (i: number, extra: Partial<RunListItem> = {}): RunListItem => ({
    run_id: `20260926-0915${String(i).padStart(2, "0")}-ig-post-3c1f`, status: "succeeded", state: "succeeded", scenario: "ig-post", ...extra,
  });

  it("scénář jde do ?scenario=, limit a Načíst další; fronta, falešný běh, přerušený", async () => {
    const requests: string[] = [];
    serve((url) => {
      if (url.startsWith("/projects/p/runs?")) {
        requests.push(url);
        const first = Array.from({ length: RUNS_PAGE }, (_, i) => item(RUNS_PAGE - i, i === 0 ? { state: "queued", status: "queued", queue_position: 2 }
          : i === 1 ? { state: "interrupted", status: "přerušen" } : i === 2 ? { fake: true } : {}));
        return new URLSearchParams(url.split("?")[1]).has("before")
          ? { runs: [item(0)] }
          : { runs: first, next_before: first.at(-1)!.run_id };
      }
      if (url === "/projects/p") return { limits: {}, scenarios: [{ name: "ig-post" }, { name: "jiny" }] };
      if (url === "/projects/p/spend") return { day: "x", total_usd: 0, runs: [] };
    });
    location.hash = "#/p/p/behy?scenar=ig-post";
    await act(async () => render(<RunsTab project="p" />));
    expect(urls()).toContain(`/projects/p/runs?scenario=ig-post&limit=${RUNS_PAGE}`);
    expect(screen.getByText("ve frontě (2.)")).toBeTruthy();
    expect(screen.getAllByText("přerušen").length).toBeGreaterThan(0);
    expect(screen.getByText("falešný běh")).toBeTruthy();
    expect(screen.getByRole("option", { name: "jiny" })).toBeTruthy();

    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Načíst další" })));
    expect(requests).toEqual([
      `/projects/p/runs?scenario=ig-post&limit=${RUNS_PAGE}`,
      `/projects/p/runs?scenario=ig-post&limit=${RUNS_PAGE}&before=${item(1).run_id}`,
    ]);
    expect(screen.getAllByRole("row").length).toBe(RUNS_PAGE + 2);

    // stav filtruje klient
    await act(async () => {
      location.hash = "#/p/p/behy?scenar=ig-post&stav=interrupted";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(screen.getAllByRole("row").length).toBe(2); // hlavička + přerušený
  });
});

describe("kontejnery a call v editoru", () => {
  const ctx: ListCtx = { project: "p", onSelect: () => {}, errors: new Map(), scenario: "ig-post", trail: "" };

  it("sbalení kontejneru schová vnitřek a ukáže počet kroků", () => {
    const par = step(1, "obe", "parallel", { branches: { a: [step(1, "x", "ask")], b: [step(1, "y", "ask"), step(2, "z", "set")] } });
    render(<StepList steps={[par]} ctx={ctx} />);
    expect(screen.getByRole("button", { name: /: ask y/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sbalit obe" }));
    expect(screen.queryByRole("button", { name: /: ask y/ })).toBeNull();
    expect(screen.getByText("3 kroky")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Rozbalit obe" }));
    expect(screen.getByRole("button", { name: /: ask y/ })).toBeTruthy();
  });

  it("otevřít u call nese cestu; drobečky ig-post › navrh › ig-text vedou zpět na kartu", () => {
    const call = step(1, "navrh", "call", { call: "ig-text" });
    render(<StepList steps={[call]} ctx={ctx} />);
    expect(screen.getByRole("link", { name: /ig-text otevřít/ }).getAttribute("href")).toBe("#/p/p/scenare/ig-text?z=ig-post%3Anavrh");
    cleanup();

    render(<Trail project="p" trail="ig-post:navrh,ig-text:x" />);
    const nav = screen.getByRole("navigation", { name: "Cesta přes call" });
    expect(nav.textContent).toBe("ig-post › navrh › ig-text › x › ");
    expect(within(nav).getByRole("link", { name: "ig-post" }).getAttribute("href")).toBe("#/p/p/scenare/ig-post?krok=navrh");
    expect(within(nav).getByRole("link", { name: "ig-text" }).getAttribute("href")).toBe("#/p/p/scenare/ig-text?krok=x&z=ig-post%3Anavrh");
  });
});

describe("rozbitý config", () => {
  const dup = { message: "config.yaml, řádek 20: duplicitní klíč 'runs_dir' (poprvé na řádku 18)", file: "config.yaml", line: 20 };
  const broken = (url: string, init?: RequestInit) => {
    if (url === "/projects/p") return json(422, { error: "projekt 'p' neprošel kontrolou", details: [dup.message], errors: [dup] });
    if (url === "/projects/p/files/config.yaml") return json(200, { path: "config.yaml", etag: "c", text: "a: 1\n", errors: [dup] });
    if (url === "/projects/p/validate" && init?.method === "POST") return json(200, { errors: [dup] });
    if (url.startsWith("/projects/p/runs?")) return json(200, { runs: [{ run_id: RUN_ID, status: "succeeded", state: "succeeded", scenario: "ukazka-call" }] });
    if (url === "/projects/p/spend") return json(200, { day: "x", total_usd: 0, runs: [] });
    return json(404, { error: "není" });
  };
  const stub = () => vi.stubGlobal("fetch", vi.fn((u: string, init?: RequestInit) => broken(u.replace(/^https?:\/\/[^/]+/, ""), init)));

  it("YAML režim Configu ukáže chybu s řádkem; záložka Běhy funguje", async () => {
    stub();
    location.hash = "#/p/p/config";
    await act(async () => render(<App />));
    expect(await screen.findByText(/řádek 20 · config.yaml, řádek 20: duplicitní klíč/)).toBeTruthy();
    cleanup();

    location.hash = "#/p/p/behy";
    await act(async () => render(<App />));
    expect(await screen.findByTestId(`run-row-${RUN_ID}`)).toBeTruthy(); // run_id jen v `title` řádku (G9)
  });
});
