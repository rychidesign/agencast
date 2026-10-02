// Journey C16 (docs/ui/user-journeys.md) and wave G: mobile 390 × 844 (iPhone 13), `pointer: coarse`.
// 56 px bar with FAB navigation, bottom sheets, runs as cards, no horizontal overflow anywhere.
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

test("G1 FAB navigation: menu above the button, Esc, scrim and an item close it", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios`);
  const bar = page.locator("header").first();
  expect((await bar.boundingBox())!.height).toBe(56);
  await expect(page.getByRole("navigation", { name: "Project sections" })).toHaveCount(0); // no horizontal tabs
  const fab = page.getByRole("button", { name: "Navigation" });
  expect(await fab.boundingBox()).toMatchObject({ width: 56, height: 56 });
  const f = (await fab.boundingBox())!;
  expect(f.x + f.width).toBe(W - 16);
  expect(f.y + f.height).toBe(H - 16);
  await fab.tap();
  const menu = page.getByRole("dialog", { name: "Navigation" });
  await expect(menu).toBeVisible();
  const m = (await menu.boundingBox())!; // one measurement: the menu grows when today's spend arrives
  expect(m.y + m.height).toBeLessThan(f.y);
  await expect(menu.getByRole("link", { name: "Projects" })).toBeFocused();
  const agents = menu.getByRole("link", { name: "Agents" });
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
  await expect(page).toHaveURL(/\/agents/);
  await fab.tap();
  await page.evaluate((name) => { location.hash = `#/p/${name}/runs`; }, project.name);
  await expect(menu).toBeHidden();
  // the FAB is on every page: it holds the language switch (projects page: nothing else; 404: the way back)
  await page.goto("/#/");
  await fab.tap();
  await expect(menu.getByRole("combobox", { name: "Language" })).toBeFocused();
  await expect(menu.getByRole("link")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.goto("/#/x");
  await fab.tap();
  await expect(menu.getByRole("link", { name: "Projects" })).toBeFocused();
  await page.keyboard.press("Escape");
  await noOverflow(page);
});

test("C16 editor on mobile: card with the type line and the name, step panel as a bottom sheet", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
  const write = page.locator('[data-step-card="write"]');
  await expect(write).toBeVisible();
  expect((await write.boundingBox())!.height).toBe(72); // type · agent, `n. id`; no prompt
  await noOverflow(page);
  // only the primary action + ⋯; Save is in ⋯
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toBeHidden();
  await expect(page.getByRole("radiogroup", { name: "View" })).toBeInViewport();
  const h1 = page.getByRole("heading", { level: 1 });
  expect(parseFloat(await h1.evaluate((el) => getComputedStyle(el.firstElementChild ?? el).fontSize))).toBe(24);

  // full-width column (Delete is in ⋯); targets ≥ 44 px,
  // the 40 px (+) in the connector has a 44 px touch area via ::before
  await expect(page.getByRole("button", { name: "Delete step write" })).toHaveCount(0);
  expect((await write.boundingBox())!.width).toBe(W - 32);
  for (const target of [page.getByRole("button", { name: "Actions for write" }), page.getByRole("button", { name: "More actions" })])
    expect(await minSide(target), await target.getAttribute("aria-label") ?? "").toBeGreaterThanOrEqual(44);
  const add = page.getByTestId("add-after-write");
  const a = (await add.boundingBox())!;
  expect(await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest("[data-testid]")?.getAttribute("data-testid"),
    [a.x + a.width / 2, a.y - 1])).toBe("add-after-write");

  await write.tap();
  const sheet = page.getByRole("dialog", { name: /STEP 1/ });
  await expect(sheet).toBeVisible();
  await expect.poll(async () => (await sheet.boundingBox())!.y + (await sheet.boundingBox())!.height).toBe(H);
  const s = (await sheet.boundingBox())!;
  expect(s.x).toBe(0);
  expect(s.width).toBe(W);
  expect(s.y).toBeGreaterThanOrEqual(48);
  expect(s.height).toBeLessThan(H);
  await expect(sheet).toHaveCSS("border-top-left-radius", "16px");
  expect(await sheet.evaluate((el) => getComputedStyle(el).boxShadow)).not.toBe("none");
  expect(await minSide(sheet.getByRole("button", { name: "Close" }))).toBeGreaterThanOrEqual(44);
  // focus stays in the sheet
  for (let i = 0; i < 30; i++) await page.keyboard.press("Tab");
  expect(await sheet.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(write).toBeFocused();
  await write.tap();
  await sheet.getByRole("button", { name: "Close" }).tap();
  await expect(sheet).toBeHidden();
  await expect(write).toBeFocused();
  await write.tap();
  await page.mouse.click(10, 10);
  await expect(sheet).toBeHidden();

  // starting from mobile: sheet, 16 px field, full-width button
  await page.getByRole("button", { name: "Run", exact: true }).tap();
  const run = page.getByRole("dialog", { name: "START RUN" });
  await expect(run).toBeVisible();
  const topic = run.getByRole("textbox", { name: "topic" });
  expect(parseFloat(await topic.evaluate((el) => getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
  const form = (await run.locator("form").boundingBox())!;
  const submit = (await run.getByRole("button", { name: "Start dry run" }).boundingBox())!;
  expect(Math.abs(submit.width - form.width)).toBeLessThanOrEqual(1);
  await noOverflow(page);
});

test("G2 runs as cards, agents as cards with a sheet, config — no overflow", async ({ page, project, server }) => {
  await page.goto(`/#/p/${project.name}/agents`);
  // below 1100 px only full-width cards; the editor opens on tap, in a bottom sheet
  const agent = page.getByTestId("file-card-writer");
  await expect(agent).toContainText("Write short texts");
  await expect(agent).toContainText(/ — \S+\/\S+/); // model: alias — id from config.yaml
  expect((await agent.boundingBox())!.width).toBe(W - 32);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await noOverflow(page);
  await agent.getByRole("link").tap();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toContainText("writer");
  await expect(sheet.getByTestId("agent-editor-card")).toBeVisible();
  await expect(sheet.getByRole("button", { name: "Save" })).toBeVisible();
  await expect(sheet.getByRole("button", { name: "Actions for writer" })).toBeVisible();
  await sheet.getByRole("button", { name: "Close" }).tap();
  await expect(page).toHaveURL(/\/agents$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  const id = await startRun(server, project.name, "demo", { dry_run: true });
  await waitRun(server, project.name, id, ["dry_run"]);
  await page.goto(`/#/p/${project.name}/runs`);
  const row = page.getByTestId(`run-row-${id}`);
  await expect(row).toBeVisible();
  await expect(page.getByRole("columnheader").first()).toBeHidden();
  const region = page.getByRole("region", { name: "Runs" });
  expect(await region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
  const card = (await row.boundingBox())!;
  expect(card.width).toBe(W - 32);
  // 1st line name + status, 2nd line run_id
  const name = (await row.getByRole("link").boundingBox())!;
  const runId = (await row.getByText(id, { exact: true }).boundingBox())!;
  expect(runId.y).toBeGreaterThan(name.y + name.height - 2);
  await noOverflow(page);

  await page.goto(`/#/p/${project.name}/runs/${id}`);
  await expect(page.getByRole("navigation", { name: "Run sections" })).toBeVisible();
  await noOverflow(page);

  await page.goto(`/#/p/${project.name}/config`);
  await expect(page.getByTestId("config-editor-card")).toBeVisible();
  await noOverflow(page);
});
