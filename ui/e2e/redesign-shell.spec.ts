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
  await expect(page.getByRole("combobox", { name: "Filtr scénáře" })).toHaveValue("ukazka");
});

test.describe("pod 1024 px", () => {
  test.use({ viewport: { width: 900, height: 800 } });

  test("R3 sidebar jako horní lišta 56 px s FAB nabídkou", async ({ page, project }) => {
    await page.goto(`/#/p/${project.name}`);
    await expect(page.getByTestId("scenario-card-ukazka")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Části projektu" })).toHaveCount(0);
    await expect(page.getByText("Dnes utraceno")).toBeHidden();
    const bar = (await page.locator("header").first().boundingBox())!;
    expect(bar.height).toBe(56);
    const h1 = (await page.getByRole("heading", { name: "Scénáře", level: 1 }).boundingBox())!;
    expect(bar.y + bar.height).toBeLessThanOrEqual(h1.y);
    const fab = page.getByRole("button", { name: "Navigace" });
    await expect(fab).toHaveCSS("width", "56px");
    await fab.click();
    const menu = page.getByRole("dialog", { name: "Navigace" });
    await expect.poll(async () => (await menu.boundingBox())!.y + (await menu.boundingBox())!.height).toBeLessThan((await fab.boundingBox())!.y);
    const nav = menu.getByRole("navigation", { name: "Části projektu" });
    for (const n of NAV) expect((await nav.getByRole("link", { name: n }).boundingBox())!.height).toBeCloseTo(48, 2);
    await expect(page.getByText("Dnes utraceno")).toBeVisible();
    await page.keyboard.press("Escape");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(900);
  });
});

// Hodnoty změřené z .pen (vlna F; fidelity §1, §3, §4, §8 opravené podle návrhu)
test("R4 věrnost návrhu: sidebar, hlavička, karta projektu, řádek běhu (změřeno z .pen)", async ({ page, project, server }) => {
  await page.goto("/");
  const h1 = page.getByRole("heading", { name: "Projekty", level: 1 });
  await expect(h1).toHaveCSS("font-size", "28px");
  await expect(h1).toHaveCSS("font-weight", "400");
  await expect(page.getByText("Spravuj projekty, scénáře a běhy agentů na jednom místě.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Načíst znovu" })).toHaveCSS("width", "44px");
  const card = page.getByTestId(`project-card-${project.name}`);
  await expect(card).toHaveCSS("border-top-left-radius", "14px");
  await expect(card).toHaveCSS("padding-left", "22px");
  await expect(card.getByRole("heading", { level: 2 })).toHaveCSS("font-size", "20px");

  const id = await startRun(server, project.name, "ukazka", { inputs: { tema: "káva" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/behy`);
  const nav = page.getByRole("navigation", { name: "Části projektu" });
  expect((await nav.locator("xpath=..").boundingBox())!.width).toBe(232);
  for (const link of await nav.getByRole("link").all()) expect((await link.boundingBox())!.height).toBe(44);
  await expect(nav.getByRole("link", { name: "Běhy" })).toHaveCSS("background-color", "rgb(37, 59, 80)"); // surface-active #253B50
  const row = page.getByTestId(`run-row-${id}`);
  expect((await row.boundingBox())!.height).toBe(72);
  await expect(row).toContainText(id);
  await expect(page.getByRole("columnheader", { name: "Scénář / run_id" })).toBeVisible();

  await page.goto(`/#/p/${project.name}/behy/${id}`);
  const title = page.getByRole("heading", { level: 1 }).getByRole("link", { name: "ukazka" });
  await expect(title).toHaveCSS("font-size", "26px");
  await expect(title).toHaveCSS("font-family", /JetBrains Mono/);
});
