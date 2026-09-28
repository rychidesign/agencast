// Průzkumné QA: interaktivní stavy (klávesnice, fokus, konflikt, výpadek, draft, překryvy).
// Předpoklad: qa-setup.sh. Spuštění: `node ui/e2e/tools/qa-flows.ts [filtr]`; snímky do /tmp/agencast-qa/flows/.
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
  const ctx = await browser.newContext({ viewport: { width, height }, locale: "cs-CZ", ...extra });
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
  return `${el.tagName.toLowerCase()}${el.getAttribute("role") ? `[${el.getAttribute("role")}]` : ""} "${name}"${ring ? "" : " (BEZ VIDITELNÉHO FOKUSU)"}`;
});

const api = async (method: string, path: string, body?: unknown) =>
  (await fetch(URL + path, { method, headers: H, body: body === undefined ? undefined : JSON.stringify(body) })).json();

const flows: Record<string, () => Promise<void>> = {
  async zive() {
    // živý běh: pulz, tikající čas, sledovat běh, konec, polling se zastaví; seznam běhů se obnovuje
    fs.writeFileSync(`${WF}/scenarios/dlouhy.yaml`, fs.readFileSync(`${import.meta.dirname}/qa-fixtures/dlouhy.yaml`, "utf8"));
    const { run_id } = await api("POST", `/projects/${P}/runs`, { scenario: "dlouhy", inputs: {} });
    const page = await open();
    const runs = await open();
    await runs.goto(`${URL}/#/p/${P}/behy`);
    await page.goto(`${URL}/#/p/${P}/behy/${run_id}`);
    await page.waitForTimeout(1200);
    await shot(page, "zive-bezi");
    await shot(runs, "zive-seznam");
    note(`živý: stav ${await page.getByTestId("run-state").textContent()}, sledovat: ${await page.getByText("sledovat běh").count()}`);
    await page.waitForTimeout(5000);
    await shot(page, "zive-konec");
    note(`po konci: stav ${await page.getByTestId("run-state").textContent()}, sledovat: ${await page.getByText("sledovat běh").count()}, status: ${await page.getByRole("status").allTextContents()}`);
    let n = 0;
    page.on("request", (r) => r.url().includes(run_id) && n++);
    let m = 0;
    runs.on("request", (r) => r.url().includes("/runs?") && m++);
    await page.waitForTimeout(7000);
    note(`GET běhu po konci za 7 s: ${n}; GET seznamu za 7 s: ${m}`);
    await shot(runs, "zive-seznam-konec");
    await page.context().close();
    await runs.context().close();
  },
  async dialogy() {
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/agenti/pisatel`);
    await page.getByRole("button", { name: "Akce pro pisatel" }).click();
    await page.getByRole("menuitem", { name: "Smazat" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Smazat" }).click();
    await page.waitForTimeout(600);
    await shot(page, "dialog-smazat-odmitnuto");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /Nový agent/ }).click();
    await page.keyboard.type("Spatne");
    await shot(page, "dialog-novy-agent-chyba");
    await page.keyboard.press("Escape");
    await page.goto(`${URL}/#/p/${P}/scenare/ukazka?krok=napis`);
    await page.getByRole("combobox", { name: "Typ kroku" }).selectOption("jev");
    await page.waitForTimeout(300);
    await shot(page, "dialog-zmena-typu");
    await page.keyboard.press("Escape");
    await page.locator('[data-step-card="napis"]').focus();
    await page.keyboard.press("Delete");
    await page.waitForTimeout(300);
    await shot(page, "dialog-smazat-krok");
    note(`fokus v dialogu smazání kroku: ${await focused(page)}`);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Další akce" }).click();
    await page.getByRole("menuitem", { name: "Přejmenovat" }).click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("ukazka");
    await shot(page, "dialog-prejmenovat");
    await page.keyboard.press("Escape");
    // rozbitý config (422)
    const cfg = `${WF}/config.yaml`;
    const good = fs.readFileSync(cfg, "utf8");
    fs.writeFileSync(cfg, `${good}\nruns_dir: ./jinde\n`);
    await page.goto(`${URL}/#/p/${P}`);
    await page.waitForTimeout(800);
    await shot(page, "config-422-scenare");
    await page.goto(`${URL}/#/p/${P}/config`);
    await page.waitForTimeout(1000);
    await shot(page, "config-422-config");
    fs.writeFileSync(cfg, good);
    await page.context().close();
  },
  async tab() {
    // pořadí Tab a viditelný fokus na editoru
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenare/ukazka`);
    await page.waitForTimeout(800);
    const seen: string[] = [];
    for (let i = 0; i < 28; i++) {
      await page.keyboard.press("Tab");
      seen.push(await focused(page));
    }
    note("TAB editor:\n  " + seen.join("\n  "));
    await page.locator('[data-step-card="napis"]').focus();
    await page.keyboard.press("Tab");
    await shot(page, "fokus-karta-menu");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await shot(page, "fokus-plus");
    await page.keyboard.press("Enter");
    await shot(page, "fokus-typepicker");
    await page.keyboard.press("Escape");
    note(`po Esc z pickeru fokus: ${await focused(page)}`);
    await page.goto(`${URL}/#/p/${P}`);
    await page.waitForTimeout(600);
    const seen2: string[] = [];
    for (let i = 0; i < 14; i++) {
      await page.keyboard.press("Tab");
      seen2.push(await focused(page));
    }
    note("TAB scénáře:\n  " + seen2.join("\n  "));
    await page.context().close();
  },
  async klavesy() {
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenare/ukazka`);
    const card = page.locator('[data-step-card="napis"]');
    await card.click();
    await page.waitForTimeout(300);
    note(`po kliku na kartu fokus: ${await focused(page)}`);
    await page.keyboard.press("Escape");
    note(`po Esc fokus: ${await focused(page)}; url ${page.url().split("#")[1]}`);
    await card.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
    note(`Enter na kartě → fokus: ${await focused(page)}`);
    await page.keyboard.press("Escape");
    await card.focus();
    await page.keyboard.press("ArrowDown");
    note(`↓ z napis: ${await focused(page)}`);
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    note(`↑↑: ${await focused(page)}`);
    // Ctrl+X a vložení
    await card.focus();
    await page.keyboard.press("Control+x");
    await page.waitForTimeout(200);
    await shot(page, "vyjmuto");
    note(`po Ctrl+X announce: ${await page.getByTestId("announce").textContent()}`);
    await page.keyboard.press("Control+z");
    await page.waitForTimeout(200);
    // menu Esc a klik mimo
    await page.getByRole("button", { name: "Další akce" }).click();
    note(`menu otevřené: ${await page.getByRole("menu").count()} , fokus ${await focused(page)}`);
    await page.keyboard.press("Escape");
    note(`menu po Esc: ${await page.getByRole("menu").count()} , fokus ${await focused(page)}`);
    await page.getByRole("button", { name: "Další akce" }).click();
    await page.mouse.click(700, 700);
    note(`menu po kliku mimo: ${await page.getByRole("menu").count()}`);
    await page.getByRole("button", { name: "Další akce" }).click();
    await page.keyboard.press("Tab");
    note(`menu po Tab: ${await page.getByRole("menu").count()} , fokus ${await focused(page)}`);
    await page.context().close();
  },
  async prompt() {
    // psaní do promptu: undo v poli, SaveNote, draft po reloadu, beforeunload
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenare/ukazka?krok=napis`);
    const prompt = page.getByRole("combobox", { name: "Prompt" });
    await prompt.click();
    await page.keyboard.press("End");
    const t0 = Date.now();
    await page.keyboard.type(" a ještě něco navíc pro test rychlosti psaní", { delay: 0 });
    note(`psaní 44 znaků: ${Date.now() - t0} ms`);
    note(`SaveNote: ${await page.getByTestId("save-status").textContent()}`);
    await shot(page, "neulozeno");
    page.on("dialog", (d) => (note(`dialog ${d.type()}`), d.accept()));
    await page.reload();
    await page.waitForTimeout(1000);
    note(`po reloadu SaveNote: ${await page.getByTestId("save-status").textContent()}; prompt obsahuje: ${(await page.getByRole("combobox", { name: "Prompt" }).inputValue()).slice(-20)}`);
    // konflikt: změna na disku
    fs.appendFileSync(`${WF}/scenarios/ukazka.yaml`, "# ručně\n");
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.waitForTimeout(1500);
    await shot(page, "konflikt");
    await page.evaluate(() => scrollTo(0, 400));
    await shot(page, "konflikt-scroll");
    await page.getByRole("button", { name: "Zobrazit rozdíl" }).click();
    await page.waitForTimeout(300);
    await shot(page, "konflikt-rozdil");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Ponechat moje" }).click();
    await page.getByRole("button", { name: "Uložit" }).first().click();
    await page.waitForTimeout(300);
    await shot(page, "konflikt-prepsat");
    await page.getByRole("button", { name: "Přepsat verzi na disku" }).click();
    await page.waitForTimeout(800);
    note(`po přepsání: ${await page.getByTestId("save-status").textContent()}`);
    await page.context().close();
  },
  async offline() {
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenare/ukazka?krok=napis`);
    await page.waitForTimeout(500);
    await page.route("**/projects/**", (r) => r.abort());
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.getByRole("combobox", { name: "Prompt" }).fill("offline změna");
    await page.getByRole("button", { name: "Uložit" }).first().click();
    await page.waitForTimeout(1500);
    await shot(page, "offline-editor");
    note(`offline SaveNote: ${await page.getByTestId("save-status").textContent()}; server-bar: ${await page.getByTestId("server-bar").count()}`);
    await page.unroute("**/projects/**");
    await page.waitForTimeout(6000);
    note(`po obnovení server-bar: ${await page.getByTestId("server-bar").count()}`);
    await page.getByRole("button", { name: "Uložit" }).first().click();
    await page.waitForTimeout(800);
    note(`po obnovení SaveNote: ${await page.getByTestId("save-status").textContent()}`);
    const p2 = await open(768, 1024);
    await p2.route("**/projects*", (r) => r.abort());
    await p2.goto(`${URL}/#/p/${P}`);
    await p2.waitForTimeout(1500);
    await shot(p2, "offline-768");
    await page.context().close();
    await p2.context().close();
  },
  async validace() {
    const page = await open();
    await page.goto(`${URL}/#/p/${P}/scenare/ukazka?krok=napis`);
    await page.getByRole("combobox", { name: "Prompt" }).fill("Téma: {{ steps.nic.text }}");
    await page.getByRole("button", { name: "Uložit" }).first().click();
    await page.waitForTimeout(1200);
    await shot(page, "validace-chyba");
    await page.getByRole("radio", { name: "YAML" }).click();
    await page.waitForTimeout(800);
    await shot(page, "validace-yaml");
    const area = page.getByRole("textbox", { name: "scenarios/ukazka.yaml" });
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
  async pravyokraj() {
    // TypePicker a menu karty u pravého okraje (768, 1024)
    for (const w of [768, 1024]) {
      const page = await open(w, 900);
      await page.goto(`${URL}/#/p/${P}/scenare/ukazka`);
      const card = page.locator('[data-step-card="napis"]');
      await card.hover();
      await page.getByRole("button", { name: "Akce pro napis" }).click();
      await shot(page, `kartamenu-${w}`);
      await page.getByRole("menuitem", { name: "Vložit krok pod" }).click();
      await page.waitForTimeout(300);
      const box = await page.getByRole("listbox").boundingBox();
      note(`[${w}] picker z menu karty: x=${box?.x} right=${box && box.x + box.width} (viewport ${w})`);
      await shot(page, `picker-z-menu-${w}`);
      await page.context().close();
    }
  },
  async dotyk() {
    const page = await open(768, 1024, { hasTouch: true, isMobile: true });
    await page.goto(`${URL}/#/p/${P}/scenare/ukazka`);
    await page.waitForTimeout(600);
    const small = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>("button, a, select, input, [role=radio]")]
      .filter((el) => el.offsetParent && getComputedStyle(el).visibility !== "hidden")
      .map((el) => ({ n: el.getAttribute("aria-label") ?? el.textContent?.trim().slice(0, 30), r: el.getBoundingClientRect() }))
      .filter((x) => x.r.width > 0 && (x.r.height < 44 || x.r.width < 24))
      .map((x) => `${x.n} ${Math.round(x.r.width)}×${Math.round(x.r.height)}`));
    note(`dotyk <44 px (editor):\n  ${small.join("\n  ")}`);
    await shot(page, "dotyk-editor", true);
    await page.context().close();
  },
};

const only = process.argv[2];
for (const [name, fn] of Object.entries(flows)) {
  if (only && !name.includes(only)) continue;
  note(`=== ${name}`);
  try { await fn(); } catch (e) { note(`!! ${name} selhal: ${(e as Error).message.split("\n").slice(0, 4).join(" / ")}`); }
}
await browser.close();
fs.writeFileSync(`${OUT}/log.txt`, log.join("\n") + "\n");
