import { expect, test } from "./fixtures";

test("F4A fidelity: agent and skill have cards, the skill selection is saved", async ({ page, project }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/p/${project.name}/skills`);
  await page.getByRole("button", { name: "New skill" }).click();
  const dialog = page.getByRole("dialog", { name: "New skill" });
  await dialog.getByRole("textbox", { name: "Name" }).fill("research");
  await dialog.getByRole("button", { name: "Create" }).click();
  const skillCard = page.getByTestId("skill-editor-card");
  await expect(skillCard).toHaveCSS("border-radius", "16px");
  await expect(skillCard.getByText("Markdown · SKILL.md")).toBeVisible();

  await page.goto(`/#/p/${project.name}/agents/writer`);
  const nav = page.getByRole("navigation", { name: "Agents" });
  // design 06 (measured from .pen): 240 px list, item p 16 r 14
  await expect(nav).toHaveCSS("width", "240px");
  await expect(nav.getByRole("link", { name: "writer" })).toHaveCSS("padding-top", "16px");
  await expect(nav.getByRole("link", { name: "writer" })).toHaveCSS("border-radius", "14px");
  const card = page.getByTestId("agent-editor-card");
  await expect(card).toHaveCSS("border-radius", "16px");
  await expect(card.getByRole("radiogroup", { name: "View" })).toBeVisible();
  const skill = card.getByRole("checkbox", { name: /research/ });
  await expect(skill).not.toBeChecked();
  await skill.check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("save-status")).toContainText("Saved");
  expect(project.read("agents/writer.md")).toMatch(/skills:\s*(?:\[research\]|\n\s*- research)/);

  await page.goto(`/#/p/${project.name}/skills/research`);
  await expect(page.getByTestId("skill-editor-card").getByRole("link", { name: /writer/ })).toBeVisible();
});

test("F4C fidelity: Config has a card, two columns and nested aliases", async ({ page, project }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/p/${project.name}/config`);
  const card = page.getByTestId("config-editor-card");
  await expect(card).toHaveCSS("border-radius", "16px");
  await expect(card.locator(":scope > p")).toHaveText(project.root);
  await expect(card.getByRole("radiogroup", { name: "View" })).toBeVisible();
  const connection = card.getByRole("heading", { name: "Connection" });
  const jev = card.getByRole("heading", { name: "Jev model" });
  const positions = await Promise.all([connection.boundingBox(), jev.boundingBox()]);
  expect(positions[0]!.y).toBe(positions[1]!.y);
  expect(positions[0]!.x).toBeLessThan(positions[1]!.x);
  const alias = card.getByRole("button", { name: "Delete alias smart" }).locator("xpath=../..");
  await expect(alias).toHaveCSS("border-radius", "10px");
  await expect(alias.getByRole("button", { name: /Delete alias/ })).toBeDisabled();
  await expect(card.getByRole("button", { name: "+ alias" })).toContainText("Add alias");
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(1);
});
