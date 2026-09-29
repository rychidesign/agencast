// Journeys C3–C5, C9–C12, C15 and states N1, N6 (docs/ui/user-journeys.md): agent and scenario editor.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import { expect, startRun, tabTo, test, waitRun } from "./fixtures";

type Scn = { description?: string; steps: ({ id: string } & Record<string, unknown>)[] };

const card = (page: Page, id: string) => page.locator(`[data-step-card="${id}"]`);
/** Card wrapper (card + controls + errors below it). */
const cardBox = (page: Page, id: string) => card(page, id).locator("xpath=..");
const saveStatus = (page: Page) => page.getByTestId("save-status");
const live = (page: Page) => page.getByTestId("announce");
const sha = (text: string) => createHash("sha256").update(text).digest("hex");

const ARTICLE = `version: 1
name: article
description: Writes and rates an article
inputs:
  topic: { type: string, default: coffee }
outputs:
  text: { type: string }
steps:
  - id: write
    ask:
      agent: writer
      prompt: "Write an article: {{ inputs.topic }}"
  - id: jev_1
    jev:
      state: "{{ steps.write.text }}"
      questions:
        ok: { type: noul, instructions: "Is the text in English?" }
  - id: result
    output:
      text: "{{ steps.write.text }}"
`;

test("C3 new agent", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/agents`);
  const nav = page.getByRole("navigation", { name: "Agents" });
  // G8: “+ New agent” is in the section header, not in the list
  await expect(page.locator("main header").getByRole("button", { name: "New agent" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "writer" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "writer", level: 2 })).toBeVisible();

  await page.getByRole("button", { name: "New agent" }).click();
  const dialog = page.getByRole("dialog", { name: "New agent" });
  const nameInput = dialog.getByRole("textbox", { name: "Name" });
  await expect(nameInput).toBeFocused();
  await nameInput.fill("Wrîter");
  await expect(nameInput).toHaveValue("writer"); // the name is normalized while typing
  await expect(dialog.getByText("“writer” already exists.")).toBeVisible();
  await nameInput.fill("proofreader");
  await dialog.getByRole("textbox", { name: "description" }).fill("Checks spelling");
  await expect(dialog.getByRole("combobox", { name: "model" })).toHaveValue("smart");
  await dialog.getByRole("button", { name: "Create" }).click();

  await expect(page).toHaveURL(/\/agents\/proofreader$/);
  await expect(page.getByRole("heading", { name: "proofreader", level: 2 })).toBeVisible();
  const mode = page.getByRole("radiogroup", { name: "View" });
  await expect(mode.getByRole("radio")).toHaveText(["Form", "Markdown"]);
  await expect(saveStatus(page)).toHaveText("Saved ✓");
  await expect(page.getByRole("textbox", { name: "description" })).toHaveValue("Checks spelling");
  await expect(page.getByRole("combobox", { name: "model" })).toHaveValue("smart");
  await expect(page.getByText("Used by: –")).toBeVisible();
  const fm = () => project.read("agents/proofreader.md");
  expect(fm()).toMatch(/model: smart/);
  expect(fm()).toMatch(/budget_usd: 0\.02/);
  expect(fm()).toMatch(/description: .?Checks spelling/);

  const before = fm().split("\n");
  await page.getByRole("textbox", { name: "Instructions (system prompt)" }).fill("Fix only errors.");
  await expect(saveStatus(page)).toHaveText("Unsaved");
  await page.keyboard.press("Control+s");
  await expect(saveStatus(page)).toHaveText(/^Saved ✓ \d{1,2}:\d{2}\s[AP]M$/);
  const after = fm();
  expect(after).toContain("Fix only errors.");
  // frontmatter unchanged, body replaced
  expect(after.split("---")[1]).toBe(before.join("\n").split("---")[1]);

  await mode.getByRole("radio", { name: "Markdown" }).click();
  await expect(page.getByRole("textbox", { name: "agents/proofreader.md" })).toHaveValue(/^---\n/);
  await expect(page.getByText("You are editing workflows/agents/proofreader.md directly")).toBeVisible();

  await page.getByRole("button", { name: "Actions for proofreader" }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  const del = page.getByRole("dialog", { name: "Delete agent “proofreader”?" });
  await del.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL(/\/agents$/);
  await expect(nav.getByRole("link")).toHaveText(["writer"]);
  expect(fs.existsSync(path.join(project.wf, "agents/proofreader.md"))).toBe(false);

  // demo uses writer → the API refuses the delete and the dialog says why
  await page.getByRole("button", { name: "Actions for writer" }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("demo");
  expect(fs.existsSync(path.join(project.wf, "agents/writer.md"))).toBe(true);
});

test("C4 new scenario with two steps and output", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}`);
  await page.getByRole("button", { name: "New scenario" }).click();
  const dialog = page.getByRole("dialog", { name: "New scenario" });
  await expect(dialog.getByText("Also used as the file name.")).toBeVisible();
  await dialog.getByRole("textbox", { name: "Name" }).fill("article");
  await dialog.getByRole("textbox", { name: "description" }).fill("Writes and rates an article");
  await dialog.getByRole("button", { name: "Create" }).click();

  await expect(page).toHaveURL(/scenarios\/article\?step=_header$/);
  await expect(page.getByRole("heading", { name: "article", level: 1 })).toBeVisible();
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("HEADER");
  await expect(panel.getByRole("textbox", { name: /^description/ })).toHaveValue("Writes and rates an article");
  await expect(panel.getByRole("checkbox", { name: "required" })).not.toBeChecked();
  await expect(panel.getByRole("textbox", { name: "Default value of topic" })).toHaveValue("coffee");
  await expect(card(page, "").locator("span.bg-nested")).toHaveText(["topicstring"]);
  await expect(card(page, "")).toContainText("1 output: text");
  await expect(card(page, "write")).toHaveAttribute("aria-label", "Step 1: ask write");
  await expect(card(page, "result")).toHaveAttribute("aria-label", "Step 2: output result");
  expect(project.yaml<Scn>("scenarios/article.yaml").description).toBe("Writes and rates an article");
  const template = project.read("scenarios/article.yaml");

  await page.getByTestId("add-after-write").click();
  const picker = page.getByRole("listbox", { name: "New step type" });
  await picker.press("j");
  await expect(picker.getByRole("option")).toHaveText([/^jev\s*cheap Jev decision$/]);
  await picker.press("Enter");
  await expect(card(page, "jev_1")).toHaveAttribute("aria-label", "Step 2: jev jev_1");
  await expect(card(page, "jev_1")).toContainText("fill in the panel");
  await expect(panel).toContainText("STEP 2");
  await expect(panel.getByRole("combobox", { name: "Step type" })).toHaveValue("jev");
  await expect(live(page)).toHaveText("Added step jev_1.");
  await expect(page).toHaveURL(/step=jev_1/);
  await expect(saveStatus(page)).toHaveText("Unsaved");

  const state = panel.getByRole("combobox", { name: "State" });
  await state.pressSequentially("{{ steps.");
  await expect(page.locator("ul[role=listbox]").getByRole("option")).toHaveText(["steps.write.text"]);
  await state.press("Enter");
  await state.pressSequentially(" }}");
  await expect(state).toHaveValue("{{ steps.write.text }}");
  await panel.getByRole("button", { name: "Add question" }).click();
  await expect(panel.getByRole("combobox", { name: "Question type for q_1" })).toBeVisible();
  const key = panel.getByRole("textbox", { name: "Name" });
  await key.fill("ok");
  await key.press("Tab");
  await panel.getByRole("combobox", { name: "Question", exact: true }).fill("Is the text in English and error-free?");

  await card(page, "result").click();
  await expect(panel.getByRole("combobox", { name: "text" })).toHaveValue("{{ steps.write.text }}");
  await expect(panel.getByRole("button", { name: /^Condition/ })).toHaveCount(0); // output has no condition (scenario.md)
  await expect(panel.getByRole("button", { name: /^Step details result/ })).toHaveAttribute("aria-expanded", "false");

  const saved = page.waitForResponse((r) => r.url().endsWith("/scenarios/article/batch") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Save" }).click();
  expect((await saved).status()).toBe(200);
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  const doc = project.yaml<Scn>("scenarios/article.yaml");
  expect(doc.steps.map((s) => s.id)).toEqual(["write", "jev_1", "result"]);
  expect(doc.steps[1].jev).toEqual({ state: "{{ steps.write.text }}", questions: { ok: { type: "noul", instructions: "Is the text in English and error-free?" } } });
  // the template's comments are kept
  const comments = (t: string) => t.split("\n").filter((l) => l.trim().startsWith("#"));
  expect(comments(project.read("scenarios/article.yaml"))).toEqual(comments(template));

  await page.getByRole("main").getByRole("link", { name: "Scenarios", exact: true }).click();
  const sc = page.getByTestId("scenario-card-article");
  await expect(sc).toContainText("3 steps · 1 agent");
  await expect(sc).not.toContainText("article.yaml");
  await expect(sc.getByLabel("Step types: ask, jev, output")).toBeVisible();
});

test("C5 validation error and fix in the panel and in YAML", async ({ page, project }) => {
  const disk = () => project.read("scenarios/demo.yaml");
  const original = disk();
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await card(page, "write").click();
  const prompt = page.getByRole("combobox", { name: "Prompt" });
  await prompt.fill("Topic: {{ steps.missing.text }}");
  // live validation (render) — error on the card before Save
  await expect(cardBox(page, "write")).toContainText("step 'missing' does not exist");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText("The change failed validation (1 error) and was not written.");
  await expect(page.getByRole("button", { name: "1 error" })).toBeVisible();
  await expect(page.getByRole("complementary").getByText(/step 'missing' does not exist \(available:/)).toBeVisible();
  await expect(prompt).toHaveAttribute("aria-invalid", "true");
  expect(disk()).toBe(original);

  await prompt.fill("Topic: {{ inputs.topic }}");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  await expect(cardBox(page, "write")).not.toContainText("does not exist");
  expect(disk()).toContain('prompt: "Topic: {{ inputs.topic }}"');

  await page.getByRole("radio", { name: "YAML" }).click();
  const area = page.getByRole("textbox", { name: "scenarios/demo.yaml" });
  await expect(page.getByText("You are editing workflows/scenarios/demo.yaml directly")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  const good = await area.inputValue();
  const line = good.split("\n").findIndex((l) => l.includes("- id: write")) + 1;
  await area.fill(good.replace("  - id: write", "  - id: [write"));
  const form = page.getByRole("radio", { name: "Form" });
  await expect(page.getByText(/^line \d+ ·/).first()).toBeVisible({ timeout: 1500 });
  const bad = Number((await page.getByText(/^line \d+ ·/).first().textContent())!.match(/line (\d+)/)![1]);
  expect(Math.abs(bad - line)).toBeLessThanOrEqual(1);
  await expect(page.getByTestId(`yaml-line-${bad}`)).toBeVisible();
  await expect(form).not.toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await form.click();
  const syntaxDialog = page.getByRole("dialog", { name: "Unsaved changes" });
  await expect(syntaxDialog).toBeVisible();
  await syntaxDialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page).toHaveURL(/mode=yaml/);

  await area.fill(good.replace("agent: writer", "agent: nobody"));
  await expect(page.getByText(/write · .*agent 'nobody'/)).toBeVisible();
  await expect(form).not.toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  const fixed = good.replace("What to write about", "What to write about (edited)");
  await area.fill(fixed);
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  expect(disk()).toBe(fixed);
  // back to Form selects the step under the cursor
  await area.evaluate((el: HTMLTextAreaElement) => {
    const i = el.value.indexOf("agent: writer");
    el.focus();
    el.setSelectionRange(i, i);
  });
  await area.press("ArrowRight");
  await form.click();
  await expect(page).toHaveURL(/step=write/);
  await expect(page).not.toHaveURL(/mode=yaml/);

  // Form → YAML with an unsaved change: text from render, no dialog
  await page.getByRole("combobox", { name: "Prompt" }).fill("Topic of the day: {{ inputs.topic }}");
  await page.getByRole("radio", { name: "YAML" }).click();
  await expect(area).toHaveValue(/prompt: "Topic of the day: \{\{ inputs\.topic \}\}"/);
  await expect(saveStatus(page)).toHaveText("Unsaved");
  // YAML → Form takes the unsaved text via render; only a syntax error keeps the dialog.
  const yamlDraft = (await area.inputValue()).replace("Topic of the day:", "Topic from YAML:").replace("agent: writer", "agent: nobody");
  await area.fill(yamlDraft);
  await area.evaluate((el: HTMLTextAreaElement) => {
    const i = el.value.indexOf("Topic from YAML:");
    el.focus();
    el.setSelectionRange(i, i);
  });
  await area.press("ArrowRight");
  await page.getByRole("radio", { name: "Form" }).click();
  await expect(page.getByRole("dialog", { name: "Unsaved changes" })).toBeHidden();
  await expect(page.getByRole("complementary").getByRole("combobox", { name: "Prompt" })).toHaveValue("Topic from YAML: {{ inputs.topic }}");
  await expect(cardBox(page, "write")).toContainText("agent 'nobody' does not exist");
  expect(disk()).toContain('prompt: "Topic: {{ inputs.topic }}"');
  await page.getByRole("complementary").getByRole("combobox", { name: "Agent" }).selectOption("writer");
  await expect(cardBox(page, "write")).not.toContainText("does not exist");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  expect(disk()).toContain('prompt: "Topic from YAML: {{ inputs.topic }}"');
});

test("C9 file conflict", async ({ page, project }) => {
  const file = path.join(project.wf, "scenarios/demo.yaml");
  page.on("dialog", (d) => void d.accept());
  await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("My version: {{ inputs.topic }}");
  await expect(saveStatus(page)).toHaveText("Unsaved");
  fs.appendFileSync(file, "# by hand\n");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const bar = page.getByTestId("conflict-bar");
  await expect(bar).toContainText("The file changed on disk.");
  await expect(bar.getByRole("button")).toHaveText(["Show diff", "Reload from disk and discard my changes", "Keep mine"]);
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();

  await bar.getByRole("button", { name: "Show diff" }).click();
  const diff = page.getByRole("dialog", { name: "Diff against disk" });
  await expect(diff).toContainText("− is the version you started from, + is the file on disk now.");
  await expect(diff.getByText("+ # by hand")).toBeVisible();
  await diff.getByRole("button", { name: "Close" }).click();

  await bar.getByRole("button", { name: "Keep mine" }).click();
  await expect(bar).toBeHidden();
  await page.getByRole("button", { name: "Save" }).click();
  const ow = page.getByRole("dialog", { name: "Overwrite the version on disk?" });
  const req = page.waitForRequest((r) => r.url().endsWith("/batch"));
  const current = sha(fs.readFileSync(file, "utf8"));
  await ow.getByRole("button", { name: "Overwrite the version on disk" }).click();
  expect((await req).postDataJSON().etag).toBe(current);
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  const text = fs.readFileSync(file, "utf8");
  expect(text).toContain("# by hand");
  expect(text).toContain("My version");

  // without local changes: silent reload
  fs.writeFileSync(file, text.replace("My version", "Someone else's version"));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(saveStatus(page)).toHaveText(/^Reloaded from disk \(\d{1,2}:\d{2}\s[AP]M\)$/);
  await expect(card(page, "write")).toContainText("Someone else's version");

  // a draft of an older version after a page reload
  await page.getByRole("combobox", { name: "Prompt" }).fill("Draft: {{ inputs.topic }}");
  fs.appendFileSync(file, "# by hand again\n");
  await page.reload();
  await expect(page.getByTestId("conflict-bar")).toContainText("The unsaved changes in this browser belong to an older version of the file.");
});

test("C10 moving and deleting a step with reference protection", async ({ page, project }) => {
  project.write("scenarios/article.yaml", ARTICLE);
  await page.goto(`/#/p/${project.name}/scenarios/article`);
  await card(page, "jev_1").click();
  await card(page, "jev_1").press("Alt+ArrowUp");
  await expect(card(page, "jev_1")).toHaveAttribute("aria-label", "Step 1: jev jev_1");
  await expect(card(page, "write")).toHaveAttribute("aria-label", "Step 2: ask write");
  await page.getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Undo" }).click();
  await expect(card(page, "write")).toHaveAttribute("aria-label", "Step 1: ask write");
  await page.getByRole("button", { name: "Actions for jev_1" }).click();
  for (const name of ["Move up", "Move down", "Cut", "Insert step above", "Insert step below", "Delete"])
    await expect(page.getByRole("menuitem", { name, exact: true })).toBeVisible();
  await page.keyboard.press("Escape");

  await card(page, "jev_1").focus();
  await page.keyboard.press("Control+x");
  await expect(live(page)).toHaveText("Step jev_1 cut — paste it with the + button in its new place.");
  await expect(card(page, "jev_1")).toHaveAttribute("aria-label", /— cut$/);
  await page.getByRole("button", { name: "Insert step at the start" }).click();
  const picker = page.getByRole("listbox", { name: "New step type" });
  await expect(picker.getByRole("option").first()).toHaveText("Paste “jev_1” here");
  await picker.press("Enter");
  await expect(live(page)).toHaveText("Step jev_1 pasted.");
  expect(await page.locator("[data-step-card]").evaluateAll((els) => els.map((e) => e.getAttribute("data-step-card")))).toEqual(["", "jev_1", "write", "result"]);
  // render: jev_1 now reads a step that is below it
  await expect(cardBox(page, "jev_1").locator("p.text-error")).toBeVisible();
  await card(page, "jev_1").focus();
  await page.keyboard.press("Control+z");
  expect(await page.locator("[data-step-card]").evaluateAll((els) => els.map((e) => e.getAttribute("data-step-card")))).toEqual(["", "write", "jev_1", "result"]);

  const original = project.read("scenarios/article.yaml");
  await card(page, "write").focus();
  await page.keyboard.press("Delete");
  const del = page.getByRole("dialog", { name: "Delete step “write”?" });
  await expect(del).toContainText("Step “write” is read by jev_1, result. Saving only succeeds if you update their references or delete them too");
  await del.getByRole("button", { name: "Delete anyway" }).click();
  await expect(live(page)).toHaveText("Step write deleted. Undo: Ctrl+Z.");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^The change failed validation/);
  await expect(cardBox(page, "result")).toContainText("write");
  expect(project.read("scenarios/article.yaml")).toBe(original);

  // updating the readers + deleting in one batch
  // the jev_1 panel is open from the start (Esc in the ⋯ menu closed only the menu, not the panel)
  await expect(card(page, "jev_1")).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("combobox", { name: "State" }).fill("{{ inputs.topic }}");
  await card(page, "result").click();
  await page.getByRole("combobox", { name: "text" }).fill("{{ inputs.topic }}");
  const req = page.waitForRequest((r) => r.url().endsWith("/batch"));
  await page.getByRole("button", { name: "Save" }).click();
  const ops = (await req).postDataJSON().ops as { op: string }[];
  expect(ops.map((o) => o.op).sort()).toEqual(["delete_step", "update_step", "update_step"]);
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  expect(project.yaml<Scn>("scenarios/article.yaml").steps.map((s) => s.id)).toEqual(["jev_1", "result"]);

  // a step nobody reads disappears without a dialog
  await card(page, "jev_1").focus();
  await page.keyboard.press("Delete");
  await expect(page.getByRole("dialog")).toBeHidden();
  const req2 = page.waitForRequest((r) => r.url().endsWith("/batch"));
  await page.getByRole("button", { name: "Save" }).click();
  expect((await req2).postDataJSON().ops).toEqual([{ op: "delete_step", address: ["steps", 0] }]);
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  expect(project.yaml<Scn>("scenarios/article.yaml").steps.map((s) => s.id)).toEqual(["result"]);

  // output: no move, cut or insert below; the card does not delete outside ⋯
  await page.getByRole("button", { name: "Actions for result" }).click();
  await expect(page.getByRole("menuitem", { name: "Insert step above" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Delete" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("region", { name: "Scenario steps" }).getByRole("button", { name: /^Delete step / })).toHaveCount(0);
});

test("C11 parallel and switch", async ({ page, project, server }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  const disk = () => project.read("scenarios/demo.yaml");
  const original = disk();
  await page.getByTestId("add-after-write").click();
  let picker = page.getByRole("listbox", { name: "New step type" });
  await picker.press("p");
  await expect(picker.getByRole("option")).toHaveText([/^parallel\s*branches in parallel$/]);
  await picker.press("Enter");
  await expect(card(page, "parallel_1")).toHaveAttribute("aria-label", "Step 2: parallel parallel_1");
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("Branches: a, b. Add steps to them with the + button in the card.");
  await page.getByRole("button", { name: "+ branch" }).click();
  const dlg = page.getByRole("dialog", { name: "branch" });
  await dlg.getByRole("textbox", { name: "Name" }).fill("short");
  await dlg.getByRole("button", { name: "Create" }).click();
  const shortBranch = page.getByTestId("branch-short");
  await expect(shortBranch).toHaveAttribute("aria-label", "short");
  await expect(shortBranch.getByRole("heading", { name: "short", level: 4 })).toBeVisible();

  // empty branches: the batch result is validated, nothing is written
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^The change failed validation/);
  expect(disk()).toBe(original);

  for (const b of ["a", "b", "short"]) {
    await page.getByTestId(`branch-${b}`).getByRole("button", { name: "Add step at the end" }).click();
    picker = page.getByRole("listbox", { name: "New step type" });
    await expect(picker.getByRole("option")).not.toContainText([/^output/]);
    await picker.press("a");
    await picker.press("Enter");
    await panel.getByRole("combobox", { name: "Agent" }).selectOption("writer");
    await panel.getByRole("combobox", { name: "Prompt" }).fill(`Branch ${b}: {{ inputs.topic }}`);
  }
  const req = page.waitForRequest((r) => r.url().endsWith("/batch"));
  await page.getByRole("button", { name: "Save" }).click();
  expect((await req).postDataJSON().ops.map((o: { op: string }) => o.op)).toEqual(["add_step"]);
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  type Par = { parallel: Record<string, { id: string }[]> };
  const par = project.yaml<Scn>("scenarios/demo.yaml").steps[1] as unknown as Par;
  expect(Object.keys(par.parallel)).toEqual(["a", "b", "short"]);
  expect(Object.values(par.parallel).map((l) => l.length)).toEqual([1, 1, 1]);
  await expect(card(page, "parallel_1")).toContainText("a ∥ b ∥ short");
  await expect(card(page, "parallel_1")).toContainText("3 branches, run in parallel");

  const collapse = page.getByRole("button", { name: "Collapse parallel_1" });
  await expect(collapse).toHaveAttribute("aria-expanded", "true");
  await collapse.click();
  await expect(shortBranch).toBeHidden();
  await expect(card(page, "parallel_1").locator("xpath=../../..")).toContainText("3 steps");
  await page.getByRole("button", { name: "Expand parallel_1" }).click();
  await expect(shortBranch).toBeVisible();

  // a container is deleted with its contents → dialog
  await card(page, "parallel_1").focus();
  await page.keyboard.press("Delete");
  await expect(page.getByRole("dialog")).toContainText("This also deletes 3 steps inside.");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

  // switch
  await page.getByTestId("add-after-parallel_1").click();
  picker = page.getByRole("listbox", { name: "New step type" });
  await picker.press("s");
  await picker.press("w");
  await picker.press("Enter");
  await expect(panel).toContainText("“otherwise” is always written");
  await panel.getByRole("combobox", { name: "Value" }).fill("steps.write.text");
  await expect(page.getByTestId("case-default")).toBeVisible();
  await page.getByRole("button", { name: "+ case" }).click();
  const pd = page.getByRole("dialog", { name: "case" });
  await pd.getByRole("textbox", { name: "Name" }).fill("approved");
  await pd.getByRole("button", { name: "Create" }).click();
  await page.getByTestId("case-approved").getByRole("button", { name: "Add step at the end" }).click();
  await page.getByRole("listbox", { name: "New step type" }).press("f");
  await page.getByRole("listbox", { name: "New step type" }).press("Enter");
  await panel.getByRole("combobox", { name: "Message" }).fill("Should not happen");
  // `default` is required (scenario.md D1d) — the GUI always writes it; empty = a deliberate “do nothing”
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  expect((project.yaml<Scn>("scenarios/demo.yaml").steps[2] as unknown as { switch: { default: unknown[] } }).switch.default).toEqual([]);

  await page.getByTestId("case-default").getByRole("button", { name: "Add step at the end" }).click();
  picker = page.getByRole("listbox", { name: "New step type" });
  await picker.press("s");
  await picker.press("e");
  await picker.press("Enter");
  await panel.getByRole("button", { name: "Add value" }).click();
  await panel.getByRole("combobox").last().fill("inputs.topic");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  const sw = project.yaml<Scn>("scenarios/demo.yaml").steps[2] as unknown as { switch: { value: string; cases: Record<string, unknown[]>; default: unknown[] } };
  expect(sw.switch.value).toBe("steps.write.text");
  expect(Object.keys(sw.switch.cases)).toEqual(["approved"]);
  expect(sw.switch.default).toHaveLength(1);

  // in the run: the unselected case is dimmed, branches show their status
  const id = await startRun(server, project.name, "demo");
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/runs/${id}`);
  const unselected = page.getByTestId("case-approved").locator("[data-step-card]");
  await expect(unselected).toHaveAttribute("aria-label", /— skipped$/);
  await expect(unselected).toContainText("skipped:");
  await expect(unselected).toHaveCSS("border-top-style", "dashed"); // dimmed (no transparency, for contrast)
  await expect(page.getByTestId("case-default").locator("[data-step-card]")).toHaveAttribute("aria-label", /— succeeded$/);
  for (const b of ["a", "b", "short"])
    await expect(page.getByTestId(`branch-${b}`).locator("[data-step-card]")).toHaveAttribute("aria-label", /— succeeded$/);
});

test("C12 renaming a step rewrites references", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
  const panel = page.getByRole("complementary");
  const details = panel.getByRole("button", { name: /^Step details/ });
  await details.click();
  await expect(details).toHaveAttribute("aria-expanded", "true");
  await expect(panel.getByText("Reads from")).toBeVisible();
  await expect(panel.locator("dd").first()).toHaveText("nothing");
  await expect(panel.getByRole("link", { name: "Open in YAML" })).toHaveAttribute("href", /step=write&mode=yaml|mode=yaml.*step=write/);
  await panel.getByRole("button", { name: "result", exact: true }).click();
  await expect(page).toHaveURL(/step=result/);
  await card(page, "write").click();
  await panel.getByRole("button", { name: /^Step details/ }).click();

  const id = panel.getByRole("textbox", { name: "id" });
  await id.fill("1");
  await expect(id).toHaveValue(""); // without a leading letter nothing is left
  await expect(panel.getByText("Lowercase letters, digits and _; starts with a letter.")).toBeVisible();
  await id.fill("Résult");
  await expect(id).toHaveValue("result");
  await expect(panel.getByText("“result” already exists.")).toBeVisible();
  await id.press("Tab");
  await expect(card(page, "write")).toBeVisible();

  await id.fill("article_text");
  await id.press("Tab");
  const dlg = page.getByRole("dialog", { name: "Rewrite references in 1 step?" });
  await expect(dlg.getByRole("listitem")).toHaveText(["result"]);
  await dlg.getByRole("button", { name: "Rename and rewrite references" }).click();
  await expect(card(page, "article_text")).toHaveAttribute("aria-label", "Step 1: ask article_text");
  await expect(page).toHaveURL(/step=article_text/);
  await page.waitForTimeout(800); // render
  await expect(cardBox(page, "result").locator("p.text-error")).toHaveCount(0);

  const req = page.waitForRequest((r) => r.url().endsWith("/scenarios/demo/batch"));
  await page.getByRole("button", { name: "Save" }).click();
  expect((await req).postDataJSON().ops[0]).toEqual({ op: "rename_step", address: ["steps", 0], new_id: "article_text", rename_refs: true });
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  const text = project.read("scenarios/demo.yaml");
  expect(text).toContain("- id: article_text");
  expect(text).toContain("{{ steps.article_text.text }}");
});

test("C15 keyboard path without a mouse", async ({ page, project }) => {
  await page.goto("/");
  await tabTo(page, page.getByRole("link", { name: project.name, exact: true }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Scenarios", level: 1 })).toBeVisible();
  await tabTo(page, page.getByRole("button", { name: "New scenario" }));
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New scenario" });
  await expect(dialog.getByRole("textbox", { name: "Name" })).toBeFocused();
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "New scenario" })).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.type("keyboard");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/scenarios\/keyboard/);

  await tabTo(page, card(page, ""));
  await page.keyboard.press("ArrowDown");
  await expect(card(page, "write")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/step=write/);
  const panel = page.getByRole("complementary");
  await expect(panel.getByRole("combobox", { name: "Step type" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(card(page, "write")).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Actions for write" })).toBeFocused();
  await page.keyboard.press("Tab");
  const plus = page.getByTestId("add-after-write");
  await expect(plus).toBeFocused();
  await expect(plus).toHaveAccessibleName("Insert step after write");
  expect(await plus.evaluate((el) => getComputedStyle(el).boxShadow)).not.toBe("none"); // focus-visible ring
  await expect(plus).toHaveCSS("opacity", "1");
  await page.keyboard.press("Enter");
  const picker = page.getByRole("listbox", { name: "New step type" });
  await expect(picker).toBeFocused();
  await page.keyboard.press("j");
  await expect(picker.getByText("filter: j")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(plus).toBeFocused();

  await tabTo(page, card(page, "write"), 10, "Shift+Tab");
  await page.keyboard.press("Delete");
  const del = page.getByRole("dialog", { name: "Delete step “write”?" });
  await expect(del.getByRole("button", { name: "Delete anyway" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(del).toBeHidden();

  await tabTo(page, page.getByRole("button", { name: "Actions for write" }));
  await page.keyboard.press("Enter");
  const items = page.getByRole("menuitem");
  await expect(items.first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(items.nth(1)).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Actions for write" })).toBeFocused();

  // header by keyboard: Enter → focus in the panel, typing, Ctrl+S
  await tabTo(page, card(page, ""), 20, "Shift+Tab");
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("textbox", { name: /^description/ })).toBeFocused();
  await page.keyboard.press("End");
  await page.keyboard.type(" from the keyboard");
  await page.keyboard.press("Control+s");
  await expect(saveStatus(page)).toHaveText(/^Saved ✓ \d/);
  await expect(page.locator("[aria-live]").first()).toBeAttached();
  expect(project.read("scenarios/keyboard.yaml")).toMatch(/description: .* from the keyboard/);
});

test("N1 server not responding", async ({ page, project, server }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Offline: {{ inputs.topic }}");
  await expect(saveStatus(page)).toHaveText("Unsaved");
  await page.route(/\/projects/, (r) => r.abort());
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const bar = page.getByTestId("server-bar");
  await expect(bar).toHaveText(`The agencast server is not responding (127.0.0.1:${server.port}), retrying…`);
  await expect(bar).toHaveRole("alert");
  await expect(card(page, "write")).toContainText("Offline");
  await expect(saveStatus(page)).toHaveText("Unsaved");
  expect(await page.evaluate(() => Object.keys(localStorage).some((k) => k.startsWith("agencast.draft.")))).toBe(true);
  await page.unroute(/\/projects/);
  await expect(bar).toBeHidden({ timeout: 7_000 });
});

test("N6 leaving with unsaved changes", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Unsaved: {{ inputs.topic }}");
  await expect(saveStatus(page)).toHaveText("Unsaved");
  const kinds: string[] = [];
  page.on("dialog", (d) => (kinds.push(d.type()), void d.accept()));
  await page.reload();
  expect(kinds).toContain("beforeunload");
  await expect(saveStatus(page)).toHaveText("Unsaved");
  await expect(card(page, "write")).toContainText("Unsaved:");

  // a link to another GUI page asks; dismissing = stay
  page.removeAllListeners("dialog");
  page.once("dialog", (d) => (kinds.push(d.type()), void d.dismiss()));
  await page.getByRole("main").getByRole("link", { name: "Scenarios", exact: true }).click();
  await expect(page).toHaveURL(/scenarios\/demo/);
  expect(kinds.at(-1)).toBe("confirm");
  page.once("dialog", (d) => void d.accept());
  await page.getByRole("main").getByRole("link", { name: "Scenarios", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`#/p/${project.name}/scenarios$`));

  await expect(page.getByRole("button", { name: "New scenario" })).toBeVisible();
  await page.getByRole("link", { name: "demo" }).click();
  await page.getByRole("button", { name: /Step 1: ask write/ }).click();
  await page.getByRole("combobox", { name: /Prompt/ }).fill("Back: {{ inputs.topic }}");
  page.once("dialog", (d) => (kinds.push(d.type()), void d.dismiss()));
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`#/p/${project.name}/scenarios/demo`));
  expect(kinds.at(-1)).toBe("confirm");
});

// Tuning 2026-09-26: a model alias in Config has a hyphenated name (like an agent) and is written in the style of the other aliases.
test("C17 hyphenated model alias in Config", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/config`);
  await page.getByRole("button", { name: "+ alias" }).click();
  const alias = page.getByRole("textbox", { name: "Alias" }).last();
  await expect(alias).toHaveValue("model-1");
  await alias.fill("1");
  await expect(alias).toHaveAttribute("aria-invalid", "true");
  await alias.press("Enter");
  await expect(alias).toHaveValue("model-1"); // an invalid name reverts
  await alias.fill("GPT image");
  await expect(alias).toHaveValue("gpt-image"); // the name is normalized while typing
  await alias.press("Enter");
  await expect(page.getByRole("textbox", { name: "Alias" }).last()).toHaveValue("gpt-image");
  await page.getByRole("textbox", { name: "Model id for gpt-image" }).fill("openai/gpt-image-2");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/Saved/);
  const text = project.read("config.yaml");
  expect(text).toContain("  gpt-image: {id: openai/gpt-image-2}\n");
  expect(text).toContain("  smart:       { id: anthropic/claude-haiku-4.5 }\n"); // other lines verbatim
  // after reloading, the alias is in the agent's model menu
  await page.goto(`/#/p/${project.name}/agents/writer`);
  await expect(page.getByRole("combobox", { name: /^model/ }).locator("option", { hasText: "gpt-image — openai/gpt-image-2" })).toHaveCount(1);
});

test("C18 inserting a variable from the menu with mouse and keyboard", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await page.getByRole("button", { name: /Step 1: ask write/ }).click();
  const prompt = page.getByRole("combobox", { name: /Prompt/ });
  const insert = page.getByRole("button", { name: "Insert variable" });

  await prompt.fill("Write a long text");
  await prompt.click({ position: { x: 72, y: 12 } });
  await insert.click();
  await page.getByRole("menuitem", { name: "inputs.topic" }).click();
  await expect(prompt).toHaveValue(/{{ inputs\.topic }}/);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  expect(project.read("scenarios/demo.yaml")).toContain("{{ inputs.topic }}");

  await prompt.fill("More text");
  await prompt.press("Tab");
  await expect(insert).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(prompt).toHaveValue(/{{ inputs\.topic }}/);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(saveStatus(page)).toHaveText(/^Saved ✓/);
  expect(project.read("scenarios/demo.yaml")).toContain("More text{{ inputs.topic }}");
});

test("C19 renaming a scenario rewrites call and navigates to the new name", async ({ page, project }) => {
  project.write("scenarios/demo.yaml", project.read("scenarios/demo.yaml").replace(
    /^name: demo$/m, "name: demo\ncallable: true"));
  project.write("scenarios/caller.yaml", `version: 1
name: caller
description: Calls demo
inputs:
  topic: { type: string, default: coffee }
outputs:
  text: { type: string }
steps:
  - id: run_demo
    call:
      scenario: demo
      inputs:
        topic: "{{ inputs.topic }}"
  - id: result
    output:
      text: "{{ steps.run_demo.text }}"
`);
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await page.getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Rename" }).click();
  const dialog = page.getByRole("dialog", { name: "Rename scenario “demo”?" });
  await expect(dialog.getByRole("textbox", { name: "Name" })).toHaveValue("demo");
  await dialog.getByRole("textbox", { name: "Name" }).fill("intro");
  await dialog.getByRole("button", { name: "Rename" }).click();

  await expect(page).toHaveURL(new RegExp(`/scenarios/intro(?:\\?|$)`));
  await expect(page.getByRole("heading", { name: "intro", level: 1 })).toBeVisible();
  expect(project.yaml<{ name: string }>("scenarios/intro.yaml").name).toBe("intro");
  expect(project.yaml<{ steps: { call: { scenario: string } }[] }>("scenarios/caller.yaml").steps[0].call.scenario).toBe("intro");
  expect(fs.existsSync(path.join(project.wf, "scenarios/demo.yaml"))).toBe(false);
  await expect(page.getByText(/^Updated:/)).toContainText("scenarios/intro.yaml");
  await expect(page.getByText(/^Updated:/)).toContainText("scenarios/caller.yaml");
});
