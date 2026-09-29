// Wave F: regressions of design V3 fidelity against .pen and of QA findings (sizes in docs/ui/redesign-fidelity.md, “measured from .pen”).
import { expect, startRun, test, waitRun } from "./fixtures";

test.use({ viewport: { width: 1440, height: 900 } });

test("F1 app background gradient, also under the sticky header", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await expect(page.locator("body")).toHaveCSS("background-image", /linear-gradient/);
  await expect(page.locator("header").first()).toHaveCSS("background-image", /linear-gradient/);
  await expect(page.locator("header").first()).toHaveCSS("background-attachment", "fixed");
});

test("F2 YAML editor: line numbers line up with text lines (27 px)", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo?mode=yaml`);
  const numbers = page.locator('div[aria-hidden="true"].select-none').first();
  await expect(numbers).toBeVisible();
  const [num, line] = await Promise.all([
    numbers.locator("div").nth(4).boundingBox(),
    page.locator("pre[aria-hidden] > div").nth(4).boundingBox(),
  ]);
  expect(num!.height).toBe(27);
  expect(Math.abs(num!.y - line!.y)).toBeLessThan(1);
});

test("F3 modal: header with ×, 22 px title, footer Cancel → action, focus on the action", async ({ page, project }) => {
  await page.goto("/");
  await page.getByRole("button", { name: `Actions for ${project.name}` }).click();
  await page.getByRole("menuitem", { name: "Remove from registry" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { level: 2 })).toHaveCSS("font-size", "22px");
  await expect(dialog).toHaveCSS("border-top-left-radius", "14px");
  const buttons = await dialog.getByRole("button").allTextContents();
  expect(buttons.at(-2)).toBe("Cancel");
  await expect(dialog.getByRole("button").last()).toBeFocused();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
});

test("F4 Runs: 210 px filters, 72 px row r8, mono 10 header; ⋯ on cards without fill", async ({ page, project, server }) => {
  const id = await startRun(server, project.name, "demo", { inputs: { topic: "coffee" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/runs`);
  for (const name of ["Status filter", "Scenario filter"]) expect((await page.getByRole("combobox", { name }).boundingBox())!.width).toBe(210);
  await expect(page.getByTestId(`run-row-${id}`).locator("td").first()).toHaveCSS("border-top-left-radius", "8px");
  await expect(page.getByRole("columnheader", { name: "Status" })).toHaveCSS("font-size", "10px");
  await page.goto(`/#/p/${project.name}`);
  await expect(page.getByRole("button", { name: "Actions for demo" })).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
});

test("F5 run detail: step card without order number, duration · cost in the third line; Files with a Markdown preview", async ({ page, project, server }) => {
  const id = await startRun(server, project.name, "demo", { inputs: { topic: "coffee" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/runs/${id}`);
  const step = page.locator('[data-step-card="write"]');
  await expect(step.getByTestId("step-cost-write")).toHaveText(/^\d+\.\d{4} USD$/);
  await expect(step.locator(".w-4")).toHaveCount(0);
  await step.click();
  expect((await page.getByRole("complementary").boundingBox())!.width).toBe(520);

  await page.goto(`/#/p/${project.name}/runs/${id}?tab=files&file=summary.md`);
  const mode = page.getByRole("radiogroup", { name: "View" });
  await expect(mode.getByRole("radio", { name: "Preview" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("region", { name: "summary.md" })).toHaveCount(0);
  await mode.getByRole("radio", { name: "Code" }).click();
  await expect(page.getByRole("region", { name: "summary.md" })).toBeVisible();
});

test("F6 editor: header card r14, connector 48, column 676 + panel 440, 44 px switch", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
  const header = page.locator('[data-step-card=""]');
  await expect(header).toHaveCSS("border-top-left-radius", "14px");
  expect((await page.getByTestId("add-after-write").locator("xpath=../..").boundingBox())!.height).toBe(48);
  expect((await page.getByRole("radio", { name: "Form" }).boundingBox())!.height).toBe(44);
  expect((await page.getByRole("complementary").boundingBox())!.width).toBe(440);
  await expect(page.getByTestId("save-status").locator("xpath=..")).toHaveClass(/rounded-full/);
});
