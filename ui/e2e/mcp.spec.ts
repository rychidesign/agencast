// Journey C21 (docs/ui/user-journeys.md): MCP servers belong to the project owner — Config only shows them, a project
// registered over HTTP runs none until `agencast projects trust`, and the run viewer shows a tool call that did not return.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { AGENCAST, expect, REPO, startRun, test, VENV, waitRun } from "./fixtures";

/** The owner's file, written on disk: the framework's fake stdio server (tools `red_pixel`, `slow`, …). */
const MCP = `version: 1
servers:
  fs:
    description: Fake server for tests
    command: ${JSON.stringify(path.join(VENV, "python"))}
    args: [${JSON.stringify(path.join(REPO, "framework/tests/fake_mcp_server.py"))}, "{run_dir}/work"]
    agents: [tester]
    timeouts: { call: 6s }
`;
const tester = (mcp: string) => `---
version: 1
name: tester
description: Test agent
model: smart
${mcp}limits: { max_turns: 5, budget_usd: 0.5 }
---
You are a test agent.
`;
/** Step \`probe\` (FAKE): \`fs.red_pixel\`, then \`fs.slow\` for 60 s — longer than the server's call timeout. */
const TOOLS = `version: 1
name: tools
description: Calls tools of an MCP server
steps:
  - id: probe
    task: { agent: tester, prompt: "Complete the task" }
`;

test("C21 MCP servers are the owner's: read-only Config, untrusted notice, a tool call that did not return", async ({ page, project, server }) => {
  const { name } = project;
  project.write("mcp.yaml", MCP);
  project.write("agents/tester.md", tester(""));
  project.write("scenarios/tools.yaml", TOOLS);
  const command = `agencast projects trust ${name}`;
  const notice = page.getByTestId("untrusted-notice");
  const asked: string[] = [];
  page.on("request", (r) => void (r.url().includes("mcp.yaml") && asked.push(`${r.method()} ${r.url()}`)));
  page.on("dialog", (d) => void d.accept());  // leaving the agent with the refused change

  // Config: the server as a card in both modes, one sentence about the owner, the command for the untrusted project
  await page.goto(`/#/p/${name}/config`);
  const card = page.getByRole("listitem").filter({ hasText: "Fake server for tests" });
  await expect(card).toContainText("stdio");
  await expect(card).toContainText("tester");
  await expect(page.getByText(/set up by the project owner in workflows\/mcp\.yaml on the server/)).toHaveCount(1);
  await expect(notice).toContainText(command);
  await expect(notice.getByRole("button")).toHaveAccessibleName("Copy command");  // nothing here changes trust
  await page.getByRole("radio", { name: "YAML" }).click();
  await expect(page.getByRole("textbox", { name: "config.yaml" })).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(1);  // no second block with mcp.yaml
  await expect(card).toBeVisible();
  await expect(page.getByTestId("save-status")).not.toContainText("error");
  expect(asked).toEqual([]);
  expect((await server.api("GET", `/projects/${name}/files/mcp.yaml`)).status).toBe(404);

  // giving the agent a server would make the scenario use it: the server refuses the change and names the command
  await page.goto(`/#/p/${name}/agents/tester`);
  await page.getByRole("checkbox", { name: /^fs/ }).check();
  await page.getByRole("textbox", { name: /Tools of fs/ }).fill("red_pixel, slow");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("save-status")).toContainText("failed validation");
  await expect(page.getByText(/MCP servers \(fs\) are disabled/)).toContainText(command);
  expect(project.read("agents/tester.md")).toBe(tester(""));
  // the owner writes the agent by hand on disk
  project.write("agents/tester.md", tester("mcp: [fs]\ntools: { fs: [red_pixel, slow] }\n"));

  // the run form names the command before the start; the server refuses the dry run with the same message
  await page.goto(`/#/p/${name}/scenarios/tools`);
  await page.getByRole("button", { name: "Run" }).click();
  const panel = page.getByRole("complementary");
  await expect(panel.getByTestId("untrusted-notice")).toContainText(command);
  await panel.getByRole("button", { name: "Start dry run" }).click();
  await expect(panel.getByRole("alert")).toContainText("failed validation");
  await expect(panel.getByRole("listitem").filter({ hasText: "MCP servers (fs) are disabled" })).toContainText(command);
  await expect(page).toHaveURL(new RegExp(`#/p/${name}/scenarios/tools$`));
  // a scenario without MCP servers is not affected
  await page.goto(`/#/p/${name}/scenarios/demo`);
  await page.getByRole("button", { name: "Run" }).click();
  await expect(panel.getByRole("button", { name: "Start dry run" })).toBeVisible();
  await expect(notice).toHaveCount(0);

  // the owner allows the servers in a terminal: the notices are gone
  const trust = spawnSync(AGENCAST, ["projects", "trust", name, "--yes"], { env: server.env, encoding: "utf8" });
  expect(trust.status, trust.stderr).toBe(0);
  await page.goto(`/#/p/${name}/config`);
  await expect(card).toBeVisible();
  await expect(notice).toHaveCount(0);
  await page.goto(`/#/p/${name}/scenarios/tools`);
  await page.getByRole("button", { name: "Run" }).click();
  await expect(panel.getByRole("button", { name: "Start dry run" })).toBeVisible();
  await expect(notice).toHaveCount(0);

  // a run: while the server is running its stderr log is not in the run yet — the link leads to a sentence, not to a 404
  const id = await startRun(server, name, "tools");
  const log = "mcp/fs.stderr.log";
  const failed: string[] = [];
  page.on("response", (r) => void (r.status() === 404 && failed.push(r.url())));
  await page.goto(`/#/p/${name}/runs/${id}?step=probe`);
  await panel.getByRole("tab", { name: "Tools" }).click();
  await expect(panel.getByText("fs.red_pixel")).toBeVisible();
  await panel.getByRole("button", { name: log }).click();
  await expect(page.getByText("The stderr log of a local MCP server is written when the server stops")).toBeVisible();
  // the run ends (the second call timed out), the server stops and the same page shows the log
  await waitRun(server, name, id, ["failed"]);
  await expect(page.getByText(/fake-mcp: root/)).toBeVisible();
  expect(failed).toEqual([]);

  // Tools: the call that did not return carries its error
  await page.goto(`/#/p/${name}/runs/${id}?step=probe`);
  await panel.getByRole("tab", { name: "Tools" }).click();
  const slow = panel.getByRole("listitem").filter({ hasText: "fs.slow" });
  await expect(slow).toContainText("tool fs.slow did not respond within 6 s (may have run)");
  await expect(slow).not.toContainText("tool returned an error");
  await expect(panel.getByRole("button", { name: log })).toBeVisible();
});
