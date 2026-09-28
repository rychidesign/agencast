import { DLOUHY, expect, startRun, test } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";

const shots = "/tmp/agencast-i";
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
    test.use({ viewport: { width, height } });

    test(`${code} ⋯ karta scénáře a hlavička editoru zůstávají ve viewportu`, async ({ page, project }) => {
      await page.goto(`/#/p/${project.name}/scenare`);
      await page.getByRole("button", { name: "Akce pro ukazka" }).click();
      await menuInsideViewport(page);
      await page.keyboard.press("Escape");

      await page.goto(`/#/p/${project.name}/scenare/ukazka`);
      await page.getByRole("button", { name: "Další akce" }).click();
      await menuInsideViewport(page);
    });

    test(`${code}B ⋯ krok, mezery konektoru a scroll`, async ({ page, project }) => {
      const errors = watchErrors(page);
      await page.goto(`/#/p/${project.name}/scenare/ukazka`);
      const plus = page.getByTestId("add-after-napis");
      const row = plus.locator("xpath=../..");
      const [r, b] = await Promise.all([row.boundingBox(), plus.boundingBox()]);
      expect(r!.height).toBe(48);
      expect(b!.height).toBe(40);
      expect(b!.y - r!.y).toBe(4);
      expect(r!.y + r!.height - b!.y - b!.height).toBe(4);
      if (width === 390 || width === 1440) await page.screenshot({ path: `${shots}/${width}-connectors.png` });
      const trigger = page.getByRole("button", { name: "Akce pro napis" });
      await trigger.click();
      await menuInsideViewport(page);
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

test.describe("sheet a vnořená pole", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("pole se liší od karty, checkbox má oba stavy", async ({ page, project }) => {
    const errors = watchErrors(page);
    await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=_hlavicka`);
    const sheet = page.getByRole("dialog");
    const field = sheet.getByRole("textbox", { name: "Výchozí hodnota tema" });
    const colors = await field.evaluate((el) => [getComputedStyle(el).backgroundColor, getComputedStyle(el.closest("li.bg-nested")!).backgroundColor]);
    expect(colors).toEqual(["rgb(37, 59, 80)", "rgb(13, 25, 42)"]);
    const cb = sheet.getByRole("checkbox", { name: "povinný" });
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
  test("N14 chyba projektu se otevře v body uvnitř viewportu", async ({ page, project }) => {
    const errors = watchErrors(page);
    project.write("scenarios/ukazka.yaml", project.read("scenarios/ukazka.yaml").replace("agent: pisatel", "agent: neexistuje"));
    await page.goto(`/#/p/${project.name}/scenare`);
    await page.getByTestId("validation-popover-trigger").click();
    const popup = page.getByRole("dialog", { name: /chyb/ });
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
  test("sheet a popover zůstávají ve viewportu", async ({ page, project }) => {
    const errors = watchErrors(page);
    await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=_hlavicka`);
    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    // Hlavičkový sheet nemá kartu kroku; její ⋯ je dostupné až po zavření sheetu.
    await page.screenshot({ path: `${shots}/768-header-sheet.png` });
    await sheet.getByRole("button", { name: "Zavřít" }).click();
    await page.getByRole("button", { name: "Akce pro napis" }).click();
    await menuInsideViewport(page);
    await cleanPage(page);
    expect(errors).toEqual([]);
  });
});

test.describe("branch connector", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("N12 (+) má 4 px i mezi kartami větve", async ({ page, project }) => {
    const errors = watchErrors(page);
    project.write("scenarios/ukazka.yaml", project.read("scenarios/ukazka.yaml").replace("  - id: vystup", `  - id: parallel_1
    parallel:
      a:
        - id: prvni
          ask: { agent: pisatel, prompt: prvni }
        - id: druhy
          ask: { agent: pisatel, prompt: druhy }
  - id: vystup`));
    await page.goto(`/#/p/${project.name}/scenare/ukazka`);
    const plus = page.getByTestId("branch-a").getByTestId("add-after-prvni");
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
  test("N11 Config, Agent a RunPanel", async ({ page, project }) => {
    const errors = watchErrors(page);
    mkdirSync(`${project.wf}/skills/pruzkum`, { recursive: true });
    project.write("skills/pruzkum/SKILL.md", "---\nname: pruzkum\ndescription: Průzkum\n---\nPostup.\n");
    await page.goto(`/#/p/${project.name}/config`);
    const field = page.locator("li.bg-nested input").first();
    await expect(field).toHaveCSS("background-color", "rgb(37, 59, 80)");
    await cleanPage(page);
    await page.screenshot({ path: `${shots}/1440-config.png` });

    await page.goto(`/#/p/${project.name}/agenti/pisatel`);
    const skill = page.getByTestId("agent-editor-card").getByRole("checkbox", { name: /pruzkum/ });
    await expect(skill).toHaveCSS("background-color", "rgb(49, 69, 95)");
    await page.screenshot({ path: `${shots}/1440-agent-checkbox-unchecked.png` });
    await skill.check();
    await expect(skill).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await cleanPage(page);
    await page.screenshot({ path: `${shots}/1440-agent-checkbox-checked.png` });

    await page.goto(`/#/p/${project.name}/scenare/ukazka`);
    await page.getByRole("button", { name: "Spustit", exact: true }).click();
    const dry = page.getByRole("radio", { name: /Dry-run/ });
    const live = page.getByRole("radio", { name: /Ostrý běh/ });
    await expect(dry).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await expect(live).toHaveCSS("background-color", "rgb(49, 69, 95)");
    await page.screenshot({ path: `${shots}/1440-runpanel-radio-dry.png` });
    await live.check();
    await expect(live).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await cleanPage(page);
    await page.screenshot({ path: `${shots}/1440-runpanel-radio-live.png` });
    expect(errors).toEqual([]);
  });

  test("N13 sledovat běh má oba stavy", async ({ page, project, server }) => {
    const errors = watchErrors(page);
    project.write("scenarios/dlouhy.yaml", DLOUHY);
    const id = await startRun(server, project.name, "dlouhy");
    await page.goto(`/#/p/${project.name}/behy/${id}`);
    const follow = page.getByRole("checkbox", { name: "sledovat běh" });
    await expect(follow).toHaveCSS("background-color", "rgb(49, 69, 95)");
    await page.screenshot({ path: `${shots}/1440-run-follow-unchecked.png` });
    await follow.check();
    await expect(follow).toHaveCSS("background-color", "rgb(210, 228, 250)");
    await page.screenshot({ path: `${shots}/1440-run-follow-checked.png` });
    await cleanPage(page);
    expect(errors).toEqual([]);
  });
});
