// Exploratory GUI QA (wave D): walks routes and states at several widths, saves screenshots to
// /tmp/agencast-qa/<profile>/<screen>.png, collects console and network errors and runs axe.
// Requires `ui/e2e/tools/qa-setup.sh` (serve --fake on 28950). Run: `node ui/e2e/tools/qa-screens.ts [filter]`.
import AxeBuilder from "@axe-core/playwright";
import { chromium, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";
import fs from "node:fs";

const URL = process.env.QA_URL ?? "http://127.0.0.1:28950";
const OUT = process.env.QA_OUT ?? "/tmp/agencast-qa";
const only = process.argv[2];
const H = { Authorization: "Bearer test-token" };
const api = async (p: string) => (await fetch(URL + p, { headers: H })).json();

type Act = (page: Page) => Promise<unknown>;
interface Screen { name: string; hash: string; act?: Act; token?: string | null }

const click = (name: string | RegExp, role: "button" | "link" | "tab" | "radio" = "button"): Act =>
  (p) => p.getByRole(role, { name, exact: typeof name === "string" }).first().click();

async function screens(): Promise<Screen[]> {
  const runs = (await api("/projects/demo/runs?limit=50")).runs as { run_id: string; scenario: string; state: string }[];
  const run = (state: string, sc?: string) => runs.find((r) => r.state === state && (!sc || r.scenario === sc))?.run_id ?? "x";
  const big = ((await api("/projects/edge-cases/runs?limit=5")).runs as { run_id: string }[])[0]?.run_id ?? "x";
  const ed = (p: string, s: string, q = "") => `#/p/${p}/scenarios/${s}${q}`;
  return [
    { name: "token", hash: "#/", token: null },
    { name: "token-401", hash: "#/", token: "wrong" },
    { name: "projects", hash: "#/" },
    { name: "projects-menu", hash: "#/", act: click("Actions for demo") },
    { name: "projects-add", hash: "#/", act: click("Add project") },
    { name: "404-address", hash: "#/x/y" },
    { name: "404-project", hash: "#/p/absent" },
    { name: "unavailable-project", hash: "#/p/stale" },
    { name: "demo-scenarios", hash: "#/p/demo" },
    { name: "demo-scenarios-menu", hash: "#/p/demo", act: click("More actions") },
    { name: "demo-navigation", hash: "#/p/demo/runs", act: click("Navigation") },
    { name: "demo-scenarios-card-menu", hash: "#/p/demo", act: click("Actions for demo") },
    { name: "demo-scenarios-new", hash: "#/p/demo", act: click(/New scenario/) },
    { name: "demo-agents", hash: "#/p/demo/agents/writer" },
    { name: "demo-agents-menu", hash: "#/p/demo/agents/writer", act: click("Actions for writer") },
    { name: "demo-agents-markdown", hash: "#/p/demo/agents/writer", act: click("Markdown", "radio") },
    { name: "demo-agents-new", hash: "#/p/demo/agents/writer", act: click(/New agent/) },
    { name: "demo-runs", hash: "#/p/demo/runs" },
    { name: "demo-skills", hash: "#/p/demo/skills" },
    { name: "demo-config", hash: "#/p/demo/config" },
    { name: "demo-config-yaml", hash: "#/p/demo/config", act: click("YAML", "radio") },
    { name: "editor", hash: ed("demo", "demo") },
    { name: "editor-menu", hash: ed("demo", "demo"), act: click("More actions") },
    { name: "editor-step", hash: ed("demo", "demo", "?step=write") },
    { name: "editor-card-menu", hash: ed("demo", "demo", "?step=write"), act: click("Actions for write") },
    { name: "editor-header", hash: ed("demo", "demo", "?step=_header") },
    { name: "editor-run", hash: ed("demo", "demo"), act: click("Run") },
    { name: "editor-run-live", hash: ed("demo", "demo"), act: async (p) => (await click("Run")(p), await p.getByText("Live run").click()) },
    { name: "editor-typepicker", hash: ed("demo", "demo"), act: async (p) => (await p.getByTestId("add-after-write").hover(), await p.getByTestId("add-after-write").click()) },
    { name: "editor-typepicker-top", hash: ed("edge-cases", "big"), act: async (p) => {
      await p.evaluate(() => scrollTo(0, 900));
      const b = p.getByTestId("add-after-step_06");
      await b.hover(); await b.click();
    } },
    { name: "editor-card-menu-bottom", hash: ed("edge-cases", "big"), act: async (p) => {
      const c = p.locator('[data-step-card="step_12"]');
      await c.scrollIntoViewIfNeeded(); await p.evaluate(() => scrollBy(0, -innerHeight + 200));
      await c.hover(); await p.getByRole("button", { name: "Actions for step_12" }).click();
    } },
    { name: "editor-variables", hash: ed("demo", "demo", "?step=write"), act: (p) => p.getByRole("button", { name: /Insert variable/ }).first().click() },
    { name: "editor-yaml", hash: ed("demo", "demo", "?mode=yaml") },
    { name: "editor-error", hash: ed("demo", "failing") },
    { name: "run-success", hash: `#/p/demo/runs/${run("succeeded", "demo")}` },
    { name: "run-success-step", hash: `#/p/demo/runs/${run("succeeded", "demo")}?step=write` },
    { name: "run-summary", hash: `#/p/demo/runs/${run("succeeded", "demo")}?tab=summary` },
    { name: "run-report", hash: `#/p/demo/runs/${run("succeeded", "demo")}?tab=report` },
    { name: "run-files", hash: `#/p/demo/runs/${run("succeeded", "demo")}?tab=files&file=summary.md` },
    { name: "run-error", hash: `#/p/demo/runs/${run("failed")}` },
    { name: "run-dryrun", hash: `#/p/demo/runs/${run("dry_run")}` },
    { name: "run-running", hash: `#/p/demo/runs/${run("running")}` },
    { name: "run-queue", hash: `#/p/demo/runs/${run("queued")}` },
    { name: "run-missing", hash: "#/p/demo/runs/20990101-000000-missing-0000" },
    { name: "scenario-missing", hash: ed("demo", "missing") },
    { name: "edge-scenarios", hash: "#/p/edge-cases" },
    { name: "edge-big", hash: ed("edge-cases", "big") },
    { name: "edge-big-parallel", hash: ed("edge-cases", "big", "?step=in_parallel") },
    { name: "edge-big-switch", hash: ed("edge-cases", "big", "?step=crossroads") },
    { name: "edge-big-header", hash: ed("edge-cases", "big", "?step=_header") },
    { name: "edge-long", hash: ed("edge-cases", "scenario-with-a-really-long-name-that-fits-neither-card-nor-header", "?step=write_very_long_step_id_that_does_not_fit_on_the_card_at_all") },
    { name: "edge-broken", hash: ed("edge-cases", "broken") },
    { name: "edge-broken-yaml", hash: ed("edge-cases", "broken", "?mode=yaml") },
    { name: "edge-agent", hash: "#/p/edge-cases/agents/ultra-long-agent-with-a-very-long-name-that-fits-nowhere" },
    { name: "edge-errors-popover", hash: "#/p/edge-cases", act: (p) => p.getByTestId("validation-popover-trigger").click() },
    { name: "edge-run-big", hash: `#/p/edge-cases/runs/${big}` },
    { name: "lumen-scenarios", hash: "#/p/lumen" },
    { name: "lumen-igpost", hash: ed("lumen", "ig-post") },
    { name: "lumen-agents", hash: "#/p/lumen/agents/copywriter" },
    { name: "lumen-skills", hash: "#/p/lumen/skills/lumen-voice" },
    { name: "lumen-config", hash: "#/p/lumen/config" },
  ];
}

const PROFILES: Record<string, BrowserContextOptions> = {
  "1440": { viewport: { width: 1440, height: 900 } },
  "1024": { viewport: { width: 1024, height: 768 } },
  "768": { viewport: { width: 768, height: 1024 } },
  "768-touch": { viewport: { width: 768, height: 1024 }, hasTouch: true, isMobile: true },
  "1440-reduced": { viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" },
  "390": { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true },
  "430": { viewport: { width: 430, height: 932 }, hasTouch: true, isMobile: true },
};

const findings: string[] = [];
const axeAll: Record<string, { id: string; impact: string; help: string; nodes: string[] }[]> = {};

async function shoot(browser: Browser, profile: string, s: Screen) {
  const ctx = await browser.newContext({ ...PROFILES[profile], locale: "en-US", timezoneId: "Europe/Prague", deviceScaleFactor: 1 });
  const token = s.token === undefined ? "test-token" : s.token;
  if (token) await ctx.addInitScript((tk) => localStorage.setItem("agencast.token", tk), token);
  const page = await ctx.newPage();
  page.setDefaultTimeout(5000);
  const tag = `[${profile}] ${s.name}`;
  page.on("console", (m) => ["error", "warning"].includes(m.type()) && findings.push(`${tag} console.${m.type()}: ${m.text().slice(0, 300)}`));
  page.on("pageerror", (e) => findings.push(`${tag} pageerror: ${e.message}`));
  page.on("requestfailed", (r) => findings.push(`${tag} requestfailed: ${r.url()} ${r.failure()?.errorText}`));
  page.on("response", (r) => r.status() >= 400 && findings.push(`${tag} HTTP ${r.status()} ${r.request().method()} ${r.url().replace(URL, "")}`));
  await page.goto(URL + "/" + s.hash);
  // no networkidle: run pages poll continuously
  await page.waitForTimeout(900);
  try {
    if (s.act) {
      await s.act(page);
      await page.waitForTimeout(400);
    }
  } catch (e) {
    findings.push(`${tag} action failed: ${(e as Error).message.split("\n")[0]}`);
  }
  const dir = `${OUT}/${profile}`;
  fs.mkdirSync(dir, { recursive: true });
  const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  if (over > 0) findings.push(`${tag} horizontal overflow by ${over} px`);
  await page.screenshot({ path: `${dir}/${s.name}.png`, fullPage: !s.act });
  if (["1440", "768", "390"].includes(profile)) {
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const v = r.violations.map((x) => ({ id: x.id, impact: x.impact ?? "", help: x.help, nodes: x.nodes.slice(0, 4).map((n) => n.target.join(" ")) }));
    if (v.length) axeAll[`${profile}/${s.name}`] = v;
  }
  await ctx.close();
}

const browser = await chromium.launch();
const list = (await screens()).filter((s) => !only || s.name.includes(only));
const profiles = (process.env.QA_PROFILES ?? Object.keys(PROFILES).join(",")).split(",");
for (const profile of profiles) for (const s of list) await shoot(browser, profile, s);
await browser.close();
fs.writeFileSync(`${OUT}/findings.txt`, [...new Set(findings)].join("\n") + "\n");
fs.writeFileSync(`${OUT}/axe.json`, JSON.stringify(axeAll, null, 1));
console.log(`${list.length} screens × ${profiles.length} profiles; ${new Set(findings).size} findings; axe: ${Object.keys(axeAll).length} screens with violations`);
