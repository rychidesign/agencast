// Redesign V3, shell (docs/ui/redesign-plan.md G1, G4, G5, G6, G8, G14): sidebar, headers, ⋯ menu, bar below 1024 px.
import { expect, startRun, test, waitRun } from "./fixtures";

const NAV = ["Scenarios", "Agents", "Runs", "Skills", "Config"];

test("R1 sidebar: project navigation, active item, spend", async ({ page, project, server }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "agencast" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Project sections" })).toHaveCount(0);
  await expect(page.getByText("Spent today")).toHaveCount(0);
  await expect(page.getByText("server available")).toHaveCount(0);
  // G8: a non-empty list → adding only via the header button
  await expect(page.getByRole("button", { name: "Add project" })).toHaveCount(1);

  await page.getByRole("link", { name: project.name, exact: true }).click();
  const nav = page.getByRole("navigation", { name: "Project sections" });
  await expect(nav.getByRole("link")).toHaveText(NAV);
  await expect(nav.getByRole("link", { name: "Scenarios" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Spent today")).toBeVisible();
  await expect(page.getByTestId("spend-today")).toHaveText(/^\d+\.\d{2,4}( \/ \d+\.\d{2,4})? USD$/);

  await nav.getByRole("link", { name: "Runs" }).click();
  await expect(page).toHaveURL(new RegExp(`#/p/${project.name}/runs$`));
  await expect(page.getByRole("heading", { name: "Runs", level: 1 })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
  await expect(nav.locator("[aria-current]")).toHaveCount(1);

  // the scenario editor belongs under Scenarios, the run detail under Runs
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await expect(nav.getByRole("link", { name: "Scenarios" })).toHaveAttribute("aria-current", "page");
  const id = await startRun(server, project.name, "demo", { inputs: { topic: "coffee" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/runs/${id}`);
  await expect(page.getByTestId("run-state")).toHaveText("succeeded");
  await expect(nav.getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");

  await page.getByRole("link", { name: "Projects" }).click();
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
});

test("R2 editor: header with Save, Run and the ⋯ menu", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await expect(page.getByRole("heading", { name: "demo", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Scenarios", exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Rename" })).toHaveCount(0);

  await page.getByRole("button", { name: "More actions" }).click();
  for (const name of ["Undo", "Copy run command", "Runs of this scenario", "Rename", "Delete"])
    await expect(page.getByRole("menuitem", { name, exact: true })).toBeVisible();
  await page.getByRole("menuitem", { name: "Runs of this scenario" }).click();
  await expect(page).toHaveURL(new RegExp(`#/p/${project.name}/runs\\?scenario=demo$`));
  await expect(page.getByRole("combobox", { name: "Scenario filter" })).toHaveValue("demo");
});

test.describe("below 1024 px", () => {
  test.use({ viewport: { width: 900, height: 800 } });

  test("R3 sidebar as a 56 px top bar with a FAB menu", async ({ page, project }) => {
    await page.goto(`/#/p/${project.name}`);
    await expect(page.getByTestId("scenario-card-demo")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Project sections" })).toHaveCount(0);
    await expect(page.getByText("Spent today")).toBeHidden();
    const bar = (await page.locator("header").first().boundingBox())!;
    expect(bar.height).toBe(56);
    const h1 = (await page.getByRole("heading", { name: "Scenarios", level: 1 }).boundingBox())!;
    expect(bar.y + bar.height).toBeLessThanOrEqual(h1.y);
    const fab = page.getByRole("button", { name: "Navigation" });
    await expect(fab).toHaveCSS("width", "56px");
    await fab.click();
    const menu = page.getByRole("dialog", { name: "Navigation" });
    await expect.poll(async () => (await menu.boundingBox())!.y + (await menu.boundingBox())!.height).toBeLessThan((await fab.boundingBox())!.y);
    const nav = menu.getByRole("navigation", { name: "Project sections" });
    for (const n of NAV) expect((await nav.getByRole("link", { name: n }).boundingBox())!.height).toBeCloseTo(48, 2);
    await expect(page.getByText("Spent today")).toBeVisible();
    await page.keyboard.press("Escape");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(900);
  });
});

// Values measured from .pen (wave F; fidelity §1, §3, §4, §8 corrected per the design)
test("R4 design fidelity: sidebar, header, project card, run row (measured from .pen)", async ({ page, project, server }) => {
  await page.goto("/");
  const h1 = page.getByRole("heading", { name: "Projects", level: 1 });
  await expect(h1).toHaveCSS("font-size", "28px");
  await expect(h1).toHaveCSS("font-weight", "400");
  await expect(page.getByText("Manage projects, scenarios and agent runs in one place.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Reload" })).toHaveCSS("width", "44px");
  const card = page.getByTestId(`project-card-${project.name}`);
  await expect(card).toHaveCSS("border-top-left-radius", "14px");
  await expect(card).toHaveCSS("padding-left", "22px");
  await expect(card.getByRole("heading", { level: 2 })).toHaveCSS("font-size", "20px");

  const id = await startRun(server, project.name, "demo", { inputs: { topic: "coffee" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/runs`);
  const nav = page.getByRole("navigation", { name: "Project sections" });
  expect((await nav.locator("xpath=..").boundingBox())!.width).toBe(232);
  for (const link of await nav.getByRole("link").all()) expect((await link.boundingBox())!.height).toBe(44);
  await expect(nav.getByRole("link", { name: "Runs" })).toHaveCSS("background-color", "rgb(37, 59, 80)"); // surface-active #253B50
  const row = page.getByTestId(`run-row-${id}`);
  expect((await row.boundingBox())!.height).toBe(72);
  await expect(row).toContainText(id);
  await expect(page.getByRole("columnheader", { name: "Scenario / run_id" })).toBeVisible();

  await page.goto(`/#/p/${project.name}/runs/${id}`);
  const title = page.getByRole("heading", { level: 1 }).getByRole("link", { name: "demo" });
  await expect(title).toHaveCSS("font-size", "26px");
  await expect(title).toHaveCSS("font-family", /JetBrains Mono/);
});
