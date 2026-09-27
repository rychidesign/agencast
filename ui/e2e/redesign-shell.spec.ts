// Redesign V3, shell (docs/ui/redesign-plan.md G1, G4, G5, G6, G8, G14): sidebar, hlavičky, menu ⋯, lišta pod 1024 px.
import { expect, startRun, test, waitRun } from "./fixtures";

const NAV = ["Scénáře", "Agenti", "Běhy", "Skilly", "Config"];

test("R1 sidebar: navigace projektu, aktivní položka, útrata", async ({ page, project, server }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projekty", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "agencast" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Části projektu" })).toHaveCount(0);
  await expect(page.getByText("Dnes utraceno")).toHaveCount(0);
  await expect(page.getByText("server dostupný")).toHaveCount(0);
  // G8: neprázdný seznam → přidání jen tlačítkem v hlavičce
  await expect(page.getByRole("button", { name: "Přidat projekt" })).toHaveCount(1);

  await page.getByRole("link", { name: project.name, exact: true }).click();
  const nav = page.getByRole("navigation", { name: "Části projektu" });
  await expect(nav.getByRole("link")).toHaveText(NAV);
  await expect(nav.getByRole("link", { name: "Scénáře" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Dnes utraceno")).toBeVisible();
  await expect(page.getByTestId("spend-today")).toHaveText(/^\d+,\d{2,4}( \/ \d+,\d{2,4})? USD$/);

  await nav.getByRole("link", { name: "Běhy" }).click();
  await expect(page).toHaveURL(new RegExp(`#/p/${project.name}/behy$`));
  await expect(page.getByRole("heading", { name: "Běhy", level: 1 })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Běhy" })).toHaveAttribute("aria-current", "page");
  await expect(nav.locator("[aria-current]")).toHaveCount(1);

  // editor scénáře patří pod Scénáře, detail běhu pod Běhy
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await expect(nav.getByRole("link", { name: "Scénáře" })).toHaveAttribute("aria-current", "page");
  const id = await startRun(server, project.name, "ukazka", { inputs: { tema: "káva" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/behy/${id}`);
  await expect(page.getByTestId("run-state")).toHaveText("úspěch");
  await expect(nav.getByRole("link", { name: "Běhy" })).toHaveAttribute("aria-current", "page");

  await page.getByRole("link", { name: "Projekty" }).click();
  await expect(page.getByRole("heading", { name: "Projekty", level: 1 })).toBeVisible();
});

test("R2 editor: hlavička s Uložit, Spustit a menu ⋯", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await expect(page.getByRole("heading", { name: "ukazka", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Scénáře", exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Spustit", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Uložit" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Přejmenovat" })).toHaveCount(0);

  await page.getByRole("button", { name: "Další akce" }).click();
  await expect(page.getByRole("menuitem")).toHaveText([
    "Vrátit zpět (Ctrl+Z)", "Kopírovat příkaz spuštění", "Běhy tohoto scénáře", "Přejmenovat", "Smazat"]);
  await page.getByRole("menuitem", { name: "Běhy tohoto scénáře" }).click();
  await expect(page).toHaveURL(new RegExp(`#/p/${project.name}/behy\\?scenar=ukazka$`));
  await expect(page.getByRole("combobox", { name: /scénář/ })).toHaveValue("ukazka");
});

test.describe("pod 1024 px", () => {
  test.use({ viewport: { width: 900, height: 800 } });

  test("R3 sidebar jako horní lišta", async ({ page, project }) => {
    await page.goto(`/#/p/${project.name}`);
    const nav = page.getByRole("navigation", { name: "Části projektu" });
    await expect(nav).toBeVisible();
    // hlavičku po načtení projektu přebírá záložka (nový uzel), měřit až po načtení karet
    await expect(page.getByTestId("scenario-card-ukazka")).toBeVisible();
    const h1 = (await page.getByRole("heading", { name: "Scénáře", level: 1 }).boundingBox())!;
    const boxes = await Promise.all(NAV.map(async (n) => (await nav.getByRole("link", { name: n }).boundingBox())!));
    for (const b of boxes) {
      expect(Math.abs(b.y - boxes[0].y)).toBeLessThanOrEqual(1); // vodorovně v jedné řadě
      expect(b.y + b.height).toBeLessThanOrEqual(h1.y); // nad obsahem
      expect(b.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.getByText("Dnes utraceno")).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(900);
  });
});
