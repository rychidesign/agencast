import fs from "node:fs";
import path from "node:path";
import { expect, test } from "./fixtures";

test("Karta kroku: výběr, konektor a klávesnice nabídky", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  const card = page.locator('[data-step-card="napis"]');
  await card.click();
  await expect(card).toHaveAttribute("aria-pressed", "true");
  await expect(card).toHaveClass(/bg-surface-active/);
  await expect(card).not.toHaveClass(/ring-1/); // .pen: vybraná karta jen plochou

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

test("Editor: celý prstenec HLAVIČKY, klidný posuvník a mazání jen v ⋯/panelu", async ({ page, project }) => {
  project.write("scenarios/tutorial-03-cviceni.yaml", fs.readFileSync(path.resolve(import.meta.dirname, "../../workflows/scenarios/tutorial-03-cviceni.yaml"), "utf8"));
  for (const agent of ["tutorial-pojmenovavac", "tutorial-sloganista"])
    project.write(`agents/${agent}.md`, fs.readFileSync(path.resolve(import.meta.dirname, `../../workflows/agents/${agent}.md`), "utf8"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/p/${project.name}/scenare/tutorial-03-cviceni?krok=_hlavicka`);
  const header = page.locator("main header").first();
  const card = page.locator('[data-step-card=""]');
  const panel = page.getByRole("complementary");
  await expect(panel).toBeVisible();
  await expect(header).toContainText("Vymyslí název");
  await page.evaluate(() => document.fonts.ready);
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--page-header-h") === `${document.querySelector<HTMLElement>("main header")?.offsetHeight}px`)).toBe(true);
  const headerBox = (await header.boundingBox())!;
  const cardBox = (await card.boundingBox())!;
  const panelBox = (await panel.boundingBox())!;
  expect(cardBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height);
  expect(panelBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height + 2);
  await expect(card).toHaveClass(/ring-inset ring-1/);

  const scroll = panel.locator("xpath=..");
  await page.mouse.move(20, 200);
  expect(await scroll.evaluate((el) => getComputedStyle(el).scrollbarWidth)).toBe("thin");
  expect(await scroll.evaluate((el) => getComputedStyle(el).scrollbarGutter)).toBe("stable");
  expect(await scroll.evaluate((el) => getComputedStyle(el).scrollbarColor)).toMatch(/^(?:transparent|rgba\(0, 0, 0, 0\))/);
  await scroll.hover();
  expect(await scroll.evaluate((el) => getComputedStyle(el).scrollbarColor)).toContain("49, 69, 95");

  await page.evaluate(() => window.scrollTo(0, 300));
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--page-header-h") === `${document.querySelector<HTMLElement>("main header")?.offsetHeight}px`)).toBe(true);
  const scrolledHeader = (await header.boundingBox())!;
  expect((await panel.boundingBox())!.y).toBeGreaterThanOrEqual(scrolledHeader.y + scrolledHeader.height + 2);
  const step = page.locator('[data-step-card="navrh"]');
  await step.click();
  await expect(step).toHaveClass(/bg-surface-active/);
  const stepBox = (await step.boundingBox())!;
  const stepHeader = (await header.boundingBox())!;
  expect(stepBox.y).toBeGreaterThanOrEqual(stepHeader.y + stepHeader.height);
  await expect(page.getByRole("region", { name: "Kroky scénáře" }).getByRole("button", { name: /^Smazat krok / })).toHaveCount(0);
  await page.getByRole("button", { name: "Akce pro navrh" }).click();
  await expect(page.getByRole("menuitem", { name: "Smazat (Delete)" })).toBeVisible();
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

test("KV6 věrnost (změřeno z .pen): pilulka 96 px, kolečko 40 px s ikonou typu, řádek typu mono 11 malými, ⋯ uvnitř", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  const card = page.locator('[data-step-card="napis"]');
  expect((await card.boundingBox())!.height).toBeCloseTo(96, 0);
  const badge = card.locator(".size-10.rounded-full");
  expect((await badge.boundingBox())!.width).toBeCloseTo(40, 0);
  const typeLine = card.getByText("ask · napis");
  await expect(typeLine).toHaveCSS("font-size", "11px");
  await expect(typeLine).not.toHaveCSS("text-transform", "uppercase");
  // ⋯ leží uvnitř pilulky vpravo
  const menu = (await page.getByRole("button", { name: "Akce pro napis" }).boundingBox())!;
  const box = (await card.boundingBox())!;
  expect(menu.x + menu.width).toBeLessThanOrEqual(box.x + box.width);
  // sloupec 676 a panel 440 s mezerou 28 (návrh 05 na 1440 px)
  await page.setViewportSize({ width: 1440, height: 900 });
  await card.click();
  const panel = (await page.getByRole("complementary").boundingBox())!;
  const col = (await card.boundingBox())!;
  expect(panel.width).toBeCloseTo(440, 0);
  expect(col.width).toBeCloseTo(676, 0);
  expect(Math.round(panel.x - (col.x + col.width))).toBe(28);
});

test("KV5 věrnost (změřeno z .pen): karta scénáře r14 p24 v. 292, prosté ikony typů bez šipek, meta mono, Otevřít ↗", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}`);
  const card = page.getByTestId("scenario-card-ukazka");
  await expect(card).toHaveCSS("border-radius", "14px");
  await expect(card).toHaveCSS("padding-top", "24px");
  expect((await card.boundingBox())!.height).toBeGreaterThanOrEqual(292);
  const chain = card.getByRole("list", { name: /Typy kroků/ });
  await expect(chain).not.toContainText("→");
  await expect(chain.locator(".rounded-full")).toHaveCount(0);
  await expect(card.getByRole("heading", { level: 2 })).toHaveCSS("font-size", "18px");
  await expect(card.getByText("2 kroky · 1 agent")).toHaveCSS("font-family", /JetBrains Mono/);
  await expect(card).toContainText("Otevřít");
});
