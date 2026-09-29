// Redesign V3 wave D: regressions of QA findings (overlaps, dialogs, 404, outage, accessibility).
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { FAILING, expect, startRun, test, waitRun } from "./fixtures";

const card = (page: Page, id: string) => page.locator(`[data-step-card="${id}"]`);

/** Axe (WCAG 2.1 A/AA): no critical or serious violations. */
async function axe(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
  expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

test("QA1 axe on the main screens", async ({ page, project, server }) => {
  project.write("scenarios/failing.yaml", FAILING);
  const id = await startRun(server, project.name, "failing");
  await waitRun(server, project.name, id, ["failed"]);
  for (const hash of ["#/", `#/p/${project.name}`, `#/p/${project.name}/scenarios/demo?step=write`, `#/p/${project.name}/agents/writer`,
    `#/p/${project.name}/config`, `#/p/${project.name}/runs`, `#/p/${project.name}/runs/${id}`]) {
    await page.goto(`/${hash}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await axe(page);
  }
  // a step not reached is dimmed by a dashed outline, not transparency (text contrast ≥ 4.5:1)
  await expect(card(page, "result")).toHaveCSS("border-top-style", "dashed");
});

test("QA2 the card ⋯ menu lies above other cards and the header menu above the panel", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
  await card(page, "write").hover();
  await page.getByRole("button", { name: "Actions for write" }).click();
  // the last item overlaps the `result` card; a mouse click must hit it
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await expect(page.getByRole("dialog")).toContainText("Delete step “write”?");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Rename" }).click();
  await expect(page.getByRole("dialog")).toContainText("Rename");
});

test("QA3 Tab closes the ⋯ menu; Esc closes the dialog after a refused delete", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/agents/writer`);
  const trigger = page.getByRole("button", { name: "Actions for writer" });
  await trigger.click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("menu")).toBeHidden();
  await trigger.click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("cannot be deleted");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("QA4 missing scenario, run and project without extra controls", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/absent`);
  await expect(page.getByRole("alert")).toContainText("does not exist");
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
  await expect(page.getByTestId("save-status")).toHaveCount(0);
  await page.goto(`/#/p/${project.name}/runs/20990101-000000-missing-0000`);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Run sections" })).toHaveCount(0);
  await page.goto("/#/p/no-such-project");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("no-such-project");
  await expect(page.getByRole("main").getByRole("link", { name: "Projects" })).toBeVisible();
});

test("QA5 outage while saving: a clear message, conflict in the header", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Another prompt");
  await page.route("**/projects/**", (r) => r.abort());
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("save-status")).toHaveText("The server is not responding; nothing was written.");
  await expect(page.getByTestId("server-bar")).toHaveCount(0);
  await page.unroute("**/projects/**");
  project.write("scenarios/demo.yaml", `${project.read("scenarios/demo.yaml")}# by hand\n`);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  // the bar is in the sticky header: the panel next to the column sits below it and doesn't cover it
  await expect(page.locator("main header").getByTestId("conflict-bar")).toBeVisible({ timeout: 10_000 });
});

test("QA6 scenario card: status at the bottom, a long description truncated", async ({ page, project }) => {
  const long = "Long description. ".repeat(40).trim();
  project.write("scenarios/demo.yaml", project.read("scenarios/demo.yaml").replace(/^description: .*$/m, `description: ${long}`));
  await page.goto(`/#/p/${project.name}`);
  const c = page.getByTestId("scenario-card-demo");
  await expect(c.getByText("no runs")).toBeVisible();
  const desc = c.locator("p", { hasText: "Long description." });
  await expect(desc).toHaveAttribute("title", long);
  expect((await desc.boundingBox())!.height).toBeLessThanOrEqual(3 * 20 + 2);
  const [chain, chip] = await Promise.all([c.locator("ol").boundingBox(), c.getByText("no runs").boundingBox()]);
  expect(chip!.y).toBeGreaterThan(chain!.y + 40);
});
