import fs from "node:fs";
import path from "node:path";
import { expect, test } from "./fixtures";

test("Karta kroku: výběr, konektor a klávesnice nabídky", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  const card = page.locator('[data-step-card="napis"]');
  await card.click();
  await expect(card).toHaveAttribute("aria-pressed", "true");
  await expect(card).toHaveClass(/ring-2 ring-accent/);

  const add = page.getByTestId("add-after-napis");
  await add.locator("xpath=../..").hover();
  await expect(add).toHaveCSS("opacity", "1");
  await add.click();
  const picker = page.getByRole("listbox", { name: "Typ nového kroku" });
  await picker.press("j");
  await expect(picker.getByRole("option")).toHaveCount(1);
  await expect(picker.getByRole("option")).toContainText("jev");
  await picker.press("Enter");
  await expect(page.locator('[data-step-card="jev_1"]')).toBeVisible();
});

test("Scénáře: karta bez přípony a čárkovaný prázdný stav", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}`);
  const card = page.getByTestId("scenario-card-ukazka");
  await expect(card).toContainText("ukazka");
  await expect(card).not.toContainText("ukazka.yaml");
  await expect(page.getByRole("button", { name: "Nový scénář" })).toHaveCount(1);

  fs.rmSync(path.join(project.wf, "scenarios/ukazka.yaml"));
  await page.reload();
  await expect(page.getByTestId("scenario-card-ukazka")).toHaveCount(0);
  const empty = page.locator("li > button.border-dashed");
  await expect(empty).toBeVisible();
  await expect(empty).toContainText("Nový scénář");
});
