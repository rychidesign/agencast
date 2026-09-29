// Redesign V3, wave B4 (docs/ui/redesign-plan.md §2 G1–G4, G11, G12): panels, agent editor, Config.
import { expect, test } from "./fixtures";

test("PN1 step panel: eyebrow, title = id, type as a field, Esc closes", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await page.getByRole("button", { name: /Step 1: ask write/ }).click();
  const panel = page.getByRole("complementary", { name: "STEP 1 · ask" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("combobox", { name: "Step type" })).toHaveValue("ask");
  await expect(page).toHaveURL(/step=write/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("complementary")).toHaveCount(0);
  await expect(page).not.toHaveURL(/step=/);
});

test("PN2 run panel: the mode is picked by card, limits only for a live run", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("START RUN");
  const mode = panel.getByRole("group", { name: "Run mode" });
  await expect(panel.getByRole("radio", { name: /Dry run/ })).toBeChecked();
  await expect(panel.getByLabel("Run limits")).toHaveCount(0);
  // a click anywhere on the card (the description under the name) switches the mode
  await mode.getByText("Calls models and costs money; no callback.").click();
  await expect(panel.getByRole("radio", { name: /Live run/ })).toBeChecked();
  await expect(panel.getByLabel("Run limits")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Start live run" })).toBeVisible();
  // .pen (design 10): Cancel + Run on the right, limits as rows with dividers, panel header with a rule, body p 20
  await expect(panel.locator(":scope > div").first()).toHaveCSS("border-bottom-width", "1px");
  await expect(panel.locator(":scope > div").nth(1)).toHaveCSS("padding-top", "20px");
  await expect(panel.getByLabel("Run limits").locator("div").first()).toHaveCSS("border-bottom-width", "1px");
  await panel.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("complementary")).toHaveCount(0);
});

test("PN5 fidelity (measured from .pen): eyebrow mono 10 and the type select with a description", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await page.getByRole("button", { name: /Step 1: ask write/ }).click();
  const panel = page.getByRole("complementary", { name: "STEP 1 · ask" });
  await expect(panel.getByRole("combobox", { name: "Step type" }).locator("option:checked")).toHaveText("ask · single agent call");
  await expect(panel.getByText("STEP 1 · ask")).toHaveCSS("font-size", "10px");
});

test("PN3 agent editor: Save only at the top, Rename and Delete in ⋯, no heading and path in the form", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/agents/writer`);
  await expect(page.getByRole("heading", { name: "writer", level: 2 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: /Cancel|Save changes/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Delete", exact: true })).toHaveCount(0);
  await expect(page.getByText("agents/writer.md")).toHaveCount(0);
  await expect(page.getByRole("radiogroup", { name: "View" })).toHaveCount(1);
  await page.getByRole("button", { name: "Actions for writer" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["Reload", "Rename", "Delete"]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
});

test("PN4 Config: one mode switch, one Save, the project path", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/config`);
  await expect(page.getByRole("heading", { name: "Connection" })).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "View" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(1);
  await expect(page.getByText("config.yaml · mcp.yaml")).toHaveCount(0);
  await expect(page.getByText(project.root, { exact: true }).first()).toBeVisible();
  await page.getByRole("radiogroup", { name: "View" }).getByRole("radio", { name: "YAML" }).click();
  await expect(page.getByRole("textbox", { name: "config.yaml" })).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "View" })).toHaveCount(1);
});
