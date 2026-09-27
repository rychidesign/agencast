// Průzkumné QA GUI (vlna D): projde routy a stavy při několika šířkách, uloží screenshoty do
// /tmp/agencast-qa/<profil>/<obrazovka>.png, sbírá chyby konzole a sítě a spustí axe.
// Předpoklad: `ui/e2e/tools/qa-setup.sh` (serve --fake na 28950). Spuštění: `node ui/e2e/tools/qa-screens.ts [filtr]`.
import AxeBuilder from "@axe-core/playwright";
import { chromium, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";
import fs from "node:fs";

const URL = process.env.QA_URL ?? "http://127.0.0.1:28950";
const OUT = "/tmp/agencast-qa";
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
  const big = ((await api("/projects/krajni/runs?limit=5")).runs as { run_id: string }[])[0]?.run_id ?? "x";
  const ed = (p: string, s: string, q = "") => `#/p/${p}/scenare/${s}${q}`;
  return [
    { name: "token", hash: "#/", token: null },
    { name: "token-401", hash: "#/", token: "spatny" },
    { name: "projekty", hash: "#/" },
    { name: "projekty-menu", hash: "#/", act: click("Akce pro demo") },
    { name: "projekty-pridat", hash: "#/", act: click("Přidat projekt") },
    { name: "404-adresa", hash: "#/x/y" },
    { name: "404-projekt", hash: "#/p/neni" },
    { name: "nedostupny-projekt", hash: "#/p/stary" },
    { name: "demo-scenare", hash: "#/p/demo" },
    { name: "demo-scenare-menu", hash: "#/p/demo", act: click("Další akce") },
    { name: "demo-scenare-kartamenu", hash: "#/p/demo", act: click("Akce pro ukazka") },
    { name: "demo-scenare-novy", hash: "#/p/demo", act: click(/Nový scénář/) },
    { name: "demo-agenti", hash: "#/p/demo/agenti/pisatel" },
    { name: "demo-agenti-menu", hash: "#/p/demo/agenti/pisatel", act: click("Akce pro pisatel") },
    { name: "demo-agenti-markdown", hash: "#/p/demo/agenti/pisatel", act: click("Markdown", "radio") },
    { name: "demo-agenti-novy", hash: "#/p/demo/agenti/pisatel", act: click(/Nový agent/) },
    { name: "demo-behy", hash: "#/p/demo/behy" },
    { name: "demo-skilly", hash: "#/p/demo/skilly" },
    { name: "demo-config", hash: "#/p/demo/config" },
    { name: "demo-config-yaml", hash: "#/p/demo/config", act: click("YAML", "radio") },
    { name: "editor", hash: ed("demo", "ukazka") },
    { name: "editor-menu", hash: ed("demo", "ukazka"), act: click("Další akce") },
    { name: "editor-krok", hash: ed("demo", "ukazka", "?krok=napis") },
    { name: "editor-kartamenu", hash: ed("demo", "ukazka", "?krok=napis"), act: click("Akce pro napis") },
    { name: "editor-hlavicka", hash: ed("demo", "ukazka", "?krok=_hlavicka") },
    { name: "editor-spustit", hash: ed("demo", "ukazka"), act: click("Spustit") },
    { name: "editor-spustit-ostry", hash: ed("demo", "ukazka"), act: async (p) => (await click("Spustit")(p), await p.getByText("Ostrý běh").click()) },
    { name: "editor-typepicker", hash: ed("demo", "ukazka"), act: async (p) => (await p.getByTestId("add-after-napis").hover(), await p.getByTestId("add-after-napis").click()) },
    { name: "editor-typepicker-nahore", hash: ed("krajni", "velky"), act: async (p) => {
      await p.evaluate(() => scrollTo(0, 900));
      const b = p.getByTestId("add-after-krok_06");
      await b.hover(); await b.click();
    } },
    { name: "editor-kartamenu-dole", hash: ed("krajni", "velky"), act: async (p) => {
      const c = p.locator('[data-step-card="krok_12"]');
      await c.scrollIntoViewIfNeeded(); await p.evaluate(() => scrollBy(0, -innerHeight + 200));
      await c.hover(); await p.getByRole("button", { name: "Akce pro krok_12" }).click();
    } },
    { name: "editor-promenne", hash: ed("demo", "ukazka", "?krok=napis"), act: (p) => p.getByRole("button", { name: /Vložit proměnnou/ }).first().click() },
    { name: "editor-yaml", hash: ed("demo", "ukazka", "?rezim=yaml") },
    { name: "editor-chyba", hash: ed("demo", "chyba") },
    { name: "beh-uspech", hash: `#/p/demo/behy/${run("succeeded", "ukazka")}` },
    { name: "beh-uspech-krok", hash: `#/p/demo/behy/${run("succeeded", "ukazka")}?krok=napis` },
    { name: "beh-souhrn", hash: `#/p/demo/behy/${run("succeeded", "ukazka")}?zalozka=souhrn` },
    { name: "beh-report", hash: `#/p/demo/behy/${run("succeeded", "ukazka")}?zalozka=report` },
    { name: "beh-soubory", hash: `#/p/demo/behy/${run("succeeded", "ukazka")}?zalozka=soubory&soubor=summary.md` },
    { name: "beh-chyba", hash: `#/p/demo/behy/${run("failed")}` },
    { name: "beh-dryrun", hash: `#/p/demo/behy/${run("dry_run")}` },
    { name: "beh-bezi", hash: `#/p/demo/behy/${run("running")}` },
    { name: "beh-fronta", hash: `#/p/demo/behy/${run("queued")}` },
    { name: "beh-neexistuje", hash: "#/p/demo/behy/20990101-000000-nic-0000" },
    { name: "scenar-neexistuje", hash: ed("demo", "nic") },
    { name: "krajni-scenare", hash: "#/p/krajni" },
    { name: "krajni-velky", hash: ed("krajni", "velky") },
    { name: "krajni-velky-paralel", hash: ed("krajni", "velky", "?krok=paralelne") },
    { name: "krajni-velky-switch", hash: ed("krajni", "velky", "?krok=rozcesti") },
    { name: "krajni-velky-hlavicka", hash: ed("krajni", "velky", "?krok=_hlavicka") },
    { name: "krajni-dlouhy", hash: ed("krajni", "scenar-s-opravdu-hodne-dlouhym-nazvem-ktery-se-do-karty-ani-hlavicky-nevejde", "?krok=napis_velmi_dlouhe_id_kroku_ktere_se_nevejde_do_karty_vubec") },
    { name: "krajni-rozbity", hash: ed("krajni", "rozbity") },
    { name: "krajni-rozbity-yaml", hash: ed("krajni", "rozbity", "?rezim=yaml") },
    { name: "krajni-agent", hash: "#/p/krajni/agenti/ultra-dlouhy-agent-s-velmi-dlouhym-jmenem-ktery-se-nevejde-nikam" },
    { name: "krajni-chyby-popover", hash: "#/p/krajni", act: (p) => p.locator("header summary").first().click() },
    { name: "krajni-beh-velky", hash: `#/p/krajni/behy/${big}` },
    { name: "thtd-scenare", hash: "#/p/thtd" },
    { name: "thtd-igpost", hash: ed("thtd", "ig-post") },
    { name: "thtd-agenti", hash: "#/p/thtd/agenti/copywriter" },
    { name: "thtd-skilly", hash: "#/p/thtd/skilly/thtd-hlas" },
    { name: "thtd-config", hash: "#/p/thtd/config" },
  ];
}

const PROFILES: Record<string, BrowserContextOptions> = {
  "1440": { viewport: { width: 1440, height: 900 } },
  "1024": { viewport: { width: 1024, height: 768 } },
  "768": { viewport: { width: 768, height: 1024 } },
  "768-dotyk": { viewport: { width: 768, height: 1024 }, hasTouch: true, isMobile: true },
  "1440-reduced": { viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" },
};

const findings: string[] = [];
const axeAll: Record<string, { id: string; impact: string; help: string; nodes: string[] }[]> = {};

async function shoot(browser: Browser, profile: string, s: Screen) {
  const ctx = await browser.newContext({ ...PROFILES[profile], locale: "cs-CZ", timezoneId: "Europe/Prague", deviceScaleFactor: 1 });
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
  // bez networkidle: stránky běhů se dotazují pořád dokola
  await page.waitForTimeout(900);
  try {
    if (s.act) {
      await s.act(page);
      await page.waitForTimeout(400);
    }
  } catch (e) {
    findings.push(`${tag} akce selhala: ${(e as Error).message.split("\n")[0]}`);
  }
  const dir = `${OUT}/${profile}`;
  fs.mkdirSync(dir, { recursive: true });
  const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  if (over > 0) findings.push(`${tag} vodorovné přetečení o ${over} px`);
  await page.screenshot({ path: `${dir}/${s.name}.png`, fullPage: !s.act });
  if (profile === "1440" || profile === "768") {
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
console.log(`${list.length} obrazovek × ${profiles.length} profilů; nálezů ${new Set(findings).size}; axe ${Object.keys(axeAll).length} obrazovek s porušením`);
