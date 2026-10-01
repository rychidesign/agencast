import fs from "node:fs";
import path from "node:path";
import { expect, startRun, test, waitRun } from "./fixtures";

test("Step card: selection, connector and menu keyboard", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  const card = page.locator('[data-step-card="write"]');
  await card.click();
  await expect(card).toHaveAttribute("aria-pressed", "true");
  await expect(card).toHaveClass(/bg-surface-active/);
  await expect(card).not.toHaveClass(/ring-1/); // .pen: the selected card only by its fill

  const add = page.getByTestId("add-after-write");
  await add.locator("xpath=../..").hover();
  await expect(add).toHaveCSS("opacity", "1");
  await add.click();
  const picker = page.getByRole("listbox", { name: "New step type" });
  await picker.press("j");
  await expect(picker.getByRole("option")).toHaveCount(1);
  await expect(picker.getByRole("option")).toContainText("jev");
  await picker.press("Enter");
  await expect(page.locator('[data-step-card="jev_1"]')).toBeVisible();
});

test("Editor: the panel is a drawer over the full height on the right, the page stays beside it", async ({ page, project }) => {
  project.write("scenarios/tutorial-03-exercise.yaml", fs.readFileSync(path.resolve(import.meta.dirname, "../../examples/tutorial/workflows/scenarios/tutorial-03-exercise.yaml"), "utf8"));
  for (const agent of ["tutorial-namer", "tutorial-slogan-writer"])
    project.write(`agents/${agent}.md`, fs.readFileSync(path.resolve(import.meta.dirname, `../../examples/tutorial/workflows/agents/${agent}.md`), "utf8"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/p/${project.name}/scenarios/tutorial-03-exercise?step=_header`);
  const header = page.locator("main header").first();
  const card = page.locator('[data-step-card=""]');
  const panel = page.getByRole("complementary");
  await expect(panel).toBeVisible();
  await expect(header).toContainText("Comes up with a name");
  await page.evaluate(() => document.fonts.ready);
  // the drawer covers the right edge from top to bottom; the header actions and the column stay left of it
  const drawer = async (width: number) => {
    await expect.poll(async () => {
      const p = (await panel.boundingBox())!;
      const more = (await page.getByRole("button", { name: "More actions" }).boundingBox())!;
      const col = (await page.getByRole("region", { name: "Scenario steps" }).boundingBox())!;
      return [Math.round(p.x + p.width), Math.round(p.y), Math.round(p.height), more.x + more.width <= p.x, col.x + col.width <= p.x];
    }).toEqual([width, 0, 900, true, true]);
  };
  await expect(card).toHaveClass(/ring-inset ring-1/);
  const slot = panel.locator("xpath=..");
  fs.mkdirSync("/tmp/agencast-l", { recursive: true });
  await drawer(1440);
  await expect(slot).toHaveCSS("position", "fixed");
  expect(await slot.evaluate((el) => getComputedStyle(el).boxShadow)).toContain("160px");
  await page.screenshot({ path: "/tmp/agencast-l/1440-header.png" });
  await page.locator('[data-step-card="stop"]').click();
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  for (const width of [1440, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await drawer(width);
    expect((await slot.boundingBox())!.width).toBeCloseTo(440, 0);
    await page.screenshot({ path: `/tmp/agencast-l/${width}-step-3.png` });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('[data-step-card="propose"]').click();
  for (const name of ["Condition", "Reliability", "Step details"])
    await panel.getByRole("button", { name: new RegExp(name) }).click();
  // a long panel scrolls inside, the header of the panel stays
  const body = panel.locator(":scope > div").last();
  await expect.poll(() => body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, document.scrollingElement!.scrollHeight));
  await drawer(1440);
  await page.screenshot({ path: "/tmp/agencast-l/1440-long-panel-bottom.png" });
  // cards stay clickable (not modal); closing gives the width back to the page
  await page.locator('[data-step-card="stop"]').click();
  await expect(panel).toContainText("stop");
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--drawer-w"))).toBe("");
  await expect(page.getByRole("region", { name: "Scenario steps" }).getByRole("button", { name: /^Delete step / })).toHaveCount(0);
});

test("Run detail: the step panel is a 520 drawer on the right", async ({ page, project, server }) => {
  const id = await startRun(server, project.name, "demo", { inputs: { topic: "coffee" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/p/${project.name}/runs/${id}?step=write`);
  const panel = page.getByRole("complementary");
  await expect(panel).toBeVisible();
  await expect.poll(async () => {
    const p = (await panel.boundingBox())!;
    return [Math.round(p.x + p.width), Math.round(p.y), Math.round(p.height), Math.round(p.width)];
  }).toEqual([1440, 0, 900, 520]);
  expect((await page.getByRole("link", { name: "Open scenario" }).boundingBox())!.x).toBeLessThan((await panel.boundingBox())!.x);
  await page.screenshot({ path: "/tmp/agencast-l/1440-run-step.png" });
});

test("Scenarios: card without extension and a dashed empty state", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}`);
  const card = page.getByTestId("scenario-card-demo");
  await expect(card).toContainText("demo");
  await expect(card).not.toContainText("demo.yaml");
  await expect(page.getByRole("button", { name: "New scenario" })).toHaveCount(1);

  fs.rmSync(path.join(project.wf, "scenarios/demo.yaml"));
  await page.reload();
  await expect(page.getByTestId("scenario-card-demo")).toHaveCount(0);
  const empty = page.locator("li > button.border-dashed");
  await expect(empty).toBeVisible();
  await expect(empty).toContainText("New scenario");
});

test("KV6 fidelity: 72 px pill, 40 px circle with the type icon, type line mono 11 lowercase, `n. id` name not mono, ⋯ inside", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  const card = page.locator('[data-step-card="write"]');
  expect((await card.boundingBox())!.height).toBeCloseTo(72, 0);
  const badge = card.locator(".size-10.rounded-full");
  expect((await badge.boundingBox())!.width).toBeCloseTo(40, 0);
  const typeLine = card.getByText("ask · writer");
  await expect(typeLine).toHaveCSS("font-size", "11px");
  await expect(typeLine).not.toHaveCSS("text-transform", "uppercase");
  const name = card.getByText("1. write");
  await expect(name).toHaveCSS("font-size", "15px");
  expect(await name.evaluate((el) => getComputedStyle(el).fontFamily)).not.toMatch(/mono/i);
  // ⋯ centered on the pill
  const dots = (await page.getByRole("button", { name: "Actions for write" }).boundingBox())!;
  const pill = (await card.boundingBox())!;
  expect(dots.y + dots.height / 2).toBeCloseTo(pill.y + pill.height / 2, 0);
  // ⋯ sits inside the pill on the right
  const menu = (await page.getByRole("button", { name: "Actions for write" }).boundingBox())!;
  const box = (await card.boundingBox())!;
  expect(menu.x + menu.width).toBeLessThanOrEqual(box.x + box.width);
  // column 676 beside the 440 drawer at 1440 px, never under it
  await page.setViewportSize({ width: 1440, height: 900 });
  await card.click();
  const panel = (await page.getByRole("complementary").boundingBox())!;
  const col = (await card.boundingBox())!;
  expect(panel.width).toBeCloseTo(440, 0);
  expect(col.width).toBeCloseTo(676, 0);
  expect(panel.x - (col.x + col.width)).toBeGreaterThanOrEqual(28);
});

test("KV5 fidelity (measured from .pen): scenario card r14 p24 h. 292, plain type icons without arrows, mono meta, Open ↗", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}`);
  const card = page.getByTestId("scenario-card-demo");
  await expect(card).toHaveCSS("border-radius", "14px");
  await expect(card).toHaveCSS("padding-top", "24px");
  expect((await card.boundingBox())!.height).toBeGreaterThanOrEqual(292);
  const chain = card.getByRole("list", { name: /Step types/ });
  await expect(chain).not.toContainText("→");
  await expect(chain.locator(".rounded-full")).toHaveCount(0);
  await expect(card.getByRole("heading", { level: 2 })).toHaveCSS("font-size", "18px");
  await expect(card.getByText("2 steps · 1 agent")).toHaveCSS("font-family", /JetBrains Mono/);
  await expect(card).toContainText("Open");
});
