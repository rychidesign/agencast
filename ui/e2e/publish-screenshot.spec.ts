// Refresh the README image: E2E_PORT=29990 npx playwright test -c e2e/playwright.config.ts publish-screenshot
import fs from "node:fs";
import path from "node:path";
import { test, expect } from "./fixtures";

test("Lumen editor for README", async ({ page, project }) => {
  const repo = path.resolve(import.meta.dirname, "../..");
  fs.cpSync(path.join(repo, "examples/showcase/workflows"), project.wf, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/#/p/${project.name}/scenarios/ig-post?step=copy`);
  await expect(page.locator('[data-step-card="copy"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const file = path.join(repo, "docs/ui/screenshots/editor.png");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  await page.screenshot({ path: file, animations: "disabled" });
  expect(fs.statSync(file).size).toBeLessThan(400_000);
});
