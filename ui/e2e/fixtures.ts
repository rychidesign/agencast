// Shared E2E starting state (user-journeys.md “Shared starting state”): one `agencast serve --fake`
// per Playwright worker with its own port and `AGENCAST_CONFIG_DIR` in tmp, one project per test via
// `POST /projects/new`. Files are checked via fs and the YAML parser from the framework venv (the GUI parses nothing).
import { test as base, expect, type Page } from "@playwright/test";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export { expect };
export const TOKEN = "test-token";
const REPO = path.resolve(import.meta.dirname, "../..");
const VENV = path.join(REPO, "framework/.venv/bin");
export const AGENCAST = process.env.AGENCAST_BIN ?? path.join(VENV, "agencast");
const PORT = Number(process.env.E2E_PORT ?? 18700);

/** Fake provider (fake.py): step id → responses. Steps with different behaviour have different ids. */
export const FAKE = `write: [{text: "Two sentences."}]
slowly: [{text: "Slow answer.", sleep: 4}]
`;

type Json = Record<string, unknown>;

export interface Server {
  url: string;
  port: number;
  tmp: string;
  cfg: string;
  projectsRoot: string;
  fake: string;
  env: NodeJS.ProcessEnv;
  api: <T = Json>(method: string, path: string, body?: unknown) => Promise<{ status: number; body: T }>;
  /** Kills `serve` (SIGKILL, like a crash) and starts it again with the same state. */
  restart: () => Promise<void>;
}

export interface Project {
  name: string;
  root: string;
  wf: string;
  read: (rel: string) => string;
  write: (rel: string, text: string) => void;
  yaml: <T = Json>(rel: string) => T;
  runsDir: string;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** YAML → JSON with the parser from the framework venv (no new dependency in ui/). */
export function readYaml<T = Json>(file: string): T {
  const r = spawnSync(path.join(VENV, "python"), ["-c", "import json,sys,yaml;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))", file], { encoding: "utf8" });
  if (r.status !== 0) throw new Error(r.stderr);
  return JSON.parse(r.stdout) as T;
}

async function startServe(s: Server): Promise<ChildProcess> {
  const log = fs.openSync(path.join(s.tmp, "serve.log"), "a");
  const proc = spawn(AGENCAST, ["serve", "--fake", s.fake, "--host", "127.0.0.1", "--port", String(s.port)],
    { cwd: s.tmp, env: s.env, stdio: ["ignore", log, log] });
  for (let i = 0; i < 100; i++) {
    if (proc.exitCode !== null) break;
    try {
      if ((await s.api("GET", "/projects")).status === 200) return proc;
    } catch { /* not listening yet */ }
    await sleep(100);
  }
  proc.kill("SIGKILL");
  throw new Error(`agencast serve did not start:\n${fs.readFileSync(path.join(s.tmp, "serve.log"), "utf8")}`);
}

export const test = base.extend<{ token: string | null; project: Project }, { server: Server }>({
  server: [async ({}, use, workerInfo) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "agencast-e2e-"));
    const cfg = path.join(tmp, "cfg");
    const projectsRoot = path.join(tmp, "projects");
    fs.mkdirSync(cfg);
    fs.mkdirSync(projectsRoot);
    fs.writeFileSync(path.join(cfg, "projects.yaml"), `projects_root: ${projectsRoot}\nprojects: []\n`);
    const fake = path.join(tmp, "fake.yaml");
    fs.writeFileSync(fake, FAKE);
    const port = PORT + workerInfo.parallelIndex;
    const url = `http://127.0.0.1:${port}`;
    // Hermetic: no values from the developer's environment; the tests use neither callback nor webhook.
    const env: NodeJS.ProcessEnv = {
      PATH: process.env.PATH, HOME: process.env.HOME, LANG: "C.UTF-8", AGENCAST_CONFIG_DIR: cfg, AGENCAST_TOKEN: TOKEN,
      OPENROUTER_API_KEY: "e2e-fake-key",
    };
    const s: Server = {
      url, port, tmp, cfg, projectsRoot, fake, env,
      api: async (method, p, body) => {
        const res = await fetch(url + p, {
          method, headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
        const text = await res.text();
        return { status: res.status, body: text ? JSON.parse(text) : {} };
      },
      restart: async () => {
        proc.kill("SIGKILL");
        await new Promise((r) => proc.once("exit", r));
        proc = await startServe(s);
      },
    };
    let proc = await startServe(s);
    await use(s);
    proc.kill("SIGKILL");
    fs.rmSync(tmp, { recursive: true, force: true });
  }, { scope: "worker" }],

  token: [TOKEN, { option: true }],

  baseURL: async ({ server }, use) => use(server.url),

  page: async ({ page, token, server }, use) => {
    // hermetic: the browser may only reach this worker's `serve`
    await page.route((u) => u.origin !== server.url, (r) => r.abort());
    if (token) await page.addInitScript((tk) => localStorage.getItem("agencast.token") || localStorage.setItem("agencast.token", tk), token);
    await use(page);
  },

  project: async ({ server }, use, testInfo) => {
    const code = testInfo.title.split(" ")[0].toLowerCase().replace(/[^a-z0-9]/g, "");
    const name = `${code}${testInfo.retry ? `-r${testInfo.retry}` : ""}`;
    const r = await server.api<{ root: string }>("POST", "/projects/new", { name });
    expect(r.status, JSON.stringify(r.body)).toBe(201);
    const wf = path.join(r.body.root, "workflows");
    await use({
      name, root: r.body.root, wf, runsDir: path.join(r.body.root, "runs"),
      read: (rel) => fs.readFileSync(path.join(wf, rel), "utf8"),
      write: (rel, text) => fs.writeFileSync(path.join(wf, rel), text),
      yaml: (rel) => readYaml(path.join(wf, rel)),
    });
  },
});

// --- helpers ---------------------------------------------------------------------------------

/** Fixture `slow.yaml`: step `slowly` sleeps 4 s (FAKE). */
export const SLOW = `version: 1
name: slow
description: Slow run for live following
inputs:
  topic: { type: string, default: coffee }
outputs:
  text: { type: string }
steps:
  - id: slowly
    ask:
      agent: writer
      prompt: "Slowly: {{ inputs.topic }}"
  - id: result
    output:
      text: "{{ steps.slowly.text }}"
`;

/** Fixture `failing.yaml`: write → stop (fail) → result. */
export const FAILING = `version: 1
name: failing
description: A run that ends with an error
inputs:
  topic: { type: string, default: coffee }
outputs:
  text: { type: string }
steps:
  - id: write
    ask:
      agent: writer
      prompt: "Write: {{ inputs.topic }}"
  - id: skip
    when: inputs.topic == "never"
    ask:
      agent: writer
      prompt: "This is skipped"
    default: { text: "default" }
  - id: stop
    when: inputs.topic != "never"
    fail: "Stopped on purpose"
  - id: result
    output:
      text: "{{ steps.write.text }} {{ steps.skip.text }}"
`;

/** Starts a scenario via the API and returns the `run_id`. */
export async function startRun(server: Server, project: string, scenario: string, extra: Json = {}): Promise<string> {
  const r = await server.api<{ run_id: string }>("POST", `/projects/${project}/runs`, { scenario, inputs: {}, ...extra });
  expect([200, 202], JSON.stringify(r.body)).toContain(r.status);
  return r.body.run_id;
}

/** Waits until the run reaches one of `states`. */
export async function waitRun(server: Server, project: string, id: string, states: string[], ms = 20_000): Promise<Json> {
  const until = Date.now() + ms;
  for (;;) {
    const r = await server.api<Json>("GET", `/projects/${project}/runs/${id}`);
    if (states.includes(String(r.body.state))) return r.body;
    if (Date.now() > until) throw new Error(`run ${id} is ${r.body.state}, expected ${states}`);
    await sleep(200);
  }
}

/** Tab until `target` has focus (keyboard path without a mouse). */
export async function tabTo(page: Page, target: ReturnType<Page["locator"]>, max = 60, key = "Tab") {
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return;
    await page.keyboard.press(key);
  }
  throw new Error(`focus did not reach the target after ${max}× ${key}`);
}

/** Number of requests whose URL passes `test` during `fn`. */
export async function countRequests(page: Page, test: (url: string, method: string) => boolean, fn: () => Promise<unknown>) {
  let n = 0;
  const on = (r: { url: () => string; method: () => string }) => void (test(r.url(), r.method()) && n++);
  page.on("request", on);
  await fn();
  page.off("request", on);
  return n;
}
