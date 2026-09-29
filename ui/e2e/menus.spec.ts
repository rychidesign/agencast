import { SLOW, expect, startRun, test } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";

const shots = "/tmp/agencast-l";
mkdirSync(shots, { recursive: true });

function watchErrors(page: import("@playwright/test").Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  return errors;
}

async function cleanPage(page: import("@playwright/test").Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(page.viewportSize()!.width);
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(axe.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
}

async function menuInsideViewport(page: import("@playwright/test").Page) {
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  const b = (await menu.boundingBox())!;
  expect(b.x).toBeGreaterThanOrEqual(12);
  expect(b.x + b.width).toBeLessThanOrEqual(page.viewportSize()!.width - 12);
  expect(b.y).toBeGreaterThanOrEqual(12);
  expect(b.y + b.height).toBeLessThanOrEqual(page.viewportSize()!.height - 12);
  const css = await menu.evaluate((el) => {
    const s = getComputedStyle(el);
    return { border: s.borderTopWidth, outline: s.outlineWidth, shadow: s.boxShadow };
  });
  expect(css.border).toBe("0px");
  expect(css.outline).toBe("0px");
  expect(css.shadow).toContain("40px");
  for (const item of await menu.getByRole("menuitem").all()) expect((await item.boundingBox())!.height).toBeCloseTo(40, 2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(page.viewportSize()!.width);
  expect(await menu.evaluate((el) => el.parentElement === document.body)).toBe(true);
}

for (const [width, height, code] of [[390, 844, "N7"], [768, 1024, "N9"], [1024, 768, "N10"], [1440, 900, "N8"]] as const) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height }, hasTouch: width === 390 });

    test(`${code} ⋯ scenario card and editor header stay in the viewport`, async ({ page, project }) => {
      await page.goto(`/#/p/${project.name}/scenarios`);
      await page.getByRole("button", { name: "Actions for demo" }).click();
      await menuInsideViewport(page);
      await page.keyboard.press("Escape");

      await page.goto(`/#/p/${project.name}/scenarios/demo`);
      await page.getByRole("button", { name: "More actions" }).click();
      await menuInsideViewport(page);
    });

    test(`${code}B ⋯ step, connector gaps and scroll`, async ({ page, project }) => {
      const errors = watchErrors(page);
      await page.goto(`/#/p/${project.name}/scenarios/demo`);
      const plus = page.getByTestId("add-after-write");
      const row = plus.locator("xpath=../..");
      const [r, b] = await Promise.all([row.boundingBox(), plus.boundingBox()]);
      expect(r!.height).toBe(48);
      expect(b!.height).toBe(40);
      expect(b!.y - r!.y).toBe(4);
      expect(r!.y + r!.height - b!.y - b!.height).toBe(4);
      if (width === 390 || width === 1440) await page.screenshot({ path: `${shots}/${width}-connectors.png` });
      const trigger = page.getByRole("button", { name: "Actions for write" });
      await trigger.click();
      await menuInsideViewport(page);
      const remove = page.getByRole("menuitem", { name: "Delete" });
      await expect(remove).toHaveCSS("color", "rgb(255, 143, 157)");
      expect((await remove.textContent())!.includes("(")).toBe(false);
      const hint = remove.locator("span");
      await expect(hint).toHaveText("Del");
      if (width === 390) await expect(hint).toBeHidden();
      if (width === 1440) {
        await expect(hint).toBeVisible();
        const [itemBox, hintBox] = await Promise.all([remove.boundingBox(), hint.boundingBox()]);
        expect(hintBox!.x).toBeGreaterThan(itemBox!.x + itemBox!.width / 2);
      }
      await cleanPage(page);
      await page.screenshot({ path: `${shots}/${width}-step-menu.png` });
      await page.evaluate(() => window.scrollBy(0, 300));
      if (await page.getByRole("menu").count()) {
        const [a, m] = await Promise.all([trigger.boundingBox(), page.getByRole("menu").boundingBox()]);
        expect(Math.min(Math.abs(m!.y - a!.y - a!.height), Math.abs(a!.y - m!.y - m!.height))).toBeLessThanOrEqual(16);
      }
      expect(errors).toEqual([]);
    });
  });
}

test.describe("sheet and nested fields", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("field is nested, the grouping card is group, the checkbox has both states", async ({ page, project }) => {
    const errors = watchErrors(page);
    await page.goto(`/#/p/${project.name}/scenarios/demo?step=_header`);
    const sheet = page.getByRole("dialog");
    await expect(sheet).toHaveCSS("opacity", "1");
    const field = sheet.getByRole("textbox", { name: "Default value of topic" });
    const colors = await field.evaluate((el) => [getComputedStyle(el).backgroundColor, getComputedStyle(el.closest("li.bg-group")!).backgroundColor]);
    expect(colors).toEqual(["rgb(13, 25, 42)", "rgb(19, 32, 50)"]);
    const cb = sheet.getByRole("checkbox", { name: "required" });
    await expect(cb).toHaveCSS("background-color", "rgb(49, 69, 95)");
    await page.screenshot({ path: `${shots}/390-header-sheet.png` });
    await cb.check();
    await expect(cb).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await page.screenshot({ path: `${shots}/390-header-checkbox-checked.png` });
    await cleanPage(page);
    expect(errors).toEqual([]);
  });
});

test.describe("validation popover", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("N14 a project error opens in body inside the viewport", async ({ page, project }) => {
    const errors = watchErrors(page);
    project.write("scenarios/demo.yaml", project.read("scenarios/demo.yaml").replace("agent: writer", "agent: missing-agent"));
    await page.goto(`/#/p/${project.name}/scenarios`);
    await page.getByTestId("validation-popover-trigger").click();
    const popup = page.getByRole("dialog", { name: /error/ });
    const b = (await popup.boundingBox())!;
    expect(b.x).toBeGreaterThanOrEqual(12);
    expect(b.x + b.width).toBeLessThanOrEqual(378);
    expect(b.y).toBeGreaterThanOrEqual(12);
    expect(b.y + b.height).toBeLessThanOrEqual(832);
    expect(await popup.evaluate((el) => el.parentElement === document.body)).toBe(true);
    await page.screenshot({ path: `${shots}/390-validation-popover.png` });
    await cleanPage(page);
    await page.keyboard.press("Escape");
    await expect(popup).toBeHidden();
    expect(errors).toEqual([]);
  });
});

test.describe("tablet sheet", () => {
  test.use({ viewport: { width: 768, height: 1024 } });
  test("sheet and popover stay in the viewport", async ({ page, project }) => {
    const errors = watchErrors(page);
    await page.goto(`/#/p/${project.name}/scenarios/demo?step=_header`);
    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    // The header sheet has no step card; its ⋯ is available only after closing the sheet.
    await page.screenshot({ path: `${shots}/768-header-sheet.png` });
    await sheet.getByRole("button", { name: "Close" }).click();
    await page.getByRole("button", { name: "Actions for write" }).click();
    await menuInsideViewport(page);
    await cleanPage(page);
    expect(errors).toEqual([]);
  });
});

test.describe("branch connector", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("N12 (+) has 4 px between branch cards too", async ({ page, project }) => {
    const errors = watchErrors(page);
    project.write("scenarios/demo.yaml", project.read("scenarios/demo.yaml").replace("  - id: result", `  - id: parallel_1
    parallel:
      a:
        - id: first
          ask: { agent: writer, prompt: first }
        - id: second
          ask: { agent: writer, prompt: second }
  - id: result`));
    await page.goto(`/#/p/${project.name}/scenarios/demo`);
    const plus = page.getByTestId("branch-a").getByTestId("add-after-first");
    const [row, button] = await Promise.all([plus.locator("xpath=../..").boundingBox(), plus.boundingBox()]);
    expect(row!.height).toBe(48);
    expect(button!.y - row!.y).toBe(4);
    expect(row!.y + row!.height - button!.y - button!.height).toBe(4);
    await page.screenshot({ path: `${shots}/390-branch-connectors.png` });
    await cleanPage(page);
    expect(errors).toEqual([]);
  });
});

test.describe("desktop fields and controls", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test("N11 Config, Agent and RunPanel", async ({ page, project }) => {
    const errors = watchErrors(page);
    mkdirSync(`${project.wf}/skills/research`, { recursive: true });
    project.write("skills/research/SKILL.md", "---\nname: research\ndescription: Research\n---\nProcedure.\n");
    await page.goto(`/#/p/${project.name}/config`);
    const field = page.locator("li.bg-group input").first();
    await expect(field).toHaveCSS("background-color", "rgb(13, 25, 42)");
    await expect(field.locator("xpath=ancestor::li[1]")).toHaveCSS("background-color", "rgb(19, 32, 50)");
    await cleanPage(page);
    await page.screenshot({ path: `${shots}/1440-config.png` });

    await page.goto(`/#/p/${project.name}/agents/writer`);
    await expect(page.locator("textarea").first()).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    const skill = page.getByTestId("agent-editor-card").getByRole("checkbox", { name: /research/ });
    await expect(skill).toHaveCSS("background-color", "rgb(49, 69, 95)");
    await page.screenshot({ path: `${shots}/1440-agent-checkbox-unchecked.png` });
    await skill.check();
    await expect(skill).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await cleanPage(page);
    await page.screenshot({ path: `${shots}/1440-agent-checkbox-checked.png` });

    await page.goto(`/#/p/${project.name}/scenarios/demo`);
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const dry = page.getByRole("radio", { name: /Dry run/ });
    const live = page.getByRole("radio", { name: /Live run/ });
    await expect(dry).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await expect(live).toHaveCSS("background-color", "rgb(49, 69, 95)");
    await page.screenshot({ path: `${shots}/1440-runpanel-radio-dry.png` });
    await live.check();
    await expect(live).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await cleanPage(page);
    await page.screenshot({ path: `${shots}/1440-runpanel-radio-live.png` });
    expect(errors).toEqual([]);
  });

  test("N13 follow run has both states", async ({ page, project, server }) => {
    const errors = watchErrors(page);
    project.write("scenarios/slow.yaml", SLOW);
    const id = await startRun(server, project.name, "slow");
    await page.goto(`/#/p/${project.name}/runs/${id}`);
    const follow = page.getByRole("checkbox", { name: "follow run" });
    await expect(follow).toHaveCSS("background-color", "rgb(49, 69, 95)");
    await page.screenshot({ path: `${shots}/1440-run-follow-unchecked.png` });
    await follow.check();
    await expect(follow).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await page.screenshot({ path: `${shots}/1440-run-follow-checked.png` });
    await cleanPage(page);
    expect(errors).toEqual([]);
  });
});
