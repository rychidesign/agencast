// Journeys C6–C8 and state N5 (docs/ui/user-journeys.md): starting a run, reading the result, failed and interrupted runs.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import { AGENCAST, FAILING, countRequests, SLOW, expect, startRun, test, waitRun } from "./fixtures";

const card = (page: Page, id: string) => page.locator(`[data-step-card="${id}"]`);
const runIdFromUrl = (page: Page) => decodeURIComponent(page.url().split("/runs/")[1].split("?")[0]);
const REQUIRED_INPUT = SLOW.replace("name: slow", "name: required").replace("topic: { type: string, default: coffee }", "topic: { type: string, required: true }");

test("C6 starting a run with the inputs form (dry run, live, following)", async ({ page, project, server }) => {
  project.write("scenarios/slow.yaml", SLOW);
  project.write("scenarios/required.yaml", REQUIRED_INPUT);
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("START RUN");
  await expect(panel.getByRole("textbox", { name: "topic" })).toHaveValue("coffee");
  await expect(panel.getByText("string · What to write about")).toBeVisible();
  await expect(panel.getByRole("radio", { name: /Dry run/ })).toBeChecked();
  await expect(panel.getByText("Plan only (plan.md): no model calls; starts the MCP servers to list their tools.")).toBeVisible();

  // a required input without a default: nothing is sent without a value
  await page.goto(`/#/p/${project.name}/scenarios/required`);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const posts = await countRequests(page, (u, m) => m === "POST" && u.endsWith("/runs"), async () => {
    await panel.getByRole("button", { name: "Start dry run" }).click();
    await expect(panel.getByText("Required input.")).toBeVisible();
  });
  expect(posts).toBe(0);

  // dry run
  await page.goto(`/#/p/${project.name}/scenarios/demo`);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await panel.getByRole("textbox", { name: "topic" }).fill("new coffee");
  const dry = page.waitForResponse((r) => r.url().endsWith(`/projects/${project.name}/runs`) && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Start dry run" }).click();
  expect((await dry).status()).toBe(200);
  expect((await dry).request().postDataJSON()).toEqual({ scenario: "demo", inputs: { topic: "new coffee" }, dry_run: true });
  await expect(page).toHaveURL(/#\/p\/[^/]+\/runs\/[^?]+$/);
  const dryId = runIdFromUrl(page);
  await expect(page.getByTestId("run-state")).toHaveText("plan only (dry run)");
  await expect(page.getByText(/This is only a plan \(dry run\) — no step ran and no model was called/)).toBeVisible();
  await expect(page.locator("main h1, main h2").filter({ hasText: /plan|Plan|demo/ }).first()).toBeVisible();
  const dryDir = path.join(project.runsDir, dryId);
  expect(fs.existsSync(path.join(dryDir, "plan.md"))).toBe(true);
  expect(JSON.parse(fs.readFileSync(path.join(dryDir, "inputs.json"), "utf8"))).toEqual({ topic: "new coffee" });
  expect(fs.existsSync(path.join(dryDir, "events.jsonl"))).toBe(false);

  // live with an unsaved change: limits and warning
  await page.goto(`/#/p/${project.name}/scenarios/demo?step=write`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Unsaved {{ inputs.topic }}");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await panel.getByRole("radio", { name: /Live run/ }).check();
  const limits = panel.getByRole("definition");
  await expect(panel.getByLabel("Run limits")).toBeVisible();
  await expect(limits).toHaveText(["1.00 USD", "0.30 USD", "1h", "0.00 USD"]); // daily spend: two places (wave G), run costs four
  await expect(panel.getByText("You have unsaved changes — the run will use the version on disk.")).toBeVisible();
  const live = page.waitForResponse((r) => r.url().endsWith(`/projects/${project.name}/runs`) && r.request().method() === "POST");
  page.once("dialog", (d) => void d.accept());
  await panel.getByRole("button", { name: "Start live run" }).click();
  expect((await live).status()).toBe(202);
  await expect(page).toHaveURL(/#\/p\/[^/]+\/runs\/[^?]+$/);

  // live run slow (step slowly sleeps 4 s)
  await page.goto(`/#/p/${project.name}/scenarios/slow`);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await panel.getByRole("radio", { name: /Live run/ }).check();
  await panel.getByRole("button", { name: "Start live run" }).click();
  await expect(page).toHaveURL(/runs\//);
  const liveId = runIdFromUrl(page);
  await expect(page.getByTestId("run-state")).toHaveText("running");
  await expect(page.getByText("fake run")).toBeVisible();
  await expect(card(page, "slowly")).toHaveAttribute("aria-label", /— running$/);
  await expect(page.locator("header p[aria-live]")).toHaveText("step slowly running");
  await expect(page.getByRole("checkbox", { name: "follow run" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Run finished" })).toHaveText("Run finished: succeeded", { timeout: 15_000 });
  await expect(card(page, "slowly")).toHaveAttribute("aria-label", /— succeeded$/);
  await expect(page.getByRole("checkbox", { name: "follow run" })).toBeHidden();
  const polls = await countRequests(page, (u) => u.includes(`/runs/${liveId}`), () => page.waitForTimeout(6_000));
  expect(polls).toBe(0);
  const dir = path.join(project.runsDir, liveId);
  for (const f of ["run.lock", "events.jsonl", "scenario/slow.yaml", "steps/01-slowly", "summary.md", "report.html"])
    expect(fs.existsSync(path.join(dir, f)), f).toBe(true);

  // run list: two starts at once → the second waits in the queue
  const a = await startRun(server, project.name, "slow");
  const b = await startRun(server, project.name, "slow");
  await page.goto(`/#/p/${project.name}/runs`);
  await expect(page.getByTestId(`run-row-${a}`)).toContainText(/step 1\/2 · slowly/);
  await expect(page.getByTestId(`run-row-${a}`)).toContainText("fake run");
  await expect(page.getByTestId(`run-row-${a}`).getByText("running", { exact: true })).toBeAttached();
  await expect(page.getByTestId(`run-row-${b}`)).toContainText("queued (#2)");
  await expect(page.getByText("1 running · 1 queued")).toBeVisible();
  await waitRun(server, project.name, b, ["succeeded"]);
});

test("C7 reading the result and cost", async ({ page, project, server }) => {
  const id = await startRun(server, project.name, "demo", { inputs: { topic: "new coffee" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/runs/${id}`);
  const h1 = page.getByRole("heading", { level: 1 });
  await expect(h1.getByRole("link", { name: "demo" })).toBeVisible();
  await expect(page.locator("main header").getByText(id, { exact: true })).toBeVisible(); // run_id under the title
  await expect(page.getByRole("link", { name: "Open scenario" })).toHaveAttribute("href", `#/p/${project.name}/scenarios/demo`);
  await expect(page.getByTestId("run-state")).toHaveText("succeeded");
  await expect(page.getByTestId("run-duration")).toHaveText(/^\d+\.\d\ss$/); // NBSP between the number and the unit
  await expect(page.getByTestId("run-cost")).toHaveText(/^\d+\.\d{4} USD$/);
  await expect(page.getByText(/Inputs\s*topic = “new coffee”/)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Run sections" }).getByRole("link")).toHaveText(["Steps", "Summary", "Report", "Files"]);

  await expect(card(page, "write")).toHaveAttribute("aria-label", "Step 1: ask write — succeeded");
  await expect(card(page, "write")).toContainText("smart → anthropic/claude-haiku-4.5");
  await expect(page.getByTestId("step-duration-write")).toHaveText(/^\d+\.\d\ss$/);
  await expect(card(page, "result")).toHaveAttribute("aria-label", "Step 2: output result — succeeded");
  const detail = page.waitForResponse((r) => r.url().endsWith(`/runs/${id}/steps/write`));
  await card(page, "write").click();
  expect((await detail).status()).toBe(200);
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("STEP 1");
  await expect(panel).toContainText("write");
  for (const width of [1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect((await panel.locator("xpath=..").boundingBox())!.width).toBeCloseTo(520, 0);
  }
  const tabs = panel.getByRole("tablist", { name: "Step sections" }).getByRole("tab");
  await expect(tabs).toContainText(["Prompt", "Response", "Output", "Calls", "Files"]);
  await tabs.filter({ hasText: "Calls" }).click();
  await expect(panel.getByText("attempt 1")).toBeVisible();
  await expect(panel.getByText(/\d+ \+ \d+ tokens/)).toBeVisible();
  await tabs.filter({ hasText: "Output" }).click();
  await expect(panel.getByRole("tabpanel")).toContainText("Two sentences.");

  const nav = page.getByRole("navigation", { name: "Run sections" });
  await nav.getByRole("link", { name: "Summary" }).click();
  await expect(page.getByText("Total").first()).toBeVisible();
  await nav.getByRole("link", { name: "Report" }).click();
  await expect(page.locator("iframe[sandbox][title='Run report']")).toBeVisible();
  await nav.getByRole("link", { name: "Files" }).click();
  await page.getByRole("navigation", { name: "Files" }).getByText("summary.md", { exact: true }).click();
  await expect(page).toHaveURL(/file=summary\.md/);

  await page.goto(`/#/p/${project.name}`);
  const sc = page.getByTestId("scenario-card-demo");
  await expect(sc).toContainText("succeeded");
  await expect(sc).toContainText("just now");
  await expect(page.getByTestId("spend-today")).toHaveText(/^0\.00( \/ [\d.,]+)? USD$/); // spend in the sidebar (G5)

  await page.getByRole("link", { name: "Runs", exact: true }).click();
  const req = page.waitForRequest((r) => r.url().includes("/runs?scenario=demo&limit=50"));
  await page.getByRole("combobox", { name: "Scenario filter" }).selectOption("demo");
  await req;
  await page.getByRole("combobox", { name: "Status filter" }).selectOption({ label: "succeeded" });
  await expect(page.getByTestId(`run-row-${id}`)).toBeVisible();
  await expect(page.getByTestId(`run-row-${id}`)).toContainText(/\d+\.\d{4} USD/);
  // search filters on the client by scenario name and run_id
  await page.getByRole("searchbox", { name: "Search scenario or run ID…" }).fill("no-such-thing");
  await expect(page.getByTestId(`run-row-${id}`)).toBeHidden();
  await page.getByRole("searchbox", { name: "Search scenario or run ID…" }).fill(id.slice(-4));
  await expect(page.getByTestId(`run-row-${id}`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more" })).toBeHidden();
});

test("C8 failed run", async ({ page, project, server }) => {
  project.write("scenarios/failing.yaml", FAILING);
  const id = await startRun(server, project.name, "failing");
  await waitRun(server, project.name, id, ["failed"]);
  await page.goto(`/#/p/${project.name}/runs/${id}`);
  await expect(page.getByTestId("run-state")).toHaveText("error: fail in stop");
  await expect(card(page, "write")).toHaveAttribute("aria-label", /— succeeded$/);
  await expect(card(page, "skip")).toHaveAttribute("aria-label", /— skipped$/);
  await expect(card(page, "skip")).toContainText(/skipped: .*false/);
  await expect(card(page, "stop")).toHaveAttribute("aria-label", /— failed$/);
  await expect(card(page, "stop")).toContainText("Stopped on purpose");
  await expect(card(page, "result")).toHaveAttribute("aria-label", /— not reached$/);
  await expect(card(page, "result")).toHaveCSS("border-top-style", "dashed"); // dimmed (no transparency, for contrast)
  await card(page, "skip").click();
  await expect(page.getByRole("complementary")).toContainText("default used");
  await card(page, "stop").click();
  await expect(page.getByRole("complementary").getByRole("alert")).toContainText("Stopped on purpose");
  await page.getByRole("navigation", { name: "Run sections" }).getByRole("link", { name: "Summary" }).click();
  await expect(page.getByRole("heading").filter({ hasText: "failing" }).first()).toBeVisible();
  await expect(page.getByText("Stopped on purpose").first()).toBeVisible();

  await page.goto(`/#/p/${project.name}/runs`);
  await expect(page.getByTestId(`run-row-${id}`)).toContainText("error: fail in stop");
  await expect(page.getByTestId(`run-row-${id}`)).toContainText(`${id} · fake run`);
  await page.goto(`/#/p/${project.name}`);
  await expect(page.getByTestId("scenario-card-failing")).toContainText("failed");
  const dir = path.join(project.runsDir, id);
  const events = fs.readFileSync(path.join(dir, "events.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
  expect(events.at(-1)).toMatchObject({ type: "run_finished", status: "failed" });
  expect(fs.readFileSync(path.join(dir, "summary.md"), "utf8")).toContain("Stopped on purpose");
});

test("N5 interrupted run (process killed mid-step)", async ({ page, project, server }) => {
  project.write("scenarios/slow.yaml", SLOW);
  const proc = spawn(AGENCAST, ["--project", project.root, "run", "slow", "--fake", server.fake], { env: server.env, stdio: "ignore" });
  const runDir = async () => {
    for (let i = 0; i < 100; i++) {
      const dirs = fs.existsSync(project.runsDir) ? fs.readdirSync(project.runsDir).filter((d) => d.includes("slow")) : [];
      const ev = dirs[0] && path.join(project.runsDir, dirs[0], "events.jsonl");
      if (ev && fs.existsSync(ev) && fs.readFileSync(ev, "utf8").includes('"step_started"')) return dirs[0];
      await new Promise((r) => setTimeout(r, 100));
    }
    throw new Error("the CLI run did not start a step");
  };
  const id = await runDir();
  proc.kill("SIGKILL");
  await new Promise((r) => proc.once("exit", r));

  await page.goto(`/#/p/${project.name}/runs/${id}`);
  await expect(page.getByTestId("run-state")).toHaveText("interrupted");
  await expect(page.getByText("The run ended without an end record (the process crashed or was killed); the GUI no longer polls it.")).toBeVisible();
  await expect(card(page, "slowly")).toHaveAttribute("aria-label", /— interrupted$/);
  await expect(card(page, "slowly")).not.toHaveClass(/animate-pulse/);
  const polls = await countRequests(page, (u) => u.includes(`/runs/${id}`), () => page.waitForTimeout(6_000));
  expect(polls).toBe(0);
  await page.goto(`/#/p/${project.name}/runs`);
  // the status is only in the status column; the note under run_id doesn't repeat it (wave C, fidelity §8)
  await expect(page.getByTestId(`run-row-${id}`).locator("td").nth(1)).toHaveText("interrupted");
  await expect(page.getByTestId(`run-row-${id}`).locator("td").first()).toContainText(`${id} · fake run`);
});

test("N5b interrupted run under serve (serve restart)", async ({ page, project, server }) => {
  project.write("scenarios/slow.yaml", SLOW);
  const id = await startRun(server, project.name, "slow");
  await waitRun(server, project.name, id, ["running"]);
  const before = await server.api<{ started_at: string }>("GET", `/projects/${project.name}/runs/${id}`);
  await server.restart();
  const after = await server.api<{ state: string; started_at: string; steps: { step: string; status: string }[] }>("GET", `/projects/${project.name}/runs/${id}`);
  expect(after.body.state).toBe("interrupted");
  expect(after.body.started_at).toBe(before.body.started_at);
  expect(after.body.steps.find((s) => s.step === "slowly")?.status).toBe("interrupted");
  await page.goto(`/#/p/${project.name}/runs/${id}`);
  await expect(page.getByTestId("run-state")).not.toContainText("v None");
  await expect(page.getByTestId("run-state")).toHaveText("interrupted");
  await expect(card(page, "slowly")).toHaveAttribute("aria-label", /— interrupted$/);
  await expect(card(page, "slowly")).not.toHaveClass(/animate-pulse/);
});

test("N25 run list loads the older page by cursor without duplicates", async ({ page, project }) => {
  const ids = Array.from({ length: 52 }, (_, i) => `20260926-1200${String(59 - i).padStart(2, "0")}-demo-${i.toString(16).padStart(4, "0")}`);
  const item = (run_id: string) => ({
    run_id, scenario: "demo", state: "succeeded", status: "succeeded", started_at: "2026-09-26T12:00:00.000Z",
    finished_at: "2026-09-26T12:00:01.000Z", duration_s: 1, cost_usd: 0,
  });
  const requested: string[] = [];
  await page.route((url) => new URL(url).pathname.endsWith(`/projects/${project.name}/runs`), async (route) => {
    const url = new URL(route.request().url());
    if (!url.searchParams.has("limit")) return route.continue();
    requested.push(url.searchParams.get("before") ?? "");
    if (!url.searchParams.has("before"))
      return route.fulfill({ json: { runs: ids.slice(0, 50).map(item), next_before: ids[49] } });
    return route.fulfill({ json: { runs: ids.slice(50).map(item) } });
  });
  await page.goto(`/#/p/${project.name}/runs`);
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(50);
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(rows).toHaveCount(52);
  expect(requested).toEqual(["", ids[49]]);
  const displayed = await rows.evaluateAll((els) => els.map((el) => el.getAttribute("data-testid")!.slice("run-row-".length)));
  expect(new Set(displayed).size).toBe(52);
  await expect(page.getByRole("button", { name: "Load more" })).toBeHidden();
});

// PNG signature + IHDR 4×3 — enough for the server's header check (api.md Uploads)
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52,
  0, 0, 0, 4, 0, 0, 0, 3, 8, 2, 0, 0, 0, 0, 0, 0, 0]);
const PIC = `version: 1
name: pic
description: Caption from an uploaded photo
inputs:
  photo: { type: file, required: true }
  refs: { type: files, default: [] }
outputs:
  text: { type: string }
  photo: { type: file }
steps:
  - id: write
    ask:
      agent: writer
      prompt: "Describe Image 1"
      images: ["{{ inputs.photo }}", "{{ inputs.refs }}"]
  - id: result
    output:
      text: "{{ steps.write.text }}"
      photo: "{{ inputs.photo }}"
`;

test("C6b image inputs: picked files are uploaded, previewed and sent as upload ids", async ({ page, project }) => {
  project.write("scenarios/pic.yaml", PIC);
  await page.goto(`/#/p/${project.name}/scenarios/pic`);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const panel = page.getByRole("complementary");
  await expect(panel.getByText("PNG, JPEG, WebP, GIF or AVIF, up to 10 MB; uploaded as soon as you pick it").first()).toBeVisible();
  const uploaded = page.waitForResponse((r) => r.url().endsWith(`/projects/${project.name}/uploads`) && r.request().method() === "POST");
  await panel.locator('input[type="file"]').first().setInputFiles({ name: "a.png", mimeType: "image/png", buffer: PNG });
  expect((await uploaded).status()).toBe(201);
  await expect(panel.getByRole("img", { name: "a.png" })).toBeVisible();
  await expect(panel.getByText(/4×3 png/)).toBeVisible();
  await panel.locator('input[type="file"]').nth(1).setInputFiles([
    { name: "b.png", mimeType: "image/png", buffer: PNG }, { name: "c.png", mimeType: "image/png", buffer: PNG }]);
  await expect(panel.getByRole("img", { name: "c.png" })).toBeVisible();
  await panel.getByRole("button", { name: "Remove b.png" }).click();
  await expect(panel.getByRole("img", { name: "b.png" })).toBeHidden();
  const dry = page.waitForResponse((r) => r.url().endsWith(`/projects/${project.name}/runs`) && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Start dry run" }).click();
  const sent = (await dry).request().postDataJSON();
  expect((await dry).status()).toBe(200);
  expect(sent.dry_run).toBe(true);
  expect(sent.inputs.photo.upload_id).toMatch(/^up_[0-9a-f]{32}$/);
  expect(sent.inputs.refs.map((x: { upload_id: string }) => x.upload_id)).toHaveLength(1);
  await expect(page).toHaveURL(/#\/p\/[^/]+\/runs\/[^?]+$/);
  const inputs = JSON.parse(fs.readFileSync(path.join(project.runsDir, runIdFromUrl(page), "inputs.json"), "utf8"));
  expect(inputs).toEqual({ photo: "inputs/photo.png", refs: ["inputs/refs-1.png"] });  // never the upload path
});
