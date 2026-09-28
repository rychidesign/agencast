import { expect, test } from "./fixtures";

async function menuInsideViewport(page: import("@playwright/test").Page) {
  const menu = page.getByRole("menu");
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
  for (const item of await menu.getByRole("menuitem").all()) expect((await item.boundingBox())!.height).toBe(40);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(page.viewportSize()!.width);
}

for (const [width, code] of [[390, "N7"], [1440, "N8"]] as const) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height: 844 } });

    test(`${code} ⋯ karta scénáře a hlavička editoru zůstávají ve viewportu`, async ({ page, project }) => {
      await page.goto(`/#/p/${project.name}/scenare`);
      await page.getByRole("button", { name: "Akce pro ukazka" }).click();
      await menuInsideViewport(page);
      await page.keyboard.press("Escape");

      await page.goto(`/#/p/${project.name}/scenare/ukazka`);
      await page.getByRole("button", { name: "Další akce" }).click();
      await menuInsideViewport(page);
    });
  });
}
