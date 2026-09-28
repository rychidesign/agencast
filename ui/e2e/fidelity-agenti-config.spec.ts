import { expect, test } from "./fixtures";

test("F4A věrnost: agent a skill mají karty, výběr skillu se uloží", async ({ page, project }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/p/${project.name}/skilly`);
  await page.getByRole("button", { name: "Nový skill" }).click();
  const dialog = page.getByRole("dialog", { name: "Nový skill" });
  await dialog.getByRole("textbox", { name: "Jméno" }).fill("pruzkum");
  await dialog.getByRole("button", { name: "Vytvořit" }).click();
  const skillCard = page.getByTestId("skill-editor-card");
  await expect(skillCard).toHaveCSS("border-radius", "16px");
  await expect(skillCard.getByText("Markdown · SKILL.md")).toBeVisible();

  await page.goto(`/#/p/${project.name}/agenti/pisatel`);
  const nav = page.getByRole("navigation", { name: "Agenti" });
  // návrh 06 (změřeno z .pen): seznam 240 px, položka p 16 r 14
  await expect(nav).toHaveCSS("width", "240px");
  await expect(nav.getByRole("link", { name: "pisatel" })).toHaveCSS("padding-top", "16px");
  await expect(nav.getByRole("link", { name: "pisatel" })).toHaveCSS("border-radius", "14px");
  const card = page.getByTestId("agent-editor-card");
  await expect(card).toHaveCSS("border-radius", "16px");
  await expect(card.getByRole("radiogroup", { name: "Zobrazení" })).toBeVisible();
  const skill = card.getByRole("checkbox", { name: /pruzkum/ });
  await expect(skill).not.toBeChecked();
  await skill.check();
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(page.getByTestId("save-status")).toContainText("Uloženo");
  expect(project.read("agents/pisatel.md")).toMatch(/skills:\s*(?:\[pruzkum\]|\n\s*- pruzkum)/);

  await page.goto(`/#/p/${project.name}/skilly/pruzkum`);
  await expect(page.getByTestId("skill-editor-card").getByRole("link", { name: /pisatel/ })).toBeVisible();
});

test("F4C věrnost: Config má kartu, dvě kolony a aliasy vnořené", async ({ page, project }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/p/${project.name}/config`);
  const card = page.getByTestId("config-editor-card");
  await expect(card).toHaveCSS("border-radius", "16px");
  await expect(card.locator(":scope > p")).toHaveText(project.root);
  await expect(card.getByRole("radiogroup", { name: "Zobrazení" })).toBeVisible();
  const connection = card.getByRole("heading", { name: "Připojení" });
  const jev = card.getByRole("heading", { name: "Jev model" });
  const positions = await Promise.all([connection.boundingBox(), jev.boundingBox()]);
  expect(positions[0]!.y).toBe(positions[1]!.y);
  expect(positions[0]!.x).toBeLessThan(positions[1]!.x);
  const alias = card.getByRole("button", { name: "Smazat alias chytry" }).locator("xpath=../..");
  await expect(alias).toHaveCSS("border-radius", "10px");
  await expect(alias.getByRole("button", { name: /Smazat alias/ })).toBeDisabled();
  await expect(card.getByRole("button", { name: "+ alias" })).toContainText("Přidat alias");
  await expect(page.getByRole("button", { name: "Uložit" })).toHaveCount(1);
});
