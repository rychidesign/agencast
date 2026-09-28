// Vlna D redesignu V3: regrese nálezů z QA (překryvy, dialogy, 404, výpadek, přístupnost).
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { CHYBA, expect, startRun, test, waitRun } from "./fixtures";

const card = (page: Page, id: string) => page.locator(`[data-step-card="${id}"]`);

/** Axe (WCAG 2.1 A/AA): žádné kritické ani vážné porušení. */
async function axe(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
  expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

test("QA1 axe na hlavních obrazovkách", async ({ page, project, server }) => {
  project.write("scenarios/chyba.yaml", CHYBA);
  const id = await startRun(server, project.name, "chyba");
  await waitRun(server, project.name, id, ["failed"]);
  for (const hash of ["#/", `#/p/${project.name}`, `#/p/${project.name}/scenare/ukazka?krok=napis`, `#/p/${project.name}/agenti/pisatel`,
    `#/p/${project.name}/config`, `#/p/${project.name}/behy`, `#/p/${project.name}/behy/${id}`]) {
    await page.goto(`/${hash}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await axe(page);
  }
  // nedošlý krok je ztlumený čárkovaným obrysem, ne průhledností (kontrast textu ≥ 4,5:1)
  await expect(card(page, "vystup")).toHaveCSS("border-top-style", "dashed");
});

test("QA2 menu ⋯ karty leží nad dalšími kartami a menu hlavičky nad panelem", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
  await card(page, "napis").hover();
  await page.getByRole("button", { name: "Akce pro napis" }).click();
  // poslední položka zasahuje nad kartu `vystup`; klik myší ji musí trefit
  await page.getByRole("menuitem", { name: "Smazat" }).click();
  await expect(page.getByRole("dialog")).toContainText("Smazat krok „napis“?");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Další akce" }).click();
  await page.getByRole("menuitem", { name: "Přejmenovat" }).click();
  await expect(page.getByRole("dialog")).toContainText("Přejmenovat");
});

test("QA3 menu ⋯ zavře Tab; dialog po odmítnutém smazání zavře Esc", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/agenti/pisatel`);
  const trigger = page.getByRole("button", { name: "Akce pro pisatel" });
  await trigger.click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("menu")).toBeHidden();
  await trigger.click();
  await page.getByRole("menuitem", { name: "Smazat" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Smazat" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("nejde smazat");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("QA4 neexistující scénář, běh a projekt bez ovládání navíc", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/neni`);
  await expect(page.getByRole("alert")).toContainText("neexistuje");
  await expect(page.getByRole("button", { name: "Uložit" })).toHaveCount(0);
  await expect(page.getByTestId("save-status")).toHaveCount(0);
  await page.goto(`/#/p/${project.name}/behy/20990101-000000-nic-0000`);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Části běhu" })).toHaveCount(0);
  await page.goto("/#/p/neni-takovy");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("neni-takovy");
  await expect(page.getByRole("main").getByRole("link", { name: "Projekty" })).toBeVisible();
});

test("QA5 výpadek při ukládání: česká hláška, konflikt v hlavičce", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Jiný prompt");
  await page.route("**/projects/**", (r) => r.abort());
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(page.getByTestId("save-status")).toHaveText("Server neodpovídá, nic se nezapsalo.");
  await expect(page.getByTestId("server-bar")).toHaveCount(0);
  await page.unroute("**/projects/**");
  project.write("scenarios/ukazka.yaml", `${project.read("scenarios/ukazka.yaml")}# ručně\n`);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  // pruh je v přilepené hlavičce: panel vedle sloupce se řadí pod něj a nepřekryje ho
  await expect(page.locator("main header").getByTestId("conflict-bar")).toBeVisible({ timeout: 10_000 });
});

test("QA6 karta scénáře: stav dole, dlouhý popis zkrácený", async ({ page, project }) => {
  const long = "Dlouhý popis. ".repeat(40).trim();
  project.write("scenarios/ukazka.yaml", project.read("scenarios/ukazka.yaml").replace(/^description: .*$/m, `description: ${long}`));
  await page.goto(`/#/p/${project.name}`);
  const c = page.getByTestId("scenario-card-ukazka");
  await expect(c.getByText("bez běhů")).toBeVisible();
  const desc = c.locator("p", { hasText: "Dlouhý popis." });
  await expect(desc).toHaveAttribute("title", long);
  expect((await desc.boundingBox())!.height).toBeLessThanOrEqual(3 * 20 + 2);
  const [chain, chip] = await Promise.all([c.locator("ol").boundingBox(), c.getByText("bez běhů").boundingBox()]);
  expect(chip!.y).toBeGreaterThan(chain!.y + 40);
});
