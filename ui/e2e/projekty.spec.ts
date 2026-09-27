// Cesty C1, C2, C13, C14 a stavy N2, N3, N4 (docs/ui/uzivatelske-cesty.md).
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { AGENCAST, countRequests, expect, readYaml, test, TOKEN } from "./fixtures";

type Registry = { projects: { name: string; root: string }[] };

test.describe("bez tokenu", () => {
  test.use({ token: null });

  test("C1 první spuštění: token", async ({ page, project, server }) => {
    const projectCalls = await countRequests(page, (u) => u.includes("/projects"), async () => {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Token serveru" })).toBeVisible();
    });
    expect(projectCalls).toBe(0);
    const input = page.getByRole("textbox", { name: "Token" });
    await expect(input).toHaveAttribute("type", "password");
    await expect(page.getByText(/V režimu registru proměnná AGENCAST_TOKEN/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Uložit" })).toBeDisabled();

    await input.fill("spatny");
    await input.press("Enter");
    await expect(page.getByRole("alert")).toHaveText("Token serveru nesedí — server vrátil 401.");
    expect(page.url()).not.toContain("spatny");

    const auth: string[] = [];
    page.on("request", (r) => r.url().includes("/projects") && auth.push(r.headers().authorization ?? ""));
    const cardCalls = await countRequests(page, (u, m) => m === "GET" &&
      (u.endsWith(`/projects/${project.name}`) || u.endsWith(`/projects/${project.name}/spend`)), async () => {
      await page.getByRole("textbox", { name: "Token" }).fill(TOKEN);
      await page.getByRole("textbox", { name: "Token" }).press("Enter");
      const card = page.getByTestId(`project-card-${project.name}`);
      await expect(card).toContainText(/1 scénář\s*1 agent/); // čipy počtů (fidelity §4)
      await expect(card).toContainText("dnes 0,00 USD");
    });
    expect(cardCalls).toBe(0);
    await expect(page.getByRole("heading", { name: "Projekty" })).toBeVisible();
    await expect(page.getByText(`${server.cfg}/projects.yaml`, { exact: true })).toBeVisible();
    const card = page.getByTestId(`project-card-${project.name}`);
    await expect(card).not.toContainText("dostupný"); // G6: dostupný projekt bez štítku
    await expect(card).toContainText(/1 scénář\s*1 agent/); // čipy počtů (fidelity §4)
    await expect(card).toContainText("dnes 0,00 USD");
    await expect(card).toContainText("bez běhů");
    expect(await page.evaluate(() => localStorage.getItem("agencast.token"))).toBe(TOKEN);
    expect(auth.length).toBeGreaterThan(0);
    expect(auth.every((a) => a === `Bearer ${TOKEN}`)).toBe(true);
  });
});

test("C2 založení projektu z GUI", async ({ page, project, server }) => {
  const name = `${project.name}-web`;
  await page.goto("/");
  await page.getByRole("button", { name: "Přidat projekt" }).click();
  const dialog = page.getByRole("dialog", { name: "Nový projekt" });
  await expect(dialog.getByRole("radio", { name: "Založit nový" })).toHaveAttribute("aria-checked", "true");
  const jmeno = dialog.getByRole("textbox", { name: "Jméno" });
  await expect(jmeno).toBeFocused();
  await jmeno.fill("Muj");
  await expect(dialog.getByText("Malá písmena, číslice a pomlčka; začíná písmenem.")).toBeVisible();
  await jmeno.fill(project.name);
  await expect(dialog.getByText(`„${project.name}“ už existuje.`)).toBeVisible();
  await jmeno.fill(name);
  const cesta = dialog.getByRole("textbox", { name: "Cesta" });
  await expect(cesta).toHaveValue(`${server.projectsRoot}/${name}`);
  await dialog.getByRole("button", { name: "Vytvořit" }).click();

  await expect(page).toHaveURL(new RegExp(`#/p/${name}$`));
  // G5: jméno projektu v sidebaru, hlavička = sekce, cesta projektu jen na kartě a v Config
  await expect(page.getByRole("heading", { name: "Scénáře", level: 1 })).toBeVisible();
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Části projektu" })).toBeVisible();
  const sc = page.getByTestId("scenario-card-ukazka");
  await expect(sc).toContainText("Napíše krátký text na zadané téma");
  await expect(sc).toContainText("2 kroky · pisatel");
  await expect(sc).toContainText("ukazka");
  await expect(sc).not.toContainText("ukazka.yaml");

  const root = path.join(server.projectsRoot, name);
  for (const f of ["workflows/config.yaml", "workflows/agents/pisatel.md", "workflows/scenarios/ukazka.yaml", ".env.example", ".gitignore"])
    expect(fs.existsSync(path.join(root, f)), f).toBe(true);
  expect(readYaml<Registry>(path.join(server.cfg, "projects.yaml")).projects).toContainEqual({ name, root });

  await page.goto("/");
  await expect(page.getByTestId(`project-card-${name}`)).toBeVisible();
  await expect(page.getByTestId(`project-card-${project.name}`)).toBeVisible();

  // kolize cesty → chyba API v dialogu, nic nevzniklo
  await page.getByRole("button", { name: "Přidat projekt" }).click();
  await jmeno.fill(`${name}-2`);
  await cesta.fill(root);
  await dialog.getByRole("button", { name: "Vytvořit" }).click();
  await expect(dialog.getByRole("alert")).toContainText("už existuje");
  expect(readYaml<Registry>(path.join(server.cfg, "projects.yaml")).projects.some((p) => p.name === `${name}-2`)).toBe(false);
});

test("C13 přidání existujícího projektu", async ({ page, project, server }) => {
  // projekt vytvořený mimo registr (jiný AGENCAST_CONFIG_DIR)
  const cizi = path.join(server.tmp, `${project.name}-cizi`);
  const r = spawnSync(AGENCAST, ["new", "project", cizi], { env: { ...server.env, AGENCAST_CONFIG_DIR: path.join(server.tmp, "jiny-cfg") }, encoding: "utf8" });
  expect(r.status, r.stderr).toBe(0);
  const files = () => fs.readdirSync(cizi, { recursive: true }).map(String).sort();
  const before = files();

  await page.goto("/");
  await page.getByRole("button", { name: "Přidat projekt" }).click();
  await page.getByRole("radio", { name: "Přidat existující" }).click();
  const dialog = page.getByRole("dialog", { name: "Přidat existující projekt" });
  await dialog.getByRole("textbox", { name: "Cesta" }).fill(cizi);
  await expect(dialog.getByRole("textbox", { name: "Jméno" })).toHaveValue(`${project.name}-cizi`);
  await dialog.getByRole("button", { name: "Přidat", exact: true }).click();
  await expect(dialog).toBeHidden();
  const card = page.getByTestId(`project-card-${project.name}-cizi`);
  await expect(card).toContainText(/1 scénář\s*1 agent/); // čipy počtů (fidelity §4)
  expect(readYaml<Registry>(path.join(server.cfg, "projects.yaml")).projects).toContainEqual({ name: `${project.name}-cizi`, root: cizi });
  expect(files()).toEqual(before);

  // cesta bez workflows/config.yaml → chyba z API, nic se nezapsalo
  const prazdna = path.join(server.tmp, `${project.name}-prazdna`);
  fs.mkdirSync(prazdna);
  const reg = fs.readFileSync(path.join(server.cfg, "projects.yaml"), "utf8");
  await page.getByRole("button", { name: "Přidat projekt" }).click();
  await page.getByRole("radio", { name: "Přidat existující" }).click();
  await dialog.getByRole("textbox", { name: "Cesta" }).fill(prazdna);
  await dialog.getByRole("button", { name: "Přidat", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("chybí workflows/config.yaml");
  expect(fs.readFileSync(path.join(server.cfg, "projects.yaml"), "utf8")).toBe(reg);

  // stejná cesta podruhé → kolize
  await dialog.getByRole("textbox", { name: "Cesta" }).fill(cizi);
  await dialog.getByRole("textbox", { name: "Jméno" }).fill(`${project.name}-cizi2`);
  await dialog.getByRole("button", { name: "Přidat", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("už je v registru");
});

test("C14 odebrání projektu z registru", async ({ page, project, server }) => {
  const name = `${project.name}-pryc`;
  const created = await server.api<{ root: string }>("POST", "/projects/new", { name });
  const root = created.body.root;
  await page.goto("/");
  await page.getByRole("button", { name: `Akce pro ${name}` }).click();
  await page.getByRole("menuitem", { name: "Odebrat z registru" }).click();
  const dialog = page.getByRole("dialog", { name: `Odebrat „${name}“ z registru?` });
  await expect(dialog).toContainText("zůstanou na disku");
  await dialog.getByRole("button", { name: "Odebrat z registru" }).click();
  await expect(page.getByTestId(`project-card-${name}`)).toBeHidden();
  expect(readYaml<Registry>(path.join(server.cfg, "projects.yaml")).projects.some((p) => p.name === name)).toBe(false);
  expect(fs.existsSync(path.join(root, "workflows/config.yaml"))).toBe(true);
  await page.goto(`/#/p/${name}`);
  await expect(page.getByRole("alert")).toContainText("neexistuje");

  // nedostupný projekt má menu s odebráním taky
  const stary = `${project.name}-stary`;
  const s = await server.api<{ root: string }>("POST", "/projects/new", { name: stary });
  fs.rmSync(path.join(s.body.root, "workflows/config.yaml"));
  await page.goto("/");
  await expect(page.getByTestId(`project-card-${stary}`)).toContainText("nedostupný");
  await page.getByRole("button", { name: `Akce pro ${stary}` }).click();
  await page.getByRole("menuitem", { name: "Odebrat z registru" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Odebrat z registru" }).click();
  await expect(page.getByTestId(`project-card-${stary}`)).toBeHidden();
});

test("N2 špatný token a změna tokenu na serveru", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}`);
  await expect(page.getByRole("heading", { name: "Scénáře", level: 1 })).toBeVisible();
  // server „restartovaný s jiným tokenem“: každý požadavek API vrací 401
  // menu otevřít ještě před 401, jinak ho může odpojit obrazovka tokenu vyvolaná pollingem
  await page.getByRole("button", { name: "Další akce" }).click();
  await page.route(/\/projects/, (r) => r.fulfill({ status: 401, contentType: "application/json", body: '{"error": "chybí nebo nesedí token"}' }));
  await page.getByRole("menuitem", { name: "Načíst znovu" }).click();
  await expect(page.getByRole("alert")).toHaveText("Token serveru nesedí — server vrátil 401.");
  expect(await page.evaluate(() => localStorage.getItem("agencast.token"))).toBe(TOKEN);
  await page.unroute(/\/projects/);
  await page.getByRole("textbox", { name: "Token" }).fill(TOKEN);
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(page.getByRole("heading", { name: "Scénáře", level: 1 })).toBeVisible();
});

test("N3 nedostupný a neznámý projekt, neznámá adresa", async ({ page, project, server }) => {
  const stary = `${project.name}-stary`;
  const s = await server.api<{ root: string }>("POST", "/projects/new", { name: stary });
  fs.rmSync(path.join(s.body.root, "workflows/config.yaml"));
  const detail = await countRequests(page, (u) => u.endsWith(`/projects/${stary}`) || u.includes(`/projects/${stary}/`), async () => {
    await page.goto("/");
    const card = page.getByTestId(`project-card-${stary}`);
    await expect(card).toContainText("nedostupný");
    await expect(card).toContainText(`chybí ${s.body.root}/workflows/config.yaml`);
    await expect(card).toHaveCSS("border-top-style", "dashed"); // ztlumená (bez průhlednosti kvůli kontrastu)
    await page.getByRole("button", { name: `Akce pro ${stary}` }).click();
    await expect(page.getByRole("menuitem")).toHaveText(["Otevřít", "Kopírovat cestu", "Odebrat z registru"]);
  });
  expect(detail).toBe(0);
  await page.goto(`/#/p/${stary}`);
  await expect(page.getByRole("alert")).toContainText("je nedostupný");
  await page.goto("/#/p/neni-takovy");
  await expect(page.getByRole("alert")).toContainText("neexistuje");
  await page.goto("/#/x");
  await expect(page.getByText("Tahle adresa v GUI neexistuje.")).toBeVisible();
  await expect(page.getByText("404")).toBeVisible();
  await page.getByRole("main").getByRole("link", { name: "Projekty" }).click();
  await expect(page.getByRole("heading", { name: "Projekty" })).toBeVisible();
});

test("N4 rozbitý config.yaml", async ({ page, project, server }) => {
  const good = project.read("config.yaml");
  const bad = `${good}\nruns_dir: ./jinde\n`;
  project.write("config.yaml", bad);
  const line = bad.split("\n").lastIndexOf("runs_dir: ./jinde") + 1;
  await page.goto(`/#/p/${project.name}`);
  const alert = page.getByRole("alert").filter({ hasText: "config.yaml projektu neprošel kontrolou" });
  await expect(alert).toBeVisible();
  await alert.getByRole("link", { name: "Otevřít Config" }).click();
  await expect(page).toHaveURL(/#\/p\/[^/]+\/config$/);
  const form = page.getByRole("radio", { name: "Form" });
  await expect(form).toHaveAttribute("aria-disabled", "true");
  await expect(form).toHaveAttribute("title", new RegExp(`Oprav YAML: řádek ${line}|neprošel kontrolou`));
  await expect(page.getByText(new RegExp(`řádek ${line} ·`))).toBeVisible();
  await expect(page.getByTestId(`yaml-line-${line}`)).toBeVisible();

  await page.getByRole("link", { name: "Běhy", exact: true }).click();
  await expect(page.getByText("Žádné běhy.")).toBeVisible();

  await page.getByRole("link", { name: "Config", exact: true }).click();
  await page.getByRole("textbox", { name: "config.yaml" }).fill(good);
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(page.getByTestId("save-status")).toHaveText(/Uloženo ✓ \d/);
  expect(project.read("config.yaml")).toBe(good);
  await page.getByRole("link", { name: "Scénáře", exact: true }).click();
  await expect(alert).toBeHidden();
  await expect(page.getByTestId("scenario-card-ukazka")).toBeVisible();

  // 0.10.0 přidává řádek i ke chybě schématu config.yaml.
  const schemaBad = good.replace(/^(\s*run_budget_usd:)\s*.*$/m, '$1 "x"');
  const schemaLine = schemaBad.split("\n").findIndex((l) => /^\s*run_budget_usd:/.test(l)) + 1;
  project.write("config.yaml", schemaBad);
  const api = await server.api<{ errors: { field?: string; line?: number }[] }>("GET", `/projects/${project.name}`);
  expect(api.status).toBe(422);
  expect(api.body.errors).toContainEqual(expect.objectContaining({ field: "limits.run_budget_usd", line: schemaLine }));
  await page.goto(`/#/p/${project.name}`);
  await page.reload();
  const schemaAlert = page.getByRole("alert").filter({ hasText: "config.yaml projektu neprošel kontrolou" });
  await expect(schemaAlert).toBeVisible();
  await schemaAlert.getByRole("link", { name: "Otevřít Config" }).click();
  await expect(page.getByText(new RegExp(`řádek ${schemaLine} ·`))).toBeVisible();
  await expect(page.getByTestId(`yaml-line-${schemaLine}`)).toBeVisible();
  project.write("config.yaml", good);
});
