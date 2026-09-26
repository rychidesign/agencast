// Cesta C16 (docs/ui/uzivatelske-cesty.md): mobilní šířka 375 px, panel jako list, `pointer: coarse`.
import type { Page } from "@playwright/test";
import { expect, startRun, test, waitRun } from "./fixtures";

test.use({ viewport: { width: 375, height: 667 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });

const noOverflow = async (page: Page) => expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);

test("C16 mobilní šířka 375 px (panel jako list)", async ({ page, project, server }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
  const napis = page.locator('[data-step-card="napis"]');
  await expect(napis).toBeVisible();
  await noOverflow(page);
  const save = await page.getByRole("button", { name: "Uložit" }).boundingBox();
  expect(save!.x + save!.width).toBeLessThanOrEqual(375);
  await expect(page.getByRole("radiogroup", { name: "Zobrazení" })).toBeInViewport();

  await napis.tap();
  const panel = page.getByRole("complementary");
  const box = (await panel.locator("xpath=..").boundingBox())!;
  expect(Math.abs(box.y + box.height - (667 - 16))).toBeLessThanOrEqual(2);
  expect(box.height).toBeLessThanOrEqual(667 * 0.7 + 1);
  await panel.getByRole("button", { name: "Zavřít" }).tap();
  await expect(panel).toBeHidden();

  // dotyk: koš trvale ztlumeně, cíle ≥ 44 px
  const trash = page.getByRole("button", { name: "Smazat krok napis" });
  await expect(trash).toHaveCSS("opacity", "1"); // prvek sám; ztlumení nese obal ovládání
  await expect(trash.locator("xpath=..")).toHaveCSS("opacity", "0.6");
  for (const target of [trash, page.getByRole("button", { name: "Akce pro napis" }), page.getByTestId("add-after-napis"), page.getByRole("button", { name: "Uložit" })]) {
    const b = (await target.boundingBox())!;
    expect(Math.min(b.width, b.height), await target.getAttribute("aria-label") ?? "Uložit").toBeGreaterThanOrEqual(44);
  }
  await noOverflow(page);

  // seznam agentů nad editorem, tabulka běhů ve scroll kontejneru
  await page.goto(`/#/p/${project.name}/agenti`);
  const nav = (await page.getByRole("navigation", { name: "Agenti" }).boundingBox())!;
  const h2 = (await page.getByRole("heading", { name: "pisatel", level: 2 }).boundingBox())!;
  expect(nav.y + nav.height).toBeLessThanOrEqual(h2.y);
  await noOverflow(page);
  const id = await startRun(server, project.name, "ukazka", { dry_run: true });
  await waitRun(server, project.name, id, ["dry_run"]);
  await page.goto(`/#/p/${project.name}/behy`);
  await expect(page.getByTestId(`run-row-${id}`)).toBeAttached();
  await noOverflow(page);
  const region = page.getByRole("region", { name: "Běhy" });
  expect(await region.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);

  // spuštění z mobilu: panel jako list, pole 16 px, tlačítko na plnou šířku
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: "Spustit", exact: true }).tap();
  const run = page.getByRole("complementary");
  await expect(run).toContainText("SPUSTIT BĚH");
  const tema = run.getByRole("textbox", { name: "tema" });
  expect(parseFloat(await tema.evaluate((el) => getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
  const form = (await run.locator("form").boundingBox())!;
  const submit = (await run.getByRole("button", { name: "Spustit dry-run" }).boundingBox())!;
  expect(Math.abs(submit.width - form.width)).toBeLessThanOrEqual(1);
});
