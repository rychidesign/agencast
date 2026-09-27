// Cesty C6–C8 a stav N5 (docs/ui/uzivatelske-cesty.md): spuštění, čtení výsledku, chybný a přerušený běh.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import { AGENCAST, CHYBA, countRequests, DLOUHY, expect, startRun, test, waitRun } from "./fixtures";

const card = (page: Page, id: string) => page.locator(`[data-step-card="${id}"]`);
const runIdFromUrl = (page: Page) => decodeURIComponent(page.url().split("/behy/")[1].split("?")[0]);
const POVINNE = DLOUHY.replace("name: dlouhy", "name: povinne").replace("tema: { type: string, default: káva }", "tema: { type: string, required: true }");

test("C6 spuštění běhu s formulářem vstupů (dry-run, ostrý, živý)", async ({ page, project, server }) => {
  project.write("scenarios/dlouhy.yaml", DLOUHY);
  project.write("scenarios/povinne.yaml", POVINNE);
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("SPUSTIT BĚH");
  await expect(panel.getByRole("textbox", { name: "tema" })).toHaveValue("káva");
  await expect(panel.getByText("string · O čem psát")).toBeVisible();
  await expect(panel.getByRole("radio", { name: /Dry-run/ })).toBeChecked();
  await expect(panel.getByText("Jen plán (plan.md), nic se nevolá, zdarma.")).toBeVisible();

  // povinný vstup bez default: bez hodnoty se nic neodešle
  await page.goto(`/#/p/${project.name}/scenare/povinne`);
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  const posts = await countRequests(page, (u, m) => m === "POST" && u.endsWith("/runs"), async () => {
    await panel.getByRole("button", { name: "Spustit dry-run" }).click();
    await expect(panel.getByText("Povinný vstup.")).toBeVisible();
  });
  expect(posts).toBe(0);

  // dry-run
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  await panel.getByRole("textbox", { name: "tema" }).fill("nová káva");
  const dry = page.waitForResponse((r) => r.url().endsWith(`/projects/${project.name}/runs`) && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Spustit dry-run" }).click();
  expect((await dry).status()).toBe(200);
  expect((await dry).request().postDataJSON()).toEqual({ scenario: "ukazka", inputs: { tema: "nová káva" }, dry_run: true });
  await expect(page).toHaveURL(/#\/p\/[^/]+\/behy\/[^?]+$/);
  const dryId = runIdFromUrl(page);
  await expect(page.getByTestId("run-state")).toHaveText("jen plán (dry-run)");
  await expect(page.getByText("Tohle je jen plán (dry-run) — běh neproběhl.")).toBeVisible();
  await expect(page.locator("main h1, main h2").filter({ hasText: /plán|Plán|ukazka/ }).first()).toBeVisible();
  const dryDir = path.join(project.runsDir, dryId);
  expect(fs.existsSync(path.join(dryDir, "plan.md"))).toBe(true);
  expect(JSON.parse(fs.readFileSync(path.join(dryDir, "inputs.json"), "utf8"))).toEqual({ tema: "nová káva" });
  expect(fs.existsSync(path.join(dryDir, "events.jsonl"))).toBe(false);

  // ostrý s neuloženou změnou: limity a varování
  await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Neuloženo {{ inputs.tema }}");
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  await panel.getByRole("radio", { name: /Ostrý běh/ }).check();
  const limits = panel.getByRole("definition");
  await expect(panel.getByLabel("Limity běhu")).toBeVisible();
  await expect(limits).toHaveText(["1,00 USD", "0,30 USD", "1h", "0 USD"]);
  await expect(panel.getByText("Máš neuložené změny — běh použije verzi na disku.")).toBeVisible();
  const live = page.waitForResponse((r) => r.url().endsWith(`/projects/${project.name}/runs`) && r.request().method() === "POST");
  page.once("dialog", (d) => void d.accept());
  await panel.getByRole("button", { name: "Spustit ostrý běh" }).click();
  expect((await live).status()).toBe(202);
  await expect(page).toHaveURL(/#\/p\/[^/]+\/behy\/[^?]+$/);

  // živý běh dlouhy (krok pomalu spí 4 s)
  await page.goto(`/#/p/${project.name}/scenare/dlouhy`);
  await page.getByRole("button", { name: "Spustit", exact: true }).click();
  await panel.getByRole("radio", { name: /Ostrý běh/ }).check();
  await panel.getByRole("button", { name: "Spustit ostrý běh" }).click();
  await expect(page).toHaveURL(/behy\//);
  const liveId = runIdFromUrl(page);
  await expect(page.getByTestId("run-state")).toHaveText("běží");
  await expect(page.getByText("falešný běh")).toBeVisible();
  await expect(card(page, "pomalu")).toHaveAttribute("aria-label", /— běží$/);
  await expect(page.locator("header p[aria-live]")).toHaveText("krok pomalu běží");
  await expect(page.getByRole("checkbox", { name: "sledovat běh" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Běh skončil" })).toHaveText("Běh skončil: úspěch", { timeout: 15_000 });
  await expect(card(page, "pomalu")).toHaveAttribute("aria-label", /— úspěch$/);
  await expect(page.getByRole("checkbox", { name: "sledovat běh" })).toBeHidden();
  const polls = await countRequests(page, (u) => u.includes(`/runs/${liveId}`), () => page.waitForTimeout(6_000));
  expect(polls).toBe(0);
  const dir = path.join(project.runsDir, liveId);
  for (const f of ["run.lock", "events.jsonl", "scenario/dlouhy.yaml", "steps/01-pomalu", "summary.md", "report.html"])
    expect(fs.existsSync(path.join(dir, f)), f).toBe(true);

  // seznam běhů: dva starty naráz → druhý čeká ve frontě
  const a = await startRun(server, project.name, "dlouhy");
  const b = await startRun(server, project.name, "dlouhy");
  await page.goto(`/#/p/${project.name}/behy`);
  await expect(page.getByTestId(`run-row-${a}`)).toContainText(/krok 1\/2 · pomalu/);
  await expect(page.getByTestId(`run-row-${a}`)).toContainText("falešný běh");
  await expect(page.getByTestId(`run-row-${a}`).getByText("běží", { exact: true })).toBeAttached();
  await expect(page.getByTestId(`run-row-${b}`)).toContainText("ve frontě (2.)");
  await expect(page.getByText("1 běží · 1 ve frontě")).toBeVisible();
  await waitRun(server, project.name, b, ["succeeded"]);
});

test("C7 čtení výsledku a ceny", async ({ page, project, server }) => {
  const id = await startRun(server, project.name, "ukazka", { inputs: { tema: "nová káva" } });
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/behy/${id}`);
  const h1 = page.getByRole("heading", { level: 1 });
  await expect(h1.getByRole("link", { name: "ukazka" })).toBeVisible();
  await expect(h1).toContainText(id);
  await expect(page.getByTestId("run-state")).toHaveText("úspěch");
  await expect(page.getByTestId("run-duration")).toHaveText(/^\d+,\d\ss$/); // mezi číslem a jednotkou je NBSP
  await expect(page.getByTestId("run-cost")).toHaveText(/^(0|\d+,\d{4,}) USD$/);
  await expect(page.getByText(/Vstupy\s*tema = „nová káva“/)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Části běhu" }).getByRole("link")).toHaveText(["Kroky", "Souhrn", "Report", "Soubory"]);

  await expect(card(page, "napis")).toHaveAttribute("aria-label", "Krok 1: ask napis — úspěch");
  await expect(card(page, "napis")).toContainText("chytry → anthropic/claude-haiku-4.5");
  await expect(page.getByTestId("step-duration-napis")).toHaveText(/^\d+,\d\ss$/);
  await expect(card(page, "vystup")).toHaveAttribute("aria-label", "Krok 2: output vystup — úspěch");
  const detail = page.waitForResponse((r) => r.url().endsWith(`/runs/${id}/steps/napis`));
  await card(page, "napis").click();
  expect((await detail).status()).toBe(200);
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("KROK 1");
  await expect(panel).toContainText("napis");
  const tabs = panel.getByRole("tablist", { name: "Části kroku" }).getByRole("tab");
  await expect(tabs).toContainText(["Prompt", "Odpověď", "Výstup", "Volání", "Soubory"]);
  await tabs.filter({ hasText: "Volání" }).click();
  await expect(panel.getByText("pokus 1")).toBeVisible();
  await expect(panel.getByText(/\d+ \+ \d+ tokenů/)).toBeVisible();
  await tabs.filter({ hasText: "Výstup" }).click();
  await expect(panel.getByRole("tabpanel")).toContainText("Dvě věty.");

  const nav = page.getByRole("navigation", { name: "Části běhu" });
  await nav.getByRole("link", { name: "Souhrn" }).click();
  await expect(page.getByText("Celkem").first()).toBeVisible();
  await nav.getByRole("link", { name: "Report" }).click();
  await expect(page.locator("iframe[sandbox][title='Report běhu']")).toBeVisible();
  await nav.getByRole("link", { name: "Soubory" }).click();
  await page.getByRole("navigation", { name: "Soubory" }).getByText("summary.md", { exact: true }).click();
  await expect(page).toHaveURL(/soubor=summary\.md/);

  await page.goto(`/#/p/${project.name}`);
  const sc = page.getByTestId("scenario-card-ukazka");
  await expect(sc).toContainText("úspěch");
  await expect(sc).toContainText("právě teď");
  await expect(page.getByTestId("spend-today")).toHaveText(/^0,00( \/ [\d,]+)? USD$/); // útrata v sidebaru (G5)

  await page.getByRole("link", { name: "Běhy", exact: true }).click();
  const req = page.waitForRequest((r) => r.url().includes("/runs?scenario=ukazka&limit=50"));
  await page.getByRole("combobox", { name: "scénář:" }).selectOption("ukazka");
  await req;
  await page.getByRole("combobox", { name: "stav:" }).selectOption({ label: "úspěch" });
  await expect(page.getByTestId(`run-row-${id}`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Načíst další" })).toBeHidden();
});

test("C8 chybný běh", async ({ page, project, server }) => {
  project.write("scenarios/chyba.yaml", CHYBA);
  const id = await startRun(server, project.name, "chyba");
  await waitRun(server, project.name, id, ["failed"]);
  await page.goto(`/#/p/${project.name}/behy/${id}`);
  await expect(page.getByTestId("run-state")).toHaveText("chyba: fail v stop");
  await expect(card(page, "napis")).toHaveAttribute("aria-label", /— úspěch$/);
  await expect(card(page, "vynech")).toHaveAttribute("aria-label", /— přeskočeno$/);
  await expect(card(page, "vynech")).toContainText(/přeskočeno: .*false/);
  await expect(card(page, "stop")).toHaveAttribute("aria-label", /— chyba$/);
  await expect(card(page, "stop")).toContainText("Zastaveno naschvál");
  await expect(card(page, "vystup")).toHaveAttribute("aria-label", /— nedošlo$/);
  await expect(card(page, "vystup")).toHaveCSS("border-top-style", "dashed"); // ztlumená (bez průhlednosti kvůli kontrastu)
  await card(page, "vynech").click();
  await expect(page.getByRole("complementary")).toContainText("použit default");
  await card(page, "stop").click();
  await expect(page.getByRole("complementary").getByRole("alert")).toContainText("Zastaveno naschvál");
  await page.getByRole("navigation", { name: "Části běhu" }).getByRole("link", { name: "Souhrn" }).click();
  await expect(page.getByRole("heading").filter({ hasText: "chyba" }).first()).toBeVisible();
  await expect(page.getByText("Zastaveno naschvál").first()).toBeVisible();

  await page.goto(`/#/p/${project.name}/behy`);
  await expect(page.getByTestId(`run-row-${id}`)).toContainText("fail v stop · falešný běh");
  await page.goto(`/#/p/${project.name}`);
  await expect(page.getByTestId("scenario-card-chyba")).toContainText("chyba");
  const dir = path.join(project.runsDir, id);
  const events = fs.readFileSync(path.join(dir, "events.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
  expect(events.at(-1)).toMatchObject({ type: "run_finished", status: "failed" });
  expect(fs.readFileSync(path.join(dir, "summary.md"), "utf8")).toContain("Zastaveno naschvál");
});

test("N5 přerušený běh (proces zabitý uprostřed kroku)", async ({ page, project, server }) => {
  project.write("scenarios/dlouhy.yaml", DLOUHY);
  const proc = spawn(AGENCAST, ["--project", project.root, "run", "dlouhy", "--fake", server.fake], { env: server.env, stdio: "ignore" });
  const runDir = async () => {
    for (let i = 0; i < 100; i++) {
      const dirs = fs.existsSync(project.runsDir) ? fs.readdirSync(project.runsDir).filter((d) => d.includes("dlouhy")) : [];
      const ev = dirs[0] && path.join(project.runsDir, dirs[0], "events.jsonl");
      if (ev && fs.existsSync(ev) && fs.readFileSync(ev, "utf8").includes('"step_started"')) return dirs[0];
      await new Promise((r) => setTimeout(r, 100));
    }
    throw new Error("běh z CLI nezačal krok");
  };
  const id = await runDir();
  proc.kill("SIGKILL");
  await new Promise((r) => proc.once("exit", r));

  await page.goto(`/#/p/${project.name}/behy/${id}`);
  await expect(page.getByTestId("run-state")).toHaveText("přerušen");
  await expect(page.getByText("Běh skončil bez záznamu o konci (proces spadl nebo byl zabit); GUI se na něj už nedotazuje.")).toBeVisible();
  await expect(card(page, "pomalu")).toHaveAttribute("aria-label", /— přerušen$/);
  await expect(card(page, "pomalu")).not.toHaveClass(/animate-pulse/);
  const polls = await countRequests(page, (u) => u.includes(`/runs/${id}`), () => page.waitForTimeout(6_000));
  expect(polls).toBe(0);
  await page.goto(`/#/p/${project.name}/behy`);
  // stav je jen ve sloupci stavu, poznámka ho neopakuje (vlna C)
  await expect(page.getByTestId(`run-row-${id}`).locator("td").first()).toHaveText("přerušen");
  await expect(page.getByTestId(`run-row-${id}`).locator("td").last()).toHaveText("falešný běh");
});

test("N5b přerušený běh pod serve (restart serve)", async ({ page, project, server }) => {
  project.write("scenarios/dlouhy.yaml", DLOUHY);
  const id = await startRun(server, project.name, "dlouhy");
  await waitRun(server, project.name, id, ["running"]);
  const before = await server.api<{ started_at: string }>("GET", `/projects/${project.name}/runs/${id}`);
  await server.restart();
  const after = await server.api<{ state: string; started_at: string; steps: { step: string; status: string }[] }>("GET", `/projects/${project.name}/runs/${id}`);
  expect(after.body.state).toBe("interrupted");
  expect(after.body.started_at).toBe(before.body.started_at);
  expect(after.body.steps.find((s) => s.step === "pomalu")?.status).toBe("interrupted");
  await page.goto(`/#/p/${project.name}/behy/${id}`);
  await expect(page.getByTestId("run-state")).not.toContainText("v None");
  await expect(page.getByTestId("run-state")).toHaveText("přerušen");
  await expect(card(page, "pomalu")).toHaveAttribute("aria-label", /— přerušen$/);
  await expect(card(page, "pomalu")).not.toHaveClass(/animate-pulse/);
});

test("N25 seznam běhů načítá starší stránku kurzorem bez duplicit", async ({ page, project }) => {
  const ids = Array.from({ length: 52 }, (_, i) => `20260926-1200${String(59 - i).padStart(2, "0")}-ukazka-${i.toString(16).padStart(4, "0")}`);
  const item = (run_id: string) => ({
    run_id, scenario: "ukazka", state: "succeeded", status: "succeeded", started_at: "2026-09-26T12:00:00.000Z",
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
  await page.goto(`/#/p/${project.name}/behy`);
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(50);
  await page.getByRole("button", { name: "Načíst další" }).click();
  await expect(rows).toHaveCount(52);
  expect(requested).toEqual(["", ids[49]]);
  const displayed = await rows.evaluateAll((els) => els.map((el) => el.getAttribute("data-testid")!.slice("run-row-".length)));
  expect(new Set(displayed).size).toBe(52);
  await expect(page.getByRole("button", { name: "Načíst další" })).toBeHidden();
});
