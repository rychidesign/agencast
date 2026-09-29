// Redesign V3 wave C: one header per section (G1–G4) and the tablet layout (G14).
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

const noOverflow = async (page: Page, w: number) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(w);

test("IC1 project sections: one h1, at most one Save, and Reload in ⋯", async ({ page, project }) => {
  const sections: [string, string, string[]][] = [
    ["", "Scenarios", ["New scenario"]],
    ["/agents", "Agents", ["New agent", "Save"]],
    ["/skills", "Skills", ["New skill"]],
    ["/runs", "Runs", []],
    ["/config", "Config", ["Save"]],
  ];
  for (const [path, title, buttons] of sections) {
    await page.goto(`/#/p/${project.name}${path}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText([title]);
    const header = page.locator("main header");
    for (const b of buttons) await expect(header.getByRole("button", { name: b })).toBeVisible();
    expect(await page.getByRole("button", { name: "Save" }).count()).toBeLessThanOrEqual(1);
    expect(await page.getByRole("radiogroup", { name: "View" }).count()).toBeLessThanOrEqual(1);
    await header.getByRole("button", { name: /^(More actions|Actions for .+)$/ }).click();
    await expect(page.getByRole("menuitem").first()).toHaveText("Reload");
    await page.keyboard.press("Escape");
  }
});

for (const w of [768, 1024]) {
  test(`IC2w${w} tablet: no overflow, the panel can be closed`, async ({ page, project }) => {
    await page.setViewportSize({ width: w, height: 900 });
    for (const path of ["", "/agents", "/runs", "/config"]) {
      await page.goto(`/#/p/${project.name}${path}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await noOverflow(page, w);
    }
    await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
    // below 1280 px the panel is a bottom sheet, at most 720 px wide on a tablet
    const panel = page.getByRole("dialog", { name: /STEP 1/ });
    await expect.poll(async () => {
      const b = (await panel.boundingBox())!;
      return b.y + b.height;
    }).toBe(900);
    const b = (await panel.boundingBox())!;
    expect(b.width).toBe(720);
    expect(b.x).toBe((w - 720) / 2);
    expect(b.y).toBeGreaterThanOrEqual(48);
    await expect(panel).toHaveCSS("border-top-left-radius", "16px");
    await panel.getByRole("button", { name: "Close" }).click();
    await expect(panel).toBeHidden();
    await noOverflow(page, w);
  });
}
