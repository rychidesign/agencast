import { expect, test } from "./fixtures";

test("P1 ⋯ menu closes on Escape and returns focus", async ({ page, project }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: `Actions for ${project.name}` });
  await trigger.click();
  await expect(page.getByRole("menu")).toBeVisible();
  await expect(page.getByRole("menuitem").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("P2 Form/YAML keeps the disabled segment with a reason", async ({ page, project }) => {
  project.write("config.yaml", `${project.read("config.yaml")}\nruns_dir: ./elsewhere\n`);
  await page.goto(`/#/p/${project.name}/config`);
  const mode = page.getByRole("radiogroup", { name: "View" });
  const form = mode.getByRole("radio", { name: "Form" });
  const yaml = mode.getByRole("radio", { name: "YAML" });
  await expect(form).toHaveAttribute("aria-disabled", "true");
  await expect(form).toHaveAttribute("title", /Fix the YAML|failed validation/);
  await expect(yaml).toHaveAttribute("aria-checked", "true");
});

test("P3 modal keeps Tab inside", async ({ page, project }) => {
  await page.goto("/");
  await page.getByRole("button", { name: `Actions for ${project.name}` }).click();
  await page.getByRole("menuitem", { name: "Remove from registry" }).click();
  const dialog = page.getByRole("dialog", { name: `Remove “${project.name}” from the registry?` });
  // focus on the action (last in the footer: Cancel, action — ModalShell design); Tab from the last jumps to the first (×) and back
  const first = dialog.getByRole("button").first();
  const last = dialog.getByRole("button").last();
  await expect(last).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(first).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(last).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("P4 a variable is inserted with mouse and keyboard", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await page.getByRole("button", { name: /Step 1: ask write/ }).click();
  const prompt = page.getByRole("combobox", { name: /Prompt/ });
  const insert = page.getByRole("button", { name: "Insert variable" });
  await prompt.fill("Text ");
  await prompt.press("End");
  await insert.click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.getByRole("menuitem", { name: "inputs.topic" }).click();
  await expect(prompt).toHaveValue("Text {{ inputs.topic }}");

  await prompt.fill("More ");
  await prompt.press("Tab");
  await expect(insert).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(prompt).toHaveValue("More {{ inputs.topic }}");
});

test("P5 basic controls keep the design sizes", async ({ page, project }) => {
  await page.goto("/");
  const add = page.getByRole("button", { name: "Add project" }).first();
  await expect(add).toBeVisible();
  // .pen: screen buttons 44 px, radius 10; card ⋯ ghost with a 44 px click area
  expect(await add.evaluate((el) => ({ height: el.getBoundingClientRect().height, radius: getComputedStyle(el).borderRadius }))).toEqual({ height: 44, radius: "10px" });
  const menu = page.getByRole("button", { name: `Actions for ${project.name}` });
  expect(await menu.evaluate((el) => el.getBoundingClientRect().width)).toBe(44);
  await expect(menu).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");

  await page.goto(`/#/p/${project.name}/config`);
  const field = page.locator("input:not([type=checkbox])").first();
  await expect(field).toBeVisible();
  expect(await field.evaluate((el) => el.getBoundingClientRect().height)).toBe(44);
});
