// Exploratory QA: interactive states (keyboard, focus, conflict, outage, draft, overlaps).
// Requires qa-setup.sh. Run: `node ui/e2e/tools/qa-flows.ts [filter]`; screenshots go to /tmp/agencast-qa/flows/.
import { chromium, type Page } from "@playwright/test";
import fs from "node:fs";

const URL = process.env.QA_URL ?? "http://127.0.0.1:28950";
const OUT = (process.env.QA_OUT ?? "/tmp/agencast-qa") + "/flows";
const H = { Authorization: "Bearer test-token", "Content-Type": "application/json" };
fs.mkdirSync(OUT, { recursive: true });
const log: string[] = [];
const note = (s: string) => (log.push(s), console.log(s));

const P = `qa${Date.now() % 100000}`;
const created = await (await fetch(`${URL}/projects/new`, { method: "POST", headers: H, body: JSON.stringify({ name: P }) })).json();
const WF = `${created.root}/workflows`;

const browser = await chromium.launch();
async function open(width = 1440, height = 900, extra = {}) {
  const ctx = await browser.newContext({ viewport: { width, height }, locale: "en-US", ...extra });
  await ctx.addInitScript(() => localStorage.getItem("agencast.token") || localStorage.setItem("agencast.token", "test-token"));
  const page = await ctx.newPage();
  page.setDefaultTimeout(5000);
  page.on("console", (m) => m.type() === "error" && !m.text().includes("Failed to load resource") && note(`console: ${m.text().slice(0, 200)}`));
  page.on("pageerror", (e) => note(`pageerror: ${e.message}`));
  return page;
}
const shot = (page: Page, name: string, full = false) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: full });
const focused = (page: Page) => page.evaluate(() => {
  const el = document.activeElement as HTMLElement | null;
  if (!el) return "-";
  const name = el.getAttribute("aria-label") ?? el.textContent?.trim().slice(0, 40) ?? "";
  const cs = getComputedStyle(el);
  const ring = cs.boxShadow !== "none" || cs.outlineStyle !== "none";
  return `${el.tagName.toLowerCase()}${el.getAttribute("role") ? `[${el.getAttribute("role")}]` : ""} "${name}"${ring ? "" : " (NO VISIBLE FOCUS)"}`;
});

const api = async (method: string, path: string, body?: unknown) =>
  (await fetch(URL + path, { method, headers: H, body: body === undefined ? undefined : JSON.stringify(body) })).json();

const flows: Record<string, () => Promise<void>> = {
  async live() {
    // live run: pulse, ticking time, follow run, end, polling stops; the run list refreshes
    fs.writeFileSync(`${WF}/scenarios/slow.yaml`, fs.readFileSync(`${import.meta.dirname}/qa-fixtures/slow.yaml`, "utf8"));
    const { run_id } = await api("POST", `/projects/${P}/runs`, { scenario: "slow", inputs: {} });
    const page = await open();
    const runs = await open();
    await runs.goto(`${URL}/#/p/${P}/runs`);
    await page.goto(`${URL}/#/p/${P}/runs/${run_id}`);
    await page.waitForTimeout(1200);
    await shot(page, "live-running");
    await shot(runs, "live-list");
    note(`live: status ${await page.getByTestId("run-state").textContent()}, follow: ${await page.getByText("follow run").count()}`);
    await page.waitForTimeout(5000);
    await shot(page, "live-end");
    note(`after the end: status ${await page.getByTestId("run-state").textContent()}, follow: ${await page.getByText("follow run").count()}, status: ${await page.getByRole("status").allTextContents()}`);
    let n = 0;
    page.on("request", (r) => r.url().includes(run_id) && n++);
    let m = 0;
    runs.on("request", (r) => r.url().includes("/runs?") && m++);
    await page.waitForTimeout(7000);
    note(`GET run after the end in 7 s: ${n}; GET list in 7 s: ${m}`);
    await shot(runs, "live-list-end");
    await page.context().close();
    await runs.context().close();
  },
  async dialogs() {
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/agents/writer`);
    await page.getByRole("button", { name: "Actions for writer" }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await page.waitForTimeout(600);
    await shot(page, "dialog-delete-rejected");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /New agent/ }).click();
    await page.keyboard.type("Wrong");
    await shot(page, "dialog-new-agent-error");
    await page.keyboard.press("Escape");
    await page.goto(`${URL}/#/p/${P}/scenarios/demo?step=write`);
    await page.getByRole("combobox", { name: "Step type" }).selectOption("jev");
    await page.waitForTimeout(300);
    await shot(page, "dialog-change-type");
    await page.keyboard.press("Escape");
    await page.locator('[data-step-card="write"]').focus();
    await page.keyboard.press("Delete");
    await page.waitForTimeout(300);
    await shot(page, "dialog-delete-step");
    note(`focus in the delete-step dialog: ${await focused(page)}`);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: "Rename" }).click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("demo");
    await shot(page, "dialog-rename");
    await page.keyboard.press("Escape");
    // broken config (422)
    const cfg = `${WF}/config.yaml`;
    const good = fs.readFileSync(cfg, "utf8");
    fs.writeFileSync(cfg, `${good}\nruns_dir: ./elsewhere\n`);
    await page.goto(`${URL}/#/p/${P}`);
    await page.waitForTimeout(800);
    await shot(page, "config-422-scenarios");
    await page.goto(`${URL}/#/p/${P}/config`);
    await page.waitForTimeout(1000);
    await shot(page, "config-422-config");
    fs.writeFileSync(cfg, good);
    await page.context().close();
  },
  async tab() {
    // Tab order and visible focus in the editor
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenarios/demo`);
    await page.waitForTimeout(800);
    const seen: string[] = [];
    for (let i = 0; i < 28; i++) {
      await page.keyboard.press("Tab");
      seen.push(await focused(page));
    }
    note("TAB editor:\n  " + seen.join("\n  "));
    await page.locator('[data-step-card="write"]').focus();
    await page.keyboard.press("Tab");
    await shot(page, "focus-card-menu");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await shot(page, "focus-plus");
    await page.keyboard.press("Enter");
    await shot(page, "focus-typepicker");
    await page.keyboard.press("Escape");
    note(`focus after Esc from the picker: ${await focused(page)}`);
    await page.goto(`${URL}/#/p/${P}`);
    await page.waitForTimeout(600);
    const seen2: string[] = [];
    for (let i = 0; i < 14; i++) {
      await page.keyboard.press("Tab");
      seen2.push(await focused(page));
    }
    note("TAB scenarios:\n  " + seen2.join("\n  "));
    await page.context().close();
  },
  async keyboard() {
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenarios/demo`);
    const card = page.locator('[data-step-card="write"]');
    await card.click();
    await page.waitForTimeout(300);
    note(`focus after clicking the card: ${await focused(page)}`);
    await page.keyboard.press("Escape");
    note(`focus after Esc: ${await focused(page)}; url ${page.url().split("#")[1]}`);
    await card.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
    note(`Enter on the card → focus: ${await focused(page)}`);
    await page.keyboard.press("Escape");
    await card.focus();
    await page.keyboard.press("ArrowDown");
    note(`↓ from write: ${await focused(page)}`);
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    note(`↑↑: ${await focused(page)}`);
    // Ctrl+X and paste
    await card.focus();
    await page.keyboard.press("Control+x");
    await page.waitForTimeout(200);
    await shot(page, "cut");
    note(`announce after Ctrl+X: ${await page.getByTestId("announce").textContent()}`);
    await page.keyboard.press("Control+z");
    await page.waitForTimeout(200);
    // menu: Esc and a click outside
    await page.getByRole("button", { name: "More actions" }).click();
    note(`menu open: ${await page.getByRole("menu").count()}, focus ${await focused(page)}`);
    await page.keyboard.press("Escape");
    note(`menu after Esc: ${await page.getByRole("menu").count()}, focus ${await focused(page)}`);
    await page.getByRole("button", { name: "More actions" }).click();
    await page.mouse.click(700, 700);
    note(`menu after a click outside: ${await page.getByRole("menu").count()}`);
    await page.getByRole("button", { name: "More actions" }).click();
    await page.keyboard.press("Tab");
    note(`menu after Tab: ${await page.getByRole("menu").count()}, focus ${await focused(page)}`);
    await page.context().close();
  },
  async prompt() {
    // typing into the prompt: undo in the field, SaveNote, draft after reload, beforeunload
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenarios/demo?step=write`);
    const prompt = page.getByRole("combobox", { name: "Prompt" });
    await prompt.click();
    await page.keyboard.press("End");
    const t0 = Date.now();
    await page.keyboard.type(" and something extra to test typing speed", { delay: 0 });
    note(`typing 41 characters: ${Date.now() - t0} ms`);
    note(`SaveNote: ${await page.getByTestId("save-status").textContent()}`);
    await shot(page, "unsaved");
    page.on("dialog", (d) => (note(`dialog ${d.type()}`), d.accept()));
    await page.reload();
    await page.waitForTimeout(1000);
    note(`SaveNote after reload: ${await page.getByTestId("save-status").textContent()}; prompt ends with: ${(await page.getByRole("combobox", { name: "Prompt" }).inputValue()).slice(-20)}`);
    // conflict: a change on disk
    fs.appendFileSync(`${WF}/scenarios/demo.yaml`, "# by hand\n");
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.waitForTimeout(1500);
    await shot(page, "conflict");
    await page.evaluate(() => scrollTo(0, 400));
    await shot(page, "conflict-scroll");
    await page.getByRole("button", { name: "Show diff" }).click();
    await page.waitForTimeout(300);
    await shot(page, "conflict-diff");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Keep mine" }).click();
    await page.getByRole("button", { name: "Save" }).first().click();
    await page.waitForTimeout(300);
    await shot(page, "conflict-overwrite");
    await page.getByRole("button", { name: "Overwrite the version on disk" }).click();
    await page.waitForTimeout(800);
    note(`after overwriting: ${await page.getByTestId("save-status").textContent()}`);
    await page.context().close();
  },
  async offline() {
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenarios/demo?step=write`);
    await page.waitForTimeout(500);
    await page.route("**/projects/**", (r) => r.abort());
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.getByRole("combobox", { name: "Prompt" }).fill("offline change");
    await page.getByRole("button", { name: "Save" }).first().click();
    await page.waitForTimeout(1500);
    await shot(page, "offline-editor");
    note(`offline SaveNote: ${await page.getByTestId("save-status").textContent()}; server-bar: ${await page.getByTestId("server-bar").count()}`);
    await page.unroute("**/projects/**");
    await page.waitForTimeout(6000);
    note(`server-bar after recovery: ${await page.getByTestId("server-bar").count()}`);
    await page.getByRole("button", { name: "Save" }).first().click();
    await page.waitForTimeout(800);
    note(`SaveNote after recovery: ${await page.getByTestId("save-status").textContent()}`);
    const p2 = await open(768, 1024);
    await p2.route("**/projects*", (r) => r.abort());
    await p2.goto(`${URL}/#/p/${P}`);
    await p2.waitForTimeout(1500);
    await shot(p2, "offline-768");
    await page.context().close();
    await p2.context().close();
  },
  async validation() {
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenarios/demo?step=write`);
    await page.getByRole("combobox", { name: "Prompt" }).fill("Topic: {{ steps.missing.text }}");
    await page.getByRole("button", { name: "Save" }).first().click();
    await page.waitForTimeout(1200);
    await shot(page, "validation-error");
    await page.getByRole("radio", { name: "YAML" }).click();
    await page.waitForTimeout(800);
    await shot(page, "validation-yaml");
    const area = page.getByRole("textbox", { name: "scenarios/demo.yaml" });
    await area.click();
    await page.keyboard.press("Control+Home");
    await page.keyboard.type("  ");
    await page.waitForTimeout(1500);
    await shot(page, "yaml-syntax");
    await page.getByRole("radio", { name: "Form" }).hover();
    await page.waitForTimeout(600);
    await shot(page, "yaml-form-disabled-hover");
    await page.context().close();
  },
  async rightEdge() {
    // TypePicker and the card menu near the right edge (768, 1024)
    for (const w of [768, 1024]) {
      const page = await open(w, 900);
      await page.goto(`${URL}/#/p/${P}/scenarios/demo`);
      const card = page.locator('[data-step-card="write"]');
      await card.hover();
      await page.getByRole("button", { name: "Actions for write" }).click();
      await shot(page, `card-menu-${w}`);
      await page.getByRole("menuitem", { name: "Insert step below" }).click();
      await page.waitForTimeout(300);
      const box = await page.getByRole("listbox").boundingBox();
      note(`[${w}] picker from the card menu: x=${box?.x} right=${box && box.x + box.width} (viewport ${w})`);
      await shot(page, `picker-z-menu-${w}`);
      await page.context().close();
    }
  },
  async touch() {
    const page = await open(768, 1024, { hasTouch: true, isMobile: true });
    await page.goto(`${URL}/#/p/${P}/scenarios/demo`);
    await page.waitForTimeout(600);
    const small = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>("button, a, select, input, [role=radio]")]
      .filter((el) => el.offsetParent && getComputedStyle(el).visibility !== "hidden")
      .map((el) => ({ n: el.getAttribute("aria-label") ?? el.textContent?.trim().slice(0, 30), r: el.getBoundingClientRect() }))
      .filter((x) => x.r.width > 0 && (x.r.height < 44 || x.r.width < 24))
      .map((x) => `${x.n} ${Math.round(x.r.width)}×${Math.round(x.r.height)}`));
    note(`touch <44 px (editor):\n  ${small.join("\n  ")}`);
    await shot(page, "touch-editor", true);
    await page.context().close();
  },
};

const only = process.argv[2];
for (const [name, fn] of Object.entries(flows)) {
  if (only && !name.includes(only)) continue;
  note(`=== ${name}`);
  try { await fn(); } catch (e) { note(`!! ${name} failed: ${(e as Error).message.split("\n").slice(0, 4).join(" / ")}`); }
}
await browser.close();
fs.writeFileSync(`${OUT}/log.txt`, log.join("\n") + "\n");
