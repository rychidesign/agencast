// Journeys C1, C2, C13, C14 and states N2, N3, N4 (docs/ui/user-journeys.md).
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { AGENCAST, countRequests, expect, readYaml, test, TOKEN } from "./fixtures";

type Registry = { projects: { name: string; root: string }[] };

test.describe("without a token", () => {
  test.use({ token: null });

  test("C1 first launch: token", async ({ page, project, server }) => {
    const projectCalls = await countRequests(page, (u) => u.includes("/projects"), async () => {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Server token" })).toBeVisible();
    });
    expect(projectCalls).toBe(0);
    const input = page.getByRole("textbox", { name: "Token" });
    await expect(input).toHaveAttribute("type", "password");
    await expect(page.getByText(/In registry mode, the server's AGENCAST_TOKEN variable/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
    await expect(page.getByRole("combobox", { name: "Language" })).toHaveValue("en");

    await input.fill("wrong");
    await input.press("Enter");
    await expect(page.getByRole("alert")).toHaveText("The server token doesn't match — the server returned 401.");
    expect(page.url()).not.toContain("wrong");

    const auth: string[] = [];
    page.on("request", (r) => r.url().includes("/projects") && auth.push(r.headers().authorization ?? ""));
    const cardCalls = await countRequests(page, (u, m) => m === "GET" &&
      (u.endsWith(`/projects/${project.name}`) || u.endsWith(`/projects/${project.name}/spend`)), async () => {
      await page.getByRole("textbox", { name: "Token" }).fill(TOKEN);
      await page.getByRole("textbox", { name: "Token" }).press("Enter");
      const card = page.getByTestId(`project-card-${project.name}`);
      await expect(card).toContainText(/1 scenario\s*1 agent/); // count chips (fidelity §4)
      await expect(card).toContainText("today 0.00 USD");
    });
    expect(cardCalls).toBe(0);
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(page.getByText(`${server.cfg}/projects.yaml`, { exact: true })).toBeVisible();
    const card = page.getByTestId(`project-card-${project.name}`);
    await expect(card).not.toContainText("available"); // G6: an available project has no label
    await expect(card).toContainText(/1 scenario\s*1 agent/); // count chips (fidelity §4)
    await expect(card).toContainText("today 0.00 USD");
    await expect(card).toContainText("no runs");
    expect(await page.evaluate(() => localStorage.getItem("agencast.token"))).toBe(TOKEN);
    expect(auth.length).toBeGreaterThan(0);
    expect(auth.every((a) => a === `Bearer ${TOKEN}`)).toBe(true);
  });

  test("C1b Czech on the token screen: the choice survives entering the token", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("combobox", { name: "Language" }).selectOption("cs");
    await expect(page.getByRole("heading", { name: "Token serveru" })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("agencast.lang"))).toBe("cs");
    await page.getByRole("textbox", { name: "Token" }).fill(TOKEN);
    await page.getByRole("button", { name: "Uložit" }).click();
    await expect(page.getByRole("heading", { name: "Projekty", level: 1 })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Jazyk" })).toHaveValue("cs");
  });
});

test("C2 creating a project from the GUI", async ({ page, project, server }) => {
  const name = `${project.name}-web`;
  await page.goto("/");
  await page.getByRole("button", { name: "Add project" }).click();
  const dialog = page.getByRole("dialog", { name: "New project" });
  await expect(dialog.getByRole("radio", { name: "Create new" })).toHaveAttribute("aria-checked", "true");
  const nameInput = dialog.getByRole("textbox", { name: "Name" });
  await expect(nameInput).toBeFocused();
  await nameInput.fill("Café Crème");
  await expect(nameInput).toHaveValue("cafe-creme"); // the name is normalized while typing
  await nameInput.fill(project.name);
  await expect(dialog.getByText(`“${project.name}” already exists.`)).toBeVisible();
  await nameInput.fill(name);
  const pathInput = dialog.getByRole("textbox", { name: "Path" });
  await expect(pathInput).toHaveValue(`${server.projectsRoot}/${name}`);
  await dialog.getByRole("button", { name: "Create" }).click();

  await expect(page).toHaveURL(new RegExp(`#/p/${name}$`));
  // G5: the project name in the sidebar, the header = the section, the project path only on the card and in Config
  await expect(page.getByRole("heading", { name: "Scenarios", level: 1 })).toBeVisible();
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Project sections" })).toBeVisible();
  const sc = page.getByTestId("scenario-card-demo");
  await expect(sc).toContainText("Write a short text on a given topic");
  await expect(sc).toContainText("2 steps · 1 agent");
  await expect(sc).toContainText("demo");
  await expect(sc).not.toContainText("demo.yaml");

  const root = path.join(server.projectsRoot, name);
  for (const f of ["workflows/config.yaml", "workflows/agents/writer.md", "workflows/scenarios/demo.yaml", ".env.example", ".gitignore"])
    expect(fs.existsSync(path.join(root, f)), f).toBe(true);
  expect(readYaml<Registry>(path.join(server.cfg, "projects.yaml")).projects).toContainEqual({ name, root });

  await page.goto("/");
  await expect(page.getByTestId(`project-card-${name}`)).toBeVisible();
  await expect(page.getByTestId(`project-card-${project.name}`)).toBeVisible();

  // path collision → API error in the dialog, nothing was created
  await page.getByRole("button", { name: "Add project" }).click();
  await nameInput.fill(`${name}-2`);
  await pathInput.fill(root);
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(dialog.getByRole("alert")).toContainText("already exists");
  expect(readYaml<Registry>(path.join(server.cfg, "projects.yaml")).projects.some((p) => p.name === `${name}-2`)).toBe(false);
});

test("C13 adding an existing project", async ({ page, project, server }) => {
  // a project created outside the registry (another AGENCAST_CONFIG_DIR)
  const foreign = path.join(server.tmp, `${project.name}-foreign`);
  const r = spawnSync(AGENCAST, ["new", "project", foreign], { env: { ...server.env, AGENCAST_CONFIG_DIR: path.join(server.tmp, "other-cfg") }, encoding: "utf8" });
  expect(r.status, r.stderr).toBe(0);
  const files = () => fs.readdirSync(foreign, { recursive: true }).map(String).sort();
  const before = files();

  await page.goto("/");
  await page.getByRole("button", { name: "Add project" }).click();
  await page.getByRole("radio", { name: "Add existing" }).click();
  const dialog = page.getByRole("dialog", { name: "Add existing project" });
  await dialog.getByRole("textbox", { name: "Path" }).fill(foreign);
  await expect(dialog.getByRole("textbox", { name: "Name" })).toHaveValue(`${project.name}-foreign`);
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(dialog).toBeHidden();
  const card = page.getByTestId(`project-card-${project.name}-foreign`);
  await expect(card).toContainText(/1 scenario\s*1 agent/); // count chips (fidelity §4)
  expect(readYaml<Registry>(path.join(server.cfg, "projects.yaml")).projects).toContainEqual({ name: `${project.name}-foreign`, root: foreign });
  expect(files()).toEqual(before);

  // a path without workflows/config.yaml → API error, nothing was written
  const emptyDir = path.join(server.tmp, `${project.name}-empty`);
  fs.mkdirSync(emptyDir);
  const reg = fs.readFileSync(path.join(server.cfg, "projects.yaml"), "utf8");
  await page.getByRole("button", { name: "Add project" }).click();
  await page.getByRole("radio", { name: "Add existing" }).click();
  await dialog.getByRole("textbox", { name: "Path" }).fill(emptyDir);
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("missing workflows/config.yaml");
  expect(fs.readFileSync(path.join(server.cfg, "projects.yaml"), "utf8")).toBe(reg);

  // the same path again → collision
  await dialog.getByRole("textbox", { name: "Path" }).fill(foreign);
  await dialog.getByRole("textbox", { name: "Name" }).fill(`${project.name}-foreign2`);
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("already in the registry");
});

test("C14 removing a project from the registry", async ({ page, project, server }) => {
  const name = `${project.name}-gone`;
  const created = await server.api<{ root: string }>("POST", "/projects/new", { name });
  const root = created.body.root;
  await page.goto("/");
  await page.getByRole("button", { name: `Actions for ${name}` }).click();
  await page.getByRole("menuitem", { name: "Remove from registry" }).click();
  const dialog = page.getByRole("dialog", { name: `Remove “${name}” from the registry?` });
  await expect(dialog).toContainText("stay on disk unchanged");
  await dialog.getByRole("button", { name: "Remove from registry" }).click();
  await expect(page.getByTestId(`project-card-${name}`)).toBeHidden();
  expect(readYaml<Registry>(path.join(server.cfg, "projects.yaml")).projects.some((p) => p.name === name)).toBe(false);
  expect(fs.existsSync(path.join(root, "workflows/config.yaml"))).toBe(true);
  await page.goto(`/#/p/${name}`);
  await expect(page.getByRole("alert")).toContainText("does not exist");

  // an unavailable project has the remove menu too
  const stale = `${project.name}-stale`;
  const s = await server.api<{ root: string }>("POST", "/projects/new", { name: stale });
  fs.rmSync(path.join(s.body.root, "workflows/config.yaml"));
  await page.goto("/");
  await expect(page.getByTestId(`project-card-${stale}`)).toContainText("unavailable");
  await page.getByRole("button", { name: `Actions for ${stale}` }).click();
  await page.getByRole("menuitem", { name: "Remove from registry" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove from registry" }).click();
  await expect(page.getByTestId(`project-card-${stale}`)).toBeHidden();
});

test("N2 wrong token and a token change on the server", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}`);
  await expect(page.getByRole("heading", { name: "Scenarios", level: 1 })).toBeVisible();
  // server “restarted with another token”: every API request returns 401
  // open the menu before the 401, otherwise the token screen triggered by polling may detach it
  await page.getByRole("button", { name: "More actions" }).click();
  await page.route(/\/projects/, (r) => r.fulfill({ status: 401, contentType: "application/json", body: '{"error": "missing or invalid token (Authorization: Bearer … header)"}' }));
  await page.getByRole("menuitem", { name: "Reload" }).click();
  await expect(page.getByRole("alert")).toHaveText("The server token doesn't match — the server returned 401.");
  expect(await page.evaluate(() => localStorage.getItem("agencast.token"))).toBe(TOKEN);
  await page.unroute(/\/projects/);
  await page.getByRole("textbox", { name: "Token" }).fill(TOKEN);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("heading", { name: "Scenarios", level: 1 })).toBeVisible();
});

test("N3 unavailable and unknown project, unknown address", async ({ page, project, server }) => {
  const stale = `${project.name}-stale`;
  const s = await server.api<{ root: string }>("POST", "/projects/new", { name: stale });
  fs.rmSync(path.join(s.body.root, "workflows/config.yaml"));
  const detail = await countRequests(page, (u) => u.endsWith(`/projects/${stale}`) || u.includes(`/projects/${stale}/`), async () => {
    await page.goto("/");
    const card = page.getByTestId(`project-card-${stale}`);
    await expect(card).toContainText("unavailable");
    await expect(card).toContainText(`missing ${s.body.root}/workflows/config.yaml`);
    await expect(card).toHaveCSS("border-top-style", "dashed"); // dimmed (no transparency, for contrast)
    await page.getByRole("button", { name: `Actions for ${stale}` }).click();
    await expect(page.getByRole("menuitem")).toHaveText(["Open", "Copy path", "Remove from registry"]);
  });
  expect(detail).toBe(0);
  await page.goto(`/#/p/${stale}`);
  await expect(page.getByRole("alert")).toContainText("is unavailable");
  await page.goto("/#/p/no-such-project");
  await expect(page.getByRole("alert")).toContainText("does not exist");
  await page.goto("/#/x");
  await expect(page.getByText("There's nothing at this address.")).toBeVisible();
  await expect(page.getByText("404")).toBeVisible();
  await page.getByRole("main").getByRole("link", { name: "Projects" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
});

test("N4 broken config.yaml", async ({ page, project, server }) => {
  const good = project.read("config.yaml");
  const bad = `${good}\nruns_dir: ./elsewhere\n`;
  project.write("config.yaml", bad);
  const line = bad.split("\n").lastIndexOf("runs_dir: ./elsewhere") + 1;
  await page.goto(`/#/p/${project.name}`);
  const alert = page.getByRole("alert").filter({ hasText: "The project's config.yaml failed validation" });
  await expect(alert).toBeVisible();
  await alert.getByRole("link", { name: "Open Config" }).click();
  await expect(page).toHaveURL(/#\/p\/[^/]+\/config$/);
  const form = page.getByRole("radio", { name: "Form" });
  await expect(form).toHaveAttribute("aria-disabled", "true");
  await expect(form).toHaveAttribute("title", new RegExp(`Fix the YAML: line ${line}|failed validation`));
  await expect(page.getByText(new RegExp(`line ${line} ·`))).toBeVisible();
  await expect(page.getByTestId(`yaml-line-${line}`)).toBeVisible();

  await page.getByRole("link", { name: "Runs", exact: true }).click();
  await expect(page.getByText("No runs.")).toBeVisible();

  await page.getByRole("link", { name: "Config", exact: true }).click();
  await page.getByRole("textbox", { name: "config.yaml" }).fill(good);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("save-status")).toHaveText(/Saved ✓ \d/);
  expect(project.read("config.yaml")).toBe(good);
  await page.getByRole("link", { name: "Scenarios", exact: true }).click();
  await expect(alert).toBeHidden();
  await expect(page.getByTestId("scenario-card-demo")).toBeVisible();

  // 0.10.0 also adds the line to config.yaml schema errors.
  const schemaBad = good.replace(/^(\s*run_budget_usd:)\s*.*$/m, '$1 "x"');
  const schemaLine = schemaBad.split("\n").findIndex((l) => /^\s*run_budget_usd:/.test(l)) + 1;
  project.write("config.yaml", schemaBad);
  const api = await server.api<{ errors: { field?: string; line?: number }[] }>("GET", `/projects/${project.name}`);
  expect(api.status).toBe(422);
  expect(api.body.errors).toContainEqual(expect.objectContaining({ field: "limits.run_budget_usd", line: schemaLine }));
  await page.goto(`/#/p/${project.name}`);
  await page.reload();
  const schemaAlert = page.getByRole("alert").filter({ hasText: "The project's config.yaml failed validation" });
  await expect(schemaAlert).toBeVisible();
  await schemaAlert.getByRole("link", { name: "Open Config" }).click();
  await expect(page.getByText(new RegExp(`line ${schemaLine} ·`))).toBeVisible();
  await expect(page.getByTestId(`yaml-line-${schemaLine}`)).toBeVisible();
  project.write("config.yaml", good);
});
