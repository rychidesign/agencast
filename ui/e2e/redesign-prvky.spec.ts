import { expect, test } from "./fixtures";

test("P1 menu ⋯ zavře Escape a vrátí fokus", async ({ page, project }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: `Akce pro ${project.name}` });
  await trigger.click();
  await expect(page.getByRole("menu")).toBeVisible();
  await expect(page.getByRole("menuitem").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("P2 Form/YAML drží zakázaný segment s důvodem", async ({ page, project }) => {
  project.write("config.yaml", `${project.read("config.yaml")}\nruns_dir: ./jinde\n`);
  await page.goto(`/#/p/${project.name}/config`);
  const mode = page.getByRole("radiogroup", { name: "Zobrazení" });
  const form = mode.getByRole("radio", { name: "Form" });
  const yaml = mode.getByRole("radio", { name: "YAML" });
  await expect(form).toHaveAttribute("aria-disabled", "true");
  await expect(form).toHaveAttribute("title", /Oprav YAML|neprošel kontrolou/);
  await expect(yaml).toHaveAttribute("aria-checked", "true");
});

test("P3 modál drží Tab uvnitř", async ({ page, project }) => {
  await page.goto("/");
  await page.getByRole("button", { name: `Akce pro ${project.name}` }).click();
  await page.getByRole("menuitem", { name: "Odebrat z registru" }).click();
  const dialog = page.getByRole("dialog", { name: `Odebrat „${project.name}“ z registru?` });
  const first = dialog.getByRole("button").first();
  const last = dialog.getByRole("button").last();
  await expect(first).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(last).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(first).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("P4 proměnná se vloží myší i klávesnicí", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: /Krok 1: ask napis/ }).click();
  const prompt = page.getByRole("combobox", { name: /Prompt/ });
  const insert = page.getByRole("button", { name: "Vložit proměnnou" });
  await prompt.fill("Text ");
  await prompt.press("End");
  await insert.click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.getByRole("menuitem", { name: "inputs.tema" }).click();
  await expect(prompt).toHaveValue("Text {{ inputs.tema }}");

  await prompt.fill("Další ");
  await prompt.press("Tab");
  await expect(insert).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(prompt).toHaveValue("Další {{ inputs.tema }}");
});

test("P5 základní ovládání drží rozměry návrhu", async ({ page, project }) => {
  await page.goto("/");
  const add = page.getByRole("button", { name: "Přidat projekt" }).first();
  await expect(add).toBeVisible();
  // .pen: tlačítka na obrazovkách 44 px, radius 10; ⋯ karty ghost s klikací plochou 44
  expect(await add.evaluate((el) => ({ height: el.getBoundingClientRect().height, radius: getComputedStyle(el).borderRadius }))).toEqual({ height: 44, radius: "10px" });
  const menu = page.getByRole("button", { name: `Akce pro ${project.name}` });
  expect(await menu.evaluate((el) => el.getBoundingClientRect().width)).toBe(44);
  await expect(menu).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");

  await page.goto(`/#/p/${project.name}/config`);
  const field = page.locator("input:not([type=checkbox])").first();
  await expect(field).toBeVisible();
  expect(await field.evaluate((el) => el.getBoundingClientRect().height)).toBe(44);
});
