// Vlna F: regrese věrnosti návrhu V3 proti .pen a nálezů z QA (rozměry v docs/ui/redesign-fidelity.md, „změřeno z .pen“).
import { expect, startRun, test, waitRun } from "./fixtures";

test.use({ viewport: { width: 1440, height: 900 } });

test("F1 gradient pozadí aplikace i pod přilepenou hlavičkou", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await expect(page.locator("body")).toHaveCSS("background-image", /linear-gradient/);
  await expect(page.locator("header").first()).toHaveCSS("background-image", /linear-gradient/);
  await expect(page.locator("header").first()).toHaveCSS("background-attachment", "fixed");
});

test("F2 YAML editor: čísla řádků sedí s řádky textu (27 px)", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka?rezim=yaml`);
  const numbers = page.locator('div[aria-hidden="true"].select-none').first();
  await expect(numbers).toBeVisible();
  const [num, line] = await Promise.all([
    numbers.locator("div").nth(4).boundingBox(),
    page.locator("pre[aria-hidden] > div").nth(4).boundingBox(),
  ]);
  expect(num!.height).toBe(27);
  expect(Math.abs(num!.y - line!.y)).toBeLessThan(1);
});

test("F3 modál: hlavička s křížkem, titul 22 px, patička Zrušit → akce, fokus na akci", async ({ page, project }) => {
  await page.goto("/");
  await page.getByRole("button", { name: `Akce pro ${project.name}` }).click();
  await page.getByRole("menuitem", { name: "Odebrat z registru" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { level: 2 })).toHaveCSS("font-size", "22px");
  await expect(dialog).toHaveCSS("border-top-left-radius", "14px");
  const buttons = await dialog.getByRole("button").allTextContents();
  expect(buttons.at(-2)).toBe("Zrušit");
  await expect(dialog.getByRole("button").last()).toBeFocused();
  await dialog.getByRole("button", { name: "Zavřít" }).click();
  await expect(dialog).toBeHidden();
});

test("F4 Běhy: filtry 210 px, řádek 72 px r8, záhlaví mono 10; ⋯ na kartách bez výplně", async ({ page, project, server }) => {
  const id = await startRun(server, project.name, "ukazka", { inputs: { tema: "káva" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/behy`);
  for (const name of ["Filtr stavu", "Filtr scénáře"]) expect((await page.getByRole("combobox", { name }).boundingBox())!.width).toBe(210);
  await expect(page.getByTestId(`run-row-${id}`).locator("td").first()).toHaveCSS("border-top-left-radius", "8px");
  await expect(page.getByRole("columnheader", { name: "Stav" })).toHaveCSS("font-size", "10px");
  await page.goto(`/#/p/${project.name}`);
  await expect(page.getByRole("button", { name: "Akce pro ukazka" })).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
});

test("F5 detail běhu: karta kroku bez pořadí, trvání · cena ve třetím řádku; Soubory s náhledem Markdownu", async ({ page, project, server }) => {
  const id = await startRun(server, project.name, "ukazka", { inputs: { tema: "káva" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/behy/${id}`);
  const step = page.locator('[data-step-card="napis"]');
  await expect(step.getByTestId("step-cost-napis")).toHaveText(/^\d+,\d{4} USD$/);
  await expect(step.locator(".w-4")).toHaveCount(0);
  await step.click();
  expect((await page.getByRole("complementary").boundingBox())!.width).toBe(520);

  await page.goto(`/#/p/${project.name}/behy/${id}?zalozka=soubory&soubor=summary.md`);
  const mode = page.getByRole("radiogroup", { name: "Zobrazení" });
  await expect(mode.getByRole("radio", { name: "Náhled" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("region", { name: "summary.md" })).toHaveCount(0);
  await mode.getByRole("radio", { name: "Kód" }).click();
  await expect(page.getByRole("region", { name: "summary.md" })).toBeVisible();
});

test("F6 editor: karta hlavičky r14, konektor 48, sloupec 676 + panel 440, přepínač 44 px", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
  const header = page.locator('[data-step-card=""]');
  await expect(header).toHaveCSS("border-top-left-radius", "14px");
  expect((await page.getByTestId("add-after-napis").locator("xpath=../..").boundingBox())!.height).toBe(48);
  expect((await page.getByRole("radio", { name: "Form" }).boundingBox())!.height).toBe(44);
  expect((await page.getByRole("complementary").boundingBox())!.width).toBe(440);
  await expect(page.getByTestId("save-status").locator("xpath=..")).toHaveClass(/rounded-full/);
});
