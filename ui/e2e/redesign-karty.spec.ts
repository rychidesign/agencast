import fs from "node:fs";
import path from "node:path";
import { expect, startRun, test, waitRun } from "./fixtures";

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

test("Editor: panel v toku stránky zarovnaný ke kartě", async ({ page, project }) => {
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
  const aligned = async (selected: string) => {
    const box = page.locator(`[data-step-card="${selected}"]`);
    await expect.poll(async () => Math.abs((await panel.boundingBox())!.y - (await box.boundingBox())!.y)).toBeLessThanOrEqual(1);
  };
  expect((await card.boundingBox())!.y).toBeGreaterThanOrEqual((await header.boundingBox())!.y + (await header.boundingBox())!.height);
  await expect(card).toHaveClass(/ring-inset ring-1/);
  const slot = panel.locator("xpath=..");
  fs.mkdirSync("/tmp/agencast-l", { recursive: true });
  await aligned("");
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  await page.screenshot({ path: "/tmp/agencast-l/1440-header.png" });
  await page.locator('[data-step-card="stop"]').click();
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  for (const width of [1440, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await aligned("stop");
    expect((await slot.boundingBox())!.width).toBe(440);
    expect(await slot.evaluate((el) => ({ height: el.scrollHeight - el.clientHeight, overflow: getComputedStyle(el).overflowY, position: getComputedStyle(el).position })))
      .toEqual({ height: 0, overflow: "visible", position: "static" });
    await page.screenshot({ path: `/tmp/agencast-l/${width}-step-3.png` });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('[data-step-card="navrh"]').click();
  for (const name of ["Podmínka", "Spolehlivost", "Podrobnosti kroku"])
    await panel.getByRole("button", { name: new RegExp(name) }).click();
  await expect.poll(() => page.evaluate(() => document.scrollingElement!.scrollHeight)).toBeGreaterThan(900);
  await page.evaluate(() => window.scrollTo(0, document.scrollingElement!.scrollHeight));
  await expect.poll(async () => (await panel.boundingBox())!.y + (await panel.boundingBox())!.height).toBeLessThanOrEqual(900);
  await page.screenshot({ path: "/tmp/agencast-l/1440-long-panel-bottom.png" });
  await expect(page.getByRole("region", { name: "Kroky scénáře" }).getByRole("button", { name: /^Smazat krok / })).toHaveCount(0);
});

test("Detail běhu: panel zarovnaný ke kartě", async ({ page, project, server }) => {
  const id = await startRun(server, project.name, "ukazka", { inputs: { tema: "káva" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/p/${project.name}/behy/${id}?krok=napis`);
  const card = page.locator('[data-step-card="napis"]');
  const panel = page.getByRole("complementary");
  await expect(panel).toBeVisible();
  await expect.poll(async () => Math.abs((await panel.boundingBox())!.y - (await card.boundingBox())!.y)).toBeLessThanOrEqual(1);
  expect((await panel.boundingBox())!.width).toBe(520);
  await page.screenshot({ path: "/tmp/agencast-l/1440-run-step.png" });
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
