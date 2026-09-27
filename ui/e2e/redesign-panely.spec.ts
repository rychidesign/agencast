// Redesign V3, vlna B4 (docs/ui/redesign-plan.md §2 G1–G4, G11, G12): panely, editor agenta, Config.
import { expect, test } from "./fixtures";

test("PN1 panel kroku: eyebrow, titul = id, typ jako pole, Esc zavře", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: /Krok 1: ask napis/ }).click();
  const panel = page.getByRole("complementary", { name: "KROK 1 · ask" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("combobox", { name: "Typ kroku" })).toHaveValue("ask");
  await expect(page).toHaveURL(/krok=napis/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("complementary")).toHaveCount(0);
  await expect(page).not.toHaveURL(/krok=/);
});

test("PN2 panel spuštění: režim se volí kartou, limity jen u ostrého běhu", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("SPUSTIT BĚH");
  const mode = panel.getByRole("group", { name: "Režim běhu" });
  await expect(panel.getByRole("radio", { name: /Dry-run/ })).toBeChecked();
  await expect(panel.getByLabel("Limity běhu")).toHaveCount(0);
  // klik kamkoli na kartu (popis pod názvem) přepne režim
  await mode.getByText("Volá modely a stojí peníze; bez callbacku.").click();
  await expect(panel.getByRole("radio", { name: /Ostrý běh/ })).toBeChecked();
  await expect(panel.getByLabel("Limity běhu")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Spustit ostrý běh" })).toBeVisible();
  // fidelity §7: Zrušit + Spustit vpravo, limity jako řádky s oddělovači, padding panelu 24
  await expect(panel).toHaveCSS("padding-top", "24px");
  await expect(panel.getByLabel("Limity běhu").locator("div").first()).toHaveCSS("border-bottom-width", "1px");
  await panel.getByRole("button", { name: "Zrušit" }).click();
  await expect(page.getByRole("complementary")).toHaveCount(0);
});

test("PN5 věrnost §7: eyebrow mono 11 a select typu s popisem", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: /Krok 1: ask napis/ }).click();
  const panel = page.getByRole("complementary", { name: "KROK 1 · ask" });
  await expect(panel.getByRole("combobox", { name: "Typ kroku" }).locator("option:checked")).toHaveText("ask · jedno volání agenta");
  await expect(panel.getByText("KROK 1 · ask")).toHaveCSS("font-size", "11px");
});

test("PN3 editor agenta: Uložit jen nahoře, Přejmenovat a Smazat v ⋯, bez nadpisu a cesty ve formuláři", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/agenti/pisatel`);
  await expect(page.getByRole("heading", { name: "pisatel", level: 2 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Uložit" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: /Zrušit|Uložit změny/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Smazat", exact: true })).toHaveCount(0);
  await expect(page.getByText("agents/pisatel.md")).toHaveCount(0);
  await expect(page.getByRole("radiogroup", { name: "Zobrazení" })).toHaveCount(1);
  await page.getByRole("button", { name: "Akce pro pisatel" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["Načíst znovu", "Přejmenovat", "Smazat"]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
});

test("PN4 Config: jeden přepínač režimu, jedno Uložit, cesta projektu", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/config`);
  await expect(page.getByRole("heading", { name: "Připojení" })).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "Zobrazení" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Uložit" })).toHaveCount(1);
  await expect(page.getByText("config.yaml · mcp.yaml")).toHaveCount(0);
  await expect(page.getByText(project.root, { exact: true }).first()).toBeVisible();
  await page.getByRole("radiogroup", { name: "Zobrazení" }).getByRole("radio", { name: "YAML" }).click();
  await expect(page.getByRole("textbox", { name: "config.yaml" })).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "Zobrazení" })).toHaveCount(1);
});
