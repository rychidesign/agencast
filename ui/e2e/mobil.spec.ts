// Cesta C16 (docs/ui/uzivatelske-cesty.md) a vlna G: mobil 390 × 844 (iPhone 13), `pointer: coarse`.
// Lišta 56 px s FAB navigací, spodní sheety, běhy jako karty, nikde vodorovné přetečení.
import type { Locator, Page } from "@playwright/test";
import { expect, startRun, test, waitRun } from "./fixtures";

const W = 390, H = 844;
test.use({ viewport: { width: W, height: H }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });

const noOverflow = async (page: Page) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBe(0);
const minSide = async (target: Locator) => {
  const b = (await target.boundingBox())!;
  return Math.min(b.width, b.height);
};

test("G1 FAB navigace: nabídka nad tlačítkem, Esc, scrim a položka zavřou", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare`);
  const bar = page.locator("header").first();
  expect((await bar.boundingBox())!.height).toBe(56);
  await expect(page.getByRole("navigation", { name: "Části projektu" })).toHaveCount(0); // žádné vodorovné záložky
  const fab = page.getByRole("button", { name: "Navigace" });
  expect(await fab.boundingBox()).toMatchObject({ width: 56, height: 56 });
  const f = (await fab.boundingBox())!;
  expect(f.x + f.width).toBe(W - 16);
  expect(f.y + f.height).toBe(H - 16);
  await fab.tap();
  const menu = page.getByRole("dialog", { name: "Navigace" });
  await expect(menu).toBeVisible();
  expect((await menu.boundingBox())!.y + (await menu.boundingBox())!.height).toBeLessThan(f.y);
  await expect(menu.getByRole("link", { name: "Projekty" })).toBeFocused();
  const agents = menu.getByRole("link", { name: "Agenti" });
  expect((await agents.boundingBox())!.height).toBeCloseTo(48, 2);
  await expect(menu.getByTestId("spend-today")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expect(fab).toBeFocused();
  await fab.tap();
  await page.mouse.click(W - 10, H / 2);
  await expect(menu).toBeHidden();
  await fab.tap();
  await agents.tap();
  await expect(menu).toBeHidden();
  await expect(page).toHaveURL(/\/agenti/);
  await fab.tap();
  await page.evaluate((name) => { location.hash = `#/p/${name}/behy`; }, project.name);
  await expect(menu).toBeHidden();
  await page.goto("/#/");
  await expect(fab).toHaveCount(0);
  await page.goto("/#/x");
  await expect(fab).toHaveCount(0);
  await noOverflow(page);
});

test("C16 editor na mobilu: karta 80 px, panel kroku jako spodní sheet", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
  const napis = page.locator('[data-step-card="napis"]');
  await expect(napis).toBeVisible();
  expect((await napis.boundingBox())!.height).toBe(80);
  await noOverflow(page);
  // jen primární akce + ⋯; Uložit je v ⋯
  await expect(page.getByRole("button", { name: "Spustit", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Uložit" })).toBeHidden();
  await expect(page.getByRole("radiogroup", { name: "Zobrazení" })).toBeInViewport();
  const h1 = page.getByRole("heading", { level: 1 });
  expect(parseFloat(await h1.evaluate((el) => getComputedStyle(el.firstElementChild ?? el).fontSize))).toBe(24);

  // sloupec přes celou šířku (koš vně pilulky jen od 768 px, Smazat je v ⋯); cíle ≥ 44 px,
  // (+) v konektoru 40 px má dotykovou plochu 44 přes ::before
  await expect(page.getByRole("button", { name: "Smazat krok napis" })).toBeHidden();
  expect((await napis.boundingBox())!.width).toBe(W - 32);
  for (const target of [page.getByRole("button", { name: "Akce pro napis" }), page.getByRole("button", { name: "Další akce" })])
    expect(await minSide(target), await target.getAttribute("aria-label") ?? "").toBeGreaterThanOrEqual(44);
  const add = page.getByTestId("add-after-napis");
  const a = (await add.boundingBox())!;
  expect(await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest("[data-testid]")?.getAttribute("data-testid"),
    [a.x + a.width / 2, a.y - 1])).toBe("add-after-napis");

  await napis.tap();
  const sheet = page.getByRole("dialog", { name: /KROK 1/ });
  await expect(sheet).toBeVisible();
  await expect.poll(async () => (await sheet.boundingBox())!.y + (await sheet.boundingBox())!.height).toBe(H);
  const s = (await sheet.boundingBox())!;
  expect(s.x).toBe(0);
  expect(s.width).toBe(W);
  expect(s.y).toBeGreaterThanOrEqual(48);
  expect(s.height).toBeLessThan(H);
  await expect(sheet).toHaveCSS("border-top-left-radius", "16px");
  expect(await sheet.evaluate((el) => getComputedStyle(el).boxShadow)).not.toBe("none");
  expect(await minSide(sheet.getByRole("button", { name: "Zavřít" }))).toBeGreaterThanOrEqual(44);
  // fokus zůstává v sheetu
  for (let i = 0; i < 30; i++) await page.keyboard.press("Tab");
  expect(await sheet.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(napis).toBeFocused();
  await napis.tap();
  await sheet.getByRole("button", { name: "Zavřít" }).tap();
  await expect(sheet).toBeHidden();
  await expect(napis).toBeFocused();
  await napis.tap();
  await page.mouse.click(10, 10);
  await expect(sheet).toBeHidden();

  // spuštění z mobilu: sheet, pole 16 px, tlačítko na plnou šířku
  await page.getByRole("button", { name: "Spustit", exact: true }).tap();
  const run = page.getByRole("dialog", { name: "SPUSTIT BĚH" });
  await expect(run).toBeVisible();
  const tema = run.getByRole("textbox", { name: "tema" });
  expect(parseFloat(await tema.evaluate((el) => getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
  const form = (await run.locator("form").boundingBox())!;
  const submit = (await run.getByRole("button", { name: "Spustit dry-run" }).boundingBox())!;
  expect(Math.abs(submit.width - form.width)).toBeLessThanOrEqual(1);
  await noOverflow(page);
});

test("G2 běhy jako karty, agenti jako čipy, config — bez přetečení", async ({ page, project, server }) => {
  await page.goto(`/#/p/${project.name}/agenti`);
  const nav = (await page.getByRole("navigation", { name: "Agenti" }).boundingBox())!;
  const h2 = (await page.getByRole("heading", { name: "pisatel", level: 2 }).boundingBox())!;
  expect(nav.y + nav.height).toBeLessThanOrEqual(h2.y);
  expect(nav.height).toBeLessThanOrEqual(56);
  await noOverflow(page);

  const id = await startRun(server, project.name, "ukazka", { dry_run: true });
  await waitRun(server, project.name, id, ["dry_run"]);
  await page.goto(`/#/p/${project.name}/behy`);
  const row = page.getByTestId(`run-row-${id}`);
  await expect(row).toBeVisible();
  await expect(page.getByRole("columnheader").first()).toBeHidden();
  const region = page.getByRole("region", { name: "Běhy" });
  expect(await region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
  const card = (await row.boundingBox())!;
  expect(card.width).toBe(W - 32);
  // 1. řádek jméno + stav, 2. řádek run_id
  const name = (await row.getByRole("link").boundingBox())!;
  const runId = (await row.getByText(id, { exact: true }).boundingBox())!;
  expect(runId.y).toBeGreaterThan(name.y + name.height - 2);
  await noOverflow(page);

  await page.goto(`/#/p/${project.name}/behy/${id}`);
  await expect(page.getByRole("navigation", { name: "Části běhu" })).toBeVisible();
  await noOverflow(page);

  await page.goto(`/#/p/${project.name}/config`);
  await expect(page.getByTestId("config-editor-card")).toBeVisible();
  await noOverflow(page);
});
