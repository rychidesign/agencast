// Společný výchozí stav E2E (uzivatelske-cesty.md „Společný výchozí stav“): jeden `agencast serve --fake`
// na Playwright worker s vlastním portem a `AGENCAST_CONFIG_DIR` v tmp, projekt na test přes
// `POST /projects/new`. Soubory se ověřují přes fs a YAML parser z venv frameworku (GUI nic neparsuje).
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

/** Falešný poskytovatel (fake.py): id kroku → odpovědi. Kroky s jiným chováním mají jiné id. */
export const FAKE = `napis: [{text: "Dvě věty."}]
pomalu: [{text: "Pomalá odpověď.", sleep: 4}]
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
  /** Zabije `serve` (SIGKILL, jako pád) a spustí ho znovu se stejným stavem. */
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

/** YAML → JSON parserem z venv frameworku (bez nové závislosti v ui/). */
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
    } catch { /* ještě neposlouchá */ }
    await sleep(100);
  }
  proc.kill("SIGKILL");
  throw new Error(`agencast serve nenaběhl:\n${fs.readFileSync(path.join(s.tmp, "serve.log"), "utf8")}`);
}

export const test = base.extend<{ token: string | null; project: Project }, { server: Server }>({
  server: [async ({}, use, workerInfo) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "agencast-e2e-"));
    const cfg = path.join(tmp, "cfg");
    const projectsRoot = path.join(tmp, "projekty");
    fs.mkdirSync(cfg);
    fs.mkdirSync(projectsRoot);
    fs.writeFileSync(path.join(cfg, "projects.yaml"), `projects_root: ${projectsRoot}\nprojects: []\n`);
    const fake = path.join(tmp, "fake.yaml");
    fs.writeFileSync(fake, FAKE);
    const port = PORT + workerInfo.parallelIndex;
    const url = `http://127.0.0.1:${port}`;
    // Hermeticky: bez hodnot z prostředí vývojáře; callback ani webhook testy nepoužívají.
    const env: NodeJS.ProcessEnv = {
      PATH: process.env.PATH, HOME: process.env.HOME, LANG: "C.UTF-8", AGENCAST_CONFIG_DIR: cfg, AGENCAST_TOKEN: TOKEN,
      OPENROUTER_API_KEY: "e2e-falesny-klic",
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
    // hermeticky: prohlížeč smí jen na `serve` tohoto workeru
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

// --- pomocníci ------------------------------------------------------------------------------

/** Fixture `dlouhy.yaml`: krok `pomalu` spí 4 s (FAKE). */
export const DLOUHY = `version: 1
name: dlouhy
description: Pomalý běh pro živé sledování
inputs:
  tema: { type: string, default: káva }
outputs:
  text: { type: string }
steps:
  - id: pomalu
    ask:
      agent: pisatel
      prompt: "Pomalu: {{ inputs.tema }}"
  - id: vystup
    output:
      text: "{{ steps.pomalu.text }}"
`;

/** Fixture `chyba.yaml`: napis → stop (fail) → vystup. */
export const CHYBA = `version: 1
name: chyba
description: Běh, který skončí chybou
inputs:
  tema: { type: string, default: káva }
outputs:
  text: { type: string }
steps:
  - id: napis
    ask:
      agent: pisatel
      prompt: "Napiš: {{ inputs.tema }}"
  - id: vynech
    when: inputs.tema == "nikdy"
    ask:
      agent: pisatel
      prompt: "Tohle se přeskočí"
    default: { text: "výchozí" }
  - id: stop
    when: inputs.tema != "nikdy"
    fail: "Zastaveno naschvál"
  - id: vystup
    output:
      text: "{{ steps.napis.text }} {{ steps.vynech.text }}"
`;

/** Spustí scénář přes API a vrátí `run_id`. */
export async function startRun(server: Server, project: string, scenario: string, extra: Json = {}): Promise<string> {
  const r = await server.api<{ run_id: string }>("POST", `/projects/${project}/runs`, { scenario, inputs: {}, ...extra });
  expect([200, 202], JSON.stringify(r.body)).toContain(r.status);
  return r.body.run_id;
}

/** Čeká, až běh dojde do některého ze stavů `states`. */
export async function waitRun(server: Server, project: string, id: string, states: string[], ms = 20_000): Promise<Json> {
  const until = Date.now() + ms;
  for (;;) {
    const r = await server.api<Json>("GET", `/projects/${project}/runs/${id}`);
    if (states.includes(String(r.body.state))) return r.body;
    if (Date.now() > until) throw new Error(`běh ${id} je ${r.body.state}, čekal jsem ${states}`);
    await sleep(200);
  }
}

/** Tab, dokud fokus nemá `target` (klávesnicová cesta bez myši). */
export async function tabTo(page: Page, target: ReturnType<Page["locator"]>, max = 60, key = "Tab") {
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return;
    await page.keyboard.press(key);
  }
  throw new Error(`fokus se na cíl nedostal po ${max}× ${key}`);
}

/** Počet požadavků, jejichž URL projde `test`, během `fn`. */
export async function countRequests(page: Page, test: (url: string, method: string) => boolean, fn: () => Promise<unknown>) {
  let n = 0;
  const on = (r: { url: () => string; method: () => string }) => void (test(r.url(), r.method()) && n++);
  page.on("request", on);
  await fn();
  page.off("request", on);
  return n;
}
