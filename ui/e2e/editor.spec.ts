// Cesty C3–C5, C9–C12, C15 a stavy N1, N6 (docs/ui/uzivatelske-cesty.md): editor agenta a scénáře.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import { expect, startRun, tabTo, test, waitRun } from "./fixtures";

type Scn = { description?: string; steps: ({ id: string } & Record<string, unknown>)[] };

const card = (page: Page, id: string) => page.locator(`[data-step-card="${id}"]`);
/** Obal karty (karta + ovládání + chyby pod ní). */
const cardBox = (page: Page, id: string) => card(page, id).locator("xpath=..");
const saveStatus = (page: Page) => page.getByTestId("save-status");
const live = (page: Page) => page.getByTestId("announce");
const sha = (text: string) => createHash("sha256").update(text).digest("hex");

const CLANEK = `version: 1
name: clanek
description: Napíše a ohodnotí článek
inputs:
  tema: { type: string, default: káva }
outputs:
  text: { type: string }
steps:
  - id: napis
    ask:
      agent: pisatel
      prompt: "Napiš článek: {{ inputs.tema }}"
  - id: jev_1
    jev:
      state: "{{ steps.napis.text }}"
      questions:
        ok: { type: noul, instructions: "Je text česky?" }
  - id: vystup
    output:
      text: "{{ steps.napis.text }}"
`;

test("C3 nový agent", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/agenti`);
  const nav = page.getByRole("navigation", { name: "Agenti" });
  // G8: „+ Nový agent“ je v hlavičce sekce, ne v seznamu
  await expect(page.locator("main header").getByRole("button", { name: "Nový agent" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "pisatel" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "pisatel", level: 2 })).toBeVisible();

  await page.getByRole("button", { name: "Nový agent" }).click();
  const dialog = page.getByRole("dialog", { name: "Nový agent" });
  const jmeno = dialog.getByRole("textbox", { name: "Jméno" });
  await expect(jmeno).toBeFocused();
  await jmeno.fill("Pisatel");
  await expect(dialog.getByText("Malá písmena, číslice a pomlčka; začíná písmenem.")).toBeVisible();
  await jmeno.fill("pisatel");
  await expect(dialog.getByText("„pisatel“ už existuje.")).toBeVisible();
  await jmeno.fill("korektor");
  await dialog.getByRole("textbox", { name: "popis" }).fill("Kontroluje pravopis");
  await expect(dialog.getByRole("combobox", { name: "model" })).toHaveValue("chytry");
  await dialog.getByRole("button", { name: "Vytvořit" }).click();

  await expect(page).toHaveURL(/\/agenti\/korektor$/);
  await expect(page.getByRole("heading", { name: "korektor", level: 2 })).toBeVisible();
  const mode = page.getByRole("radiogroup", { name: "Zobrazení" });
  await expect(mode.getByRole("radio")).toHaveText(["Form", "Markdown"]);
  await expect(saveStatus(page)).toHaveText("Uloženo ✓");
  await expect(page.getByRole("textbox", { name: "popis" })).toHaveValue("Kontroluje pravopis");
  await expect(page.getByRole("combobox", { name: "model" })).toHaveValue("chytry");
  await expect(page.getByText("Používá: –")).toBeVisible();
  const fm = () => project.read("agents/korektor.md");
  expect(fm()).toMatch(/model: chytry/);
  expect(fm()).toMatch(/budget_usd: 0\.02/);
  expect(fm()).toMatch(/description: .?Kontroluje pravopis/);

  const before = fm().split("\n");
  await page.getByRole("textbox", { name: "Instrukce (system prompt)" }).fill("Opravuj jen chyby.");
  await expect(saveStatus(page)).toHaveText("Neuloženo");
  await page.keyboard.press("Control+s");
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓ \d{1,2}:\d{2}$/);
  const after = fm();
  expect(after).toContain("Opravuj jen chyby.");
  // frontmatter beze změny, tělo nahrazeno
  expect(after.split("---")[1]).toBe(before.join("\n").split("---")[1]);

  await mode.getByRole("radio", { name: "Markdown" }).click();
  await expect(page.getByRole("textbox", { name: "agents/korektor.md" })).toHaveValue(/^---\n/);
  await expect(page.getByText("Upravuješ přímo soubor workflows/agents/korektor.md")).toBeVisible();

  await page.getByRole("button", { name: "Akce pro korektor" }).click();
  await page.getByRole("menuitem", { name: "Smazat" }).click();
  const del = page.getByRole("dialog", { name: "Smazat agenta „korektor“?" });
  await del.getByRole("button", { name: "Smazat", exact: true }).click();
  await expect(page).toHaveURL(/\/agenti$/);
  await expect(nav.getByRole("link")).toHaveText(["pisatel"]);
  expect(fs.existsSync(path.join(project.wf, "agents/korektor.md"))).toBe(false);

  // pisatel používá ukazka → smazání odmítne API a dialog řekne proč
  await page.getByRole("button", { name: "Akce pro pisatel" }).click();
  await page.getByRole("menuitem", { name: "Smazat" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Smazat", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("ukazka");
  expect(fs.existsSync(path.join(project.wf, "agents/pisatel.md"))).toBe(true);
});

test("C4 nový scénář se dvěma kroky a output", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}`);
  await page.getByRole("button", { name: "Nový scénář" }).click();
  const dialog = page.getByRole("dialog", { name: "Nový scénář" });
  await expect(dialog.getByText("Stane se i jménem souboru.")).toBeVisible();
  await dialog.getByRole("textbox", { name: "Jméno" }).fill("clanek");
  await dialog.getByRole("textbox", { name: "popis" }).fill("Napíše a ohodnotí článek");
  await dialog.getByRole("button", { name: "Vytvořit" }).click();

  await expect(page).toHaveURL(/scenare\/clanek\?krok=_hlavicka$/);
  await expect(page.getByRole("heading", { name: "clanek", level: 1 })).toBeVisible();
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("HLAVIČKA");
  await expect(panel.getByRole("textbox", { name: /^popis/ })).toHaveValue("Napíše a ohodnotí článek");
  await expect(panel.getByRole("checkbox", { name: "povinný" })).not.toBeChecked();
  await expect(panel.getByRole("textbox", { name: "Výchozí hodnota tema" })).toHaveValue("káva");
  await expect(card(page, "")).toContainText("1 vstup: tema · 1 výstup: text");
  await expect(card(page, "napis")).toHaveAttribute("aria-label", "Krok 1: ask napis");
  await expect(card(page, "vystup")).toHaveAttribute("aria-label", "Krok 2: output vystup");
  expect(project.yaml<Scn>("scenarios/clanek.yaml").description).toBe("Napíše a ohodnotí článek");
  const template = project.read("scenarios/clanek.yaml");

  await page.getByTestId("add-after-napis").click();
  const picker = page.getByRole("listbox", { name: "Typ nového kroku" });
  await picker.press("j");
  await expect(picker.getByRole("option")).toHaveText([/^jev\s*levné rozhodnutí Jev$/]);
  await picker.press("Enter");
  await expect(card(page, "jev_1")).toHaveAttribute("aria-label", "Krok 2: jev jev_1");
  await expect(card(page, "jev_1")).toContainText("doplň v panelu");
  await expect(panel).toContainText("KROK 2");
  await expect(panel.getByRole("combobox", { name: "Typ kroku" })).toHaveValue("jev");
  await expect(live(page)).toHaveText("Přidán krok jev_1.");
  await expect(page).toHaveURL(/krok=jev_1/);
  await expect(saveStatus(page)).toHaveText("Neuloženo");

  const state = panel.getByRole("combobox", { name: "State" });
  await state.pressSequentially("{{ steps.");
  await expect(page.locator("ul[role=listbox]").getByRole("option")).toHaveText(["steps.napis.text"]);
  await state.press("Enter");
  await state.pressSequentially(" }}");
  await expect(state).toHaveValue("{{ steps.napis.text }}");
  await panel.getByRole("button", { name: "Přidat otázku" }).click();
  await expect(panel.getByRole("combobox", { name: "Typ otázky q_1" })).toBeVisible();
  const key = panel.getByRole("textbox", { name: "Jméno" });
  await key.fill("ok");
  await key.press("Tab");
  await panel.getByRole("combobox", { name: "Otázka" }).fill("Je text česky a bez chyb?");

  await card(page, "vystup").click();
  await expect(panel.getByRole("combobox", { name: "text" })).toHaveValue("{{ steps.napis.text }}");
  await expect(panel.getByRole("button", { name: /^Podmínka/ })).toHaveCount(0); // output podmínku nemá (scenario.md)
  await expect(panel.getByRole("button", { name: /^Podrobnosti kroku vystup/ })).toHaveAttribute("aria-expanded", "false");

  const saved = page.waitForResponse((r) => r.url().endsWith("/scenarios/clanek/batch") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Uložit" }).click();
  expect((await saved).status()).toBe(200);
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  const doc = project.yaml<Scn>("scenarios/clanek.yaml");
  expect(doc.steps.map((s) => s.id)).toEqual(["napis", "jev_1", "vystup"]);
  expect(doc.steps[1].jev).toEqual({ state: "{{ steps.napis.text }}", questions: { ok: { type: "noul", instructions: "Je text česky a bez chyb?" } } });
  // komentáře šablony zůstaly
  const comments = (t: string) => t.split("\n").filter((l) => l.trim().startsWith("#"));
  expect(comments(project.read("scenarios/clanek.yaml"))).toEqual(comments(template));

  await page.getByRole("main").getByRole("link", { name: "Scénáře", exact: true }).click();
  const sc = page.getByTestId("scenario-card-clanek");
  await expect(sc).toContainText("3 kroky · 1 agent");
  await expect(sc).not.toContainText("clanek.yaml");
  await expect(sc.getByLabel("Typy kroků: ask, jev, output")).toBeVisible();
});

test("C5 validace s chybou a oprava v panelu i v YAML", async ({ page, project }) => {
  const disk = () => project.read("scenarios/ukazka.yaml");
  const original = disk();
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await card(page, "napis").click();
  const prompt = page.getByRole("combobox", { name: "Prompt" });
  await prompt.fill("Téma: {{ steps.nic.text }}");
  // průběžná validace (render) — chyba u karty ještě před Uložit
  await expect(cardBox(page, "napis")).toContainText("krok 'nic' neexistuje");
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText("Změna neprošla kontrolou (1 chyba), nezapsala se.");
  await expect(page.getByRole("button", { name: "1 chyba" })).toBeVisible();
  await expect(page.getByRole("complementary").getByText(/krok 'nic' neexistuje \(dostupné:/)).toBeVisible();
  await expect(prompt).toHaveAttribute("aria-invalid", "true");
  expect(disk()).toBe(original);

  await prompt.fill("Téma: {{ inputs.tema }}");
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  await expect(cardBox(page, "napis")).not.toContainText("neexistuje");
  expect(disk()).toContain('prompt: "Téma: {{ inputs.tema }}"');

  await page.getByRole("radio", { name: "YAML" }).click();
  const area = page.getByRole("textbox", { name: "scenarios/ukazka.yaml" });
  await expect(page.getByText("Upravuješ přímo soubor workflows/scenarios/ukazka.yaml")).toBeVisible();
  await expect(page.getByRole("button", { name: "Uložit" })).toBeDisabled();
  const good = await area.inputValue();
  const line = good.split("\n").findIndex((l) => l.includes("- id: napis")) + 1;
  await area.fill(good.replace("  - id: napis", "  - id: [napis"));
  const form = page.getByRole("radio", { name: "Form" });
  await expect(page.getByText(/^řádek \d+ ·/).first()).toBeVisible({ timeout: 1500 });
  const bad = Number((await page.getByText(/^řádek \d+ ·/).first().textContent())!.match(/řádek (\d+)/)![1]);
  expect(Math.abs(bad - line)).toBeLessThanOrEqual(1);
  await expect(page.getByTestId(`yaml-line-${bad}`)).toBeVisible();
  await expect(form).not.toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("button", { name: "Uložit" })).toBeDisabled();
  await form.click();
  const syntaxDialog = page.getByRole("dialog", { name: "Neuložené změny" });
  await expect(syntaxDialog).toBeVisible();
  await syntaxDialog.getByRole("button", { name: "Zrušit" }).click();
  await expect(page).toHaveURL(/rezim=yaml/);

  await area.fill(good.replace("agent: pisatel", "agent: nikdo"));
  await expect(page.getByText(/napis · .*agent 'nikdo'/)).toBeVisible();
  await expect(form).not.toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("button", { name: "Uložit" })).toBeDisabled();
  const fixed = good.replace("O čem psát", "O čem psát (upraveno)");
  await area.fill(fixed);
  await expect(page.getByRole("button", { name: "Uložit" })).toBeEnabled();
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  expect(disk()).toBe(fixed);
  // zpět do Form vybere krok pod kurzorem
  await area.evaluate((el: HTMLTextAreaElement) => {
    const i = el.value.indexOf("agent: pisatel");
    el.focus();
    el.setSelectionRange(i, i);
  });
  await area.press("ArrowRight");
  await form.click();
  await expect(page).toHaveURL(/krok=napis/);
  await expect(page).not.toHaveURL(/rezim=yaml/);

  // Form → YAML s neuloženou změnou: text z render, bez dialogu
  await page.getByRole("combobox", { name: "Prompt" }).fill("Téma dne: {{ inputs.tema }}");
  await page.getByRole("radio", { name: "YAML" }).click();
  await expect(area).toHaveValue(/prompt: "Téma dne: \{\{ inputs\.tema \}\}"/);
  await expect(saveStatus(page)).toHaveText("Neuloženo");
  // YAML → Form vezme neuložený text přes render, jen syntaktická chyba ponechá dialog.
  const yamlDraft = (await area.inputValue()).replace("Téma dne:", "Téma z YAML:").replace("agent: pisatel", "agent: nikdo");
  await area.fill(yamlDraft);
  await area.evaluate((el: HTMLTextAreaElement) => {
    const i = el.value.indexOf("Téma z YAML:");
    el.focus();
    el.setSelectionRange(i, i);
  });
  await area.press("ArrowRight");
  await page.getByRole("radio", { name: "Form" }).click();
  await expect(page.getByRole("dialog", { name: "Neuložené změny" })).toBeHidden();
  await expect(page.getByRole("complementary").getByRole("combobox", { name: "Prompt" })).toHaveValue("Téma z YAML: {{ inputs.tema }}");
  await expect(cardBox(page, "napis")).toContainText("agent 'nikdo' neexistuje");
  expect(disk()).toContain('prompt: "Téma: {{ inputs.tema }}"');
  await page.getByRole("complementary").getByRole("combobox", { name: "Agent" }).selectOption("pisatel");
  await expect(cardBox(page, "napis")).not.toContainText("neexistuje");
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  expect(disk()).toContain('prompt: "Téma z YAML: {{ inputs.tema }}"');
});

test("C9 konflikt souboru", async ({ page, project }) => {
  const file = path.join(project.wf, "scenarios/ukazka.yaml");
  page.on("dialog", (d) => void d.accept());
  await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Moje verze: {{ inputs.tema }}");
  await expect(saveStatus(page)).toHaveText("Neuloženo");
  fs.appendFileSync(file, "# ručně\n");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const bar = page.getByTestId("conflict-bar");
  await expect(bar).toContainText("Soubor se na disku změnil.");
  await expect(bar.getByRole("button")).toHaveText(["Zobrazit rozdíl", "Načíst z disku a zahodit moje změny", "Ponechat moje"]);
  await expect(page.getByRole("button", { name: "Uložit" })).toBeDisabled();

  await bar.getByRole("button", { name: "Zobrazit rozdíl" }).click();
  const diff = page.getByRole("dialog", { name: "Rozdíl proti disku" });
  await expect(diff).toContainText("− je verze, ze které vycházíš, + je soubor na disku teď.");
  await expect(diff.getByText("+ # ručně")).toBeVisible();
  await diff.getByRole("button", { name: "Zavřít" }).click();

  await bar.getByRole("button", { name: "Ponechat moje" }).click();
  await expect(bar).toBeHidden();
  await page.getByRole("button", { name: "Uložit" }).click();
  const ow = page.getByRole("dialog", { name: "Přepsat verzi na disku?" });
  const req = page.waitForRequest((r) => r.url().endsWith("/batch"));
  const current = sha(fs.readFileSync(file, "utf8"));
  await ow.getByRole("button", { name: "Přepsat verzi na disku" }).click();
  expect((await req).postDataJSON().etag).toBe(current);
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  const text = fs.readFileSync(file, "utf8");
  expect(text).toContain("# ručně");
  expect(text).toContain("Moje verze");

  // bez lokálních změn: tiché znovunačtení
  fs.writeFileSync(file, text.replace("Moje verze", "Cizí verze"));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(saveStatus(page)).toHaveText(/^Načteno z disku \(\d{1,2}:\d{2}\)$/);
  await expect(card(page, "napis")).toContainText("Cizí verze");

  // rozpracovaný draft ke starší verzi po obnovení stránky
  await page.getByRole("combobox", { name: "Prompt" }).fill("Rozpracováno: {{ inputs.tema }}");
  fs.appendFileSync(file, "# zase ručně\n");
  await page.reload();
  await expect(page.getByTestId("conflict-bar")).toContainText("Rozpracované změny v prohlížeči patří ke starší verzi souboru.");
});

test("C10 přesun a smazání kroku s ochranou odkazů", async ({ page, project }) => {
  project.write("scenarios/clanek.yaml", CLANEK);
  await page.goto(`/#/p/${project.name}/scenare/clanek`);
  await card(page, "jev_1").click();
  await card(page, "jev_1").press("Alt+ArrowUp");
  await expect(card(page, "jev_1")).toHaveAttribute("aria-label", "Krok 1: jev jev_1");
  await expect(card(page, "napis")).toHaveAttribute("aria-label", "Krok 2: ask napis");
  await page.getByRole("button", { name: "Další akce" }).click();
  await page.getByRole("menuitem", { name: "Vrátit zpět" }).click();
  await expect(card(page, "napis")).toHaveAttribute("aria-label", "Krok 1: ask napis");
  await page.getByRole("button", { name: "Akce pro jev_1" }).click();
  for (const name of ["Posunout nahoru", "Posunout dolů", "Vyjmout", "Vložit krok nad", "Vložit krok pod", "Smazat"])
    await expect(page.getByRole("menuitem", { name, exact: true })).toBeVisible();
  await page.keyboard.press("Escape");

  await card(page, "jev_1").focus();
  await page.keyboard.press("Control+x");
  await expect(live(page)).toHaveText("Krok jev_1 vyjmut — vlož ho tlačítkem + na novém místě.");
  await expect(card(page, "jev_1")).toHaveAttribute("aria-label", /— vyjmuto$/);
  await page.getByRole("button", { name: "Vložit krok na začátek" }).click();
  const picker = page.getByRole("listbox", { name: "Typ nového kroku" });
  await expect(picker.getByRole("option").first()).toHaveText("Vložit „jev_1“ sem");
  await picker.press("Enter");
  await expect(live(page)).toHaveText("Krok jev_1 vložen.");
  expect(await page.locator("[data-step-card]").evaluateAll((els) => els.map((e) => e.getAttribute("data-step-card")))).toEqual(["", "jev_1", "napis", "vystup"]);
  // render: jev_1 teď čte krok, který je až pod ním
  await expect(cardBox(page, "jev_1").locator("p.text-error")).toBeVisible();
  await card(page, "jev_1").focus();
  await page.keyboard.press("Control+z");
  expect(await page.locator("[data-step-card]").evaluateAll((els) => els.map((e) => e.getAttribute("data-step-card")))).toEqual(["", "napis", "jev_1", "vystup"]);

  const original = project.read("scenarios/clanek.yaml");
  await card(page, "napis").focus();
  await page.keyboard.press("Delete");
  const del = page.getByRole("dialog", { name: "Smazat krok „napis“?" });
  await expect(del).toContainText("Krok „napis“ čtou jev_1, vystup. Uložení projde, jen když jejich odkazy upravíš nebo je smažeš taky");
  await del.getByRole("button", { name: "Smazat i tak" }).click();
  await expect(live(page)).toHaveText("Krok napis smazán. Vrátit zpět: Ctrl+Z.");
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Změna neprošla kontrolou/);
  await expect(cardBox(page, "vystup")).toContainText("napis");
  expect(project.read("scenarios/clanek.yaml")).toBe(original);

  // úprava čtenářů + smazání v jedné dávce
  // panel jev_1 je otevřený od začátku (Esc v menu ⋯ zavřel jen menu, ne panel)
  await expect(card(page, "jev_1")).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("combobox", { name: "State" }).fill("{{ inputs.tema }}");
  await card(page, "vystup").click();
  await page.getByRole("combobox", { name: "text" }).fill("{{ inputs.tema }}");
  const req = page.waitForRequest((r) => r.url().endsWith("/batch"));
  await page.getByRole("button", { name: "Uložit" }).click();
  const ops = (await req).postDataJSON().ops as { op: string }[];
  expect(ops.map((o) => o.op).sort()).toEqual(["delete_step", "update_step", "update_step"]);
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  expect(project.yaml<Scn>("scenarios/clanek.yaml").steps.map((s) => s.id)).toEqual(["jev_1", "vystup"]);

  // krok, který nikdo nečte, zmizí bez dialogu
  await card(page, "jev_1").focus();
  await page.keyboard.press("Delete");
  await expect(page.getByRole("dialog")).toBeHidden();
  const req2 = page.waitForRequest((r) => r.url().endsWith("/batch"));
  await page.getByRole("button", { name: "Uložit" }).click();
  expect((await req2).postDataJSON().ops).toEqual([{ op: "delete_step", address: ["steps", 0] }]);
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  expect(project.yaml<Scn>("scenarios/clanek.yaml").steps.map((s) => s.id)).toEqual(["vystup"]);

  // output: bez posunu, vyjmutí a vložení pod; karta nemaže mimo ⋯
  await page.getByRole("button", { name: "Akce pro vystup" }).click();
  await expect(page.getByRole("menuitem", { name: "Vložit krok nad" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Smazat" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("region", { name: "Kroky scénáře" }).getByRole("button", { name: /^Smazat krok / })).toHaveCount(0);
});

test("C11 parallel a switch", async ({ page, project, server }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  const disk = () => project.read("scenarios/ukazka.yaml");
  const original = disk();
  await page.getByTestId("add-after-napis").click();
  let picker = page.getByRole("listbox", { name: "Typ nového kroku" });
  await picker.press("p");
  await expect(picker.getByRole("option")).toHaveText([/^parallel\s*větve zároveň$/]);
  await picker.press("Enter");
  await expect(card(page, "parallel_1")).toHaveAttribute("aria-label", "Krok 2: parallel parallel_1");
  const panel = page.getByRole("complementary");
  await expect(panel).toContainText("Větve: a, b. Kroky do nich přidáš tlačítkem + v kartě.");
  await page.getByRole("button", { name: "+ větev" }).click();
  const dlg = page.getByRole("dialog", { name: "větev" });
  await dlg.getByRole("textbox", { name: "Jméno" }).fill("kratka");
  await dlg.getByRole("button", { name: "Vytvořit" }).click();
  const kratka = page.getByTestId("branch-kratka");
  await expect(kratka).toHaveAttribute("aria-label", "kratka");
  await expect(kratka.getByRole("heading", { name: "kratka", level: 4 })).toBeVisible();

  // prázdné větve: validace výsledku dávky, nic se nezapíše
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Změna neprošla kontrolou/);
  expect(disk()).toBe(original);

  for (const b of ["a", "b", "kratka"]) {
    await page.getByTestId(`branch-${b}`).getByRole("button", { name: "Přidat krok na konec" }).click();
    picker = page.getByRole("listbox", { name: "Typ nového kroku" });
    await expect(picker.getByRole("option")).not.toContainText([/^output/]);
    await picker.press("a");
    await picker.press("Enter");
    await panel.getByRole("combobox", { name: "Agent" }).selectOption("pisatel");
    await panel.getByRole("combobox", { name: "Prompt" }).fill(`Větev ${b}: {{ inputs.tema }}`);
  }
  const req = page.waitForRequest((r) => r.url().endsWith("/batch"));
  await page.getByRole("button", { name: "Uložit" }).click();
  expect((await req).postDataJSON().ops.map((o: { op: string }) => o.op)).toEqual(["add_step"]);
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  type Par = { parallel: Record<string, { id: string }[]> };
  const par = project.yaml<Scn>("scenarios/ukazka.yaml").steps[1] as unknown as Par;
  expect(Object.keys(par.parallel)).toEqual(["a", "b", "kratka"]);
  expect(Object.values(par.parallel).map((l) => l.length)).toEqual([1, 1, 1]);
  await expect(card(page, "parallel_1")).toContainText("a ∥ b ∥ kratka");
  await expect(card(page, "parallel_1")).toContainText("3 větve, běží zároveň");

  const collapse = page.getByRole("button", { name: "Sbalit parallel_1" });
  await expect(collapse).toHaveAttribute("aria-expanded", "true");
  await collapse.click();
  await expect(kratka).toBeHidden();
  await expect(card(page, "parallel_1").locator("xpath=../../..")).toContainText("3 kroky");
  await page.getByRole("button", { name: "Rozbalit parallel_1" }).click();
  await expect(kratka).toBeVisible();

  // kontejner se maže i s vnitřkem → dialog
  await card(page, "parallel_1").focus();
  await page.keyboard.press("Delete");
  await expect(page.getByRole("dialog")).toContainText("Smaže i 3 kroky uvnitř.");
  await page.getByRole("dialog").getByRole("button", { name: "Zrušit" }).click();

  // switch
  await page.getByTestId("add-after-parallel_1").click();
  picker = page.getByRole("listbox", { name: "Typ nového kroku" });
  await picker.press("s");
  await picker.press("w");
  await picker.press("Enter");
  await expect(panel).toContainText("„jinak“ se zapíše vždy");
  await panel.getByRole("combobox", { name: "Hodnota" }).fill("steps.napis.text");
  await expect(page.getByTestId("case-default")).toBeVisible();
  await page.getByRole("button", { name: "+ případ" }).click();
  const pd = page.getByRole("dialog", { name: "případ" });
  await pd.getByRole("textbox", { name: "Jméno" }).fill("ano");
  await pd.getByRole("button", { name: "Vytvořit" }).click();
  await page.getByTestId("case-ano").getByRole("button", { name: "Přidat krok na konec" }).click();
  await page.getByRole("listbox", { name: "Typ nového kroku" }).press("f");
  await page.getByRole("listbox", { name: "Typ nového kroku" }).press("Enter");
  await panel.getByRole("combobox", { name: "Zpráva" }).fill("Nemělo by nastat");
  // `default` je povinný (scenario.md D1d) — GUI ho zapíše vždy, prázdný = vědomé „nic nedělej“
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  expect((project.yaml<Scn>("scenarios/ukazka.yaml").steps[2] as unknown as { switch: { default: unknown[] } }).switch.default).toEqual([]);

  await page.getByTestId("case-default").getByRole("button", { name: "Přidat krok na konec" }).click();
  picker = page.getByRole("listbox", { name: "Typ nového kroku" });
  await picker.press("s");
  await picker.press("e");
  await picker.press("Enter");
  await panel.getByRole("button", { name: "Přidat hodnotu" }).click();
  await panel.getByRole("combobox").last().fill("inputs.tema");
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  const sw = project.yaml<Scn>("scenarios/ukazka.yaml").steps[2] as unknown as { switch: { value: string; cases: Record<string, unknown[]>; default: unknown[] } };
  expect(sw.switch.value).toBe("steps.napis.text");
  expect(Object.keys(sw.switch.cases)).toEqual(["ano"]);
  expect(sw.switch.default).toHaveLength(1);

  // v běhu: nevybraný případ ztlumený, větve se stavem
  const id = await startRun(server, project.name, "ukazka");
  await waitRun(server, project.name, id, ["succeeded"]);
  await page.goto(`/#/p/${project.name}/behy/${id}`);
  const nevybrany = page.getByTestId("case-ano").locator("[data-step-card]");
  await expect(nevybrany).toHaveAttribute("aria-label", /— přeskočeno$/);
  await expect(nevybrany).toContainText("přeskočeno:");
  await expect(nevybrany).toHaveCSS("border-top-style", "dashed"); // ztlumená (bez průhlednosti kvůli kontrastu)
  await expect(page.getByTestId("case-default").locator("[data-step-card]")).toHaveAttribute("aria-label", /— úspěch$/);
  for (const b of ["a", "b", "kratka"])
    await expect(page.getByTestId(`branch-${b}`).locator("[data-step-card]")).toHaveAttribute("aria-label", /— úspěch$/);
});

test("C12 přejmenování kroku s přepisem odkazů", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
  const panel = page.getByRole("complementary");
  const details = panel.getByRole("button", { name: /^Podrobnosti kroku/ });
  await details.click();
  await expect(details).toHaveAttribute("aria-expanded", "true");
  await expect(panel.getByText("Čte z")).toBeVisible();
  await expect(panel.locator("dd").first()).toHaveText("nic");
  await expect(panel.getByRole("link", { name: "Otevřít v YAML" })).toHaveAttribute("href", /krok=napis&rezim=yaml|rezim=yaml.*krok=napis/);
  await panel.getByRole("button", { name: "vystup", exact: true }).click();
  await expect(page).toHaveURL(/krok=vystup/);
  await card(page, "napis").click();
  await panel.getByRole("button", { name: /^Podrobnosti kroku/ }).click();

  const id = panel.getByRole("textbox", { name: "id" });
  await id.fill("Napis");
  await expect(panel.getByText("Malá písmena, číslice a _, začíná písmenem.")).toBeVisible();
  await id.fill("vystup");
  await expect(panel.getByText("„vystup“ už existuje.")).toBeVisible();
  await id.press("Tab");
  await expect(card(page, "napis")).toBeVisible();

  await id.fill("text_clanku");
  await id.press("Tab");
  const dlg = page.getByRole("dialog", { name: "Přepsat odkazy v 1 kroku?" });
  await expect(dlg.getByRole("listitem")).toHaveText(["vystup"]);
  await dlg.getByRole("button", { name: "Přejmenovat a přepsat odkazy" }).click();
  await expect(card(page, "text_clanku")).toHaveAttribute("aria-label", "Krok 1: ask text_clanku");
  await expect(page).toHaveURL(/krok=text_clanku/);
  await page.waitForTimeout(800); // render
  await expect(cardBox(page, "vystup").locator("p.text-error")).toHaveCount(0);

  const req = page.waitForRequest((r) => r.url().endsWith("/scenarios/ukazka/batch"));
  await page.getByRole("button", { name: "Uložit" }).click();
  expect((await req).postDataJSON().ops[0]).toEqual({ op: "rename_step", address: ["steps", 0], new_id: "text_clanku", rename_refs: true });
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  const text = project.read("scenarios/ukazka.yaml");
  expect(text).toContain("- id: text_clanku");
  expect(text).toContain("{{ steps.text_clanku.text }}");
});

test("C15 klávesnicová cesta bez myši", async ({ page, project }) => {
  await page.goto("/");
  await tabTo(page, page.getByRole("link", { name: project.name, exact: true }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Scénáře", level: 1 })).toBeVisible();
  await tabTo(page, page.getByRole("button", { name: "Nový scénář" }));
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Nový scénář" });
  await expect(dialog.getByRole("textbox", { name: "Jméno" })).toBeFocused();
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Nový scénář" })).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.type("klavesy");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/scenare\/klavesy/);

  await tabTo(page, card(page, ""));
  await page.keyboard.press("ArrowDown");
  await expect(card(page, "napis")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/krok=napis/);
  const panel = page.getByRole("complementary");
  await expect(panel.getByRole("combobox", { name: "Typ kroku" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(card(page, "napis")).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Akce pro napis" })).toBeFocused();
  await page.keyboard.press("Tab");
  const plus = page.getByTestId("add-after-napis");
  await expect(plus).toBeFocused();
  await expect(plus).toHaveAccessibleName("Vložit krok za napis");
  expect(await plus.evaluate((el) => getComputedStyle(el).boxShadow)).not.toBe("none"); // focus-visible ring
  await expect(plus).toHaveCSS("opacity", "1");
  await page.keyboard.press("Enter");
  const picker = page.getByRole("listbox", { name: "Typ nového kroku" });
  await expect(picker).toBeFocused();
  await page.keyboard.press("j");
  await expect(picker.getByText("filtr: j")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(plus).toBeFocused();

  await tabTo(page, card(page, "napis"), 10, "Shift+Tab");
  await page.keyboard.press("Delete");
  const del = page.getByRole("dialog", { name: "Smazat krok „napis“?" });
  await expect(del.getByRole("button", { name: "Smazat i tak" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(del).toBeHidden();

  await tabTo(page, page.getByRole("button", { name: "Akce pro napis" }));
  await page.keyboard.press("Enter");
  const items = page.getByRole("menuitem");
  await expect(items.first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(items.nth(1)).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Akce pro napis" })).toBeFocused();

  // hlavička klávesami: Enter → fokus v panelu, psaní, Ctrl+S
  await tabTo(page, card(page, ""), 20, "Shift+Tab");
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("textbox", { name: /^popis/ })).toBeFocused();
  await page.keyboard.press("End");
  await page.keyboard.type(" z klávesnice");
  await page.keyboard.press("Control+s");
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓ \d/);
  await expect(page.locator("[aria-live]").first()).toBeAttached();
  expect(project.read("scenarios/klavesy.yaml")).toMatch(/description: .* z klávesnice/);
});

test("N1 server neodpovídá", async ({ page, project, server }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Offline: {{ inputs.tema }}");
  await expect(saveStatus(page)).toHaveText("Neuloženo");
  await page.route(/\/projects/, (r) => r.abort());
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const bar = page.getByTestId("server-bar");
  await expect(bar).toHaveText(`Server agencast neodpovídá (127.0.0.1:${server.port}), zkouším znovu…`);
  await expect(bar).toHaveRole("alert");
  await expect(card(page, "napis")).toContainText("Offline");
  await expect(saveStatus(page)).toHaveText("Neuloženo");
  expect(await page.evaluate(() => Object.keys(localStorage).some((k) => k.startsWith("agencast.draft.")))).toBe(true);
  await page.unroute(/\/projects/);
  await expect(bar).toBeHidden({ timeout: 7_000 });
});

test("N6 odchod s neuloženými změnami", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
  await page.getByRole("combobox", { name: "Prompt" }).fill("Neuloženo: {{ inputs.tema }}");
  await expect(saveStatus(page)).toHaveText("Neuloženo");
  const kinds: string[] = [];
  page.on("dialog", (d) => (kinds.push(d.type()), void d.accept()));
  await page.reload();
  expect(kinds).toContain("beforeunload");
  await expect(saveStatus(page)).toHaveText("Neuloženo");
  await expect(card(page, "napis")).toContainText("Neuloženo:");

  // odkaz na jinou stránku GUI se ptá; odmítnutí = zůstat
  page.removeAllListeners("dialog");
  page.once("dialog", (d) => (kinds.push(d.type()), void d.dismiss()));
  await page.getByRole("main").getByRole("link", { name: "Scénáře", exact: true }).click();
  await expect(page).toHaveURL(/scenare\/ukazka/);
  expect(kinds.at(-1)).toBe("confirm");
  page.once("dialog", (d) => void d.accept());
  await page.getByRole("main").getByRole("link", { name: "Scénáře", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`#/p/${project.name}/scenare$`));

  await expect(page.getByRole("button", { name: "Nový scénář" })).toBeVisible();
  await page.getByRole("link", { name: "ukazka" }).click();
  await page.getByRole("button", { name: /Krok 1: ask napis/ }).click();
  await page.getByRole("combobox", { name: /Prompt/ }).fill("Zpět: {{ inputs.tema }}");
  page.once("dialog", (d) => (kinds.push(d.type()), void d.dismiss()));
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`#/p/${project.name}/scenare/ukazka`));
  expect(kinds.at(-1)).toBe("confirm");
});

// Ladění 2026-09-26: alias modelu v Configu má jméno s pomlčkou (jako agent) a zapíše se stylem ostatních aliasů.
test("C17 alias modelu s pomlčkou v Configu", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/config`);
  await page.getByRole("button", { name: "+ alias" }).click();
  const alias = page.getByRole("textbox", { name: "Alias" }).last();
  await expect(alias).toHaveValue("model-1");
  await alias.fill("GPT image");
  await expect(alias).toHaveAttribute("aria-invalid", "true");
  await alias.press("Enter");
  await expect(alias).toHaveValue("model-1"); // neplatné se vrátí
  await alias.fill("gpt-image");
  await alias.press("Enter");
  await expect(page.getByRole("textbox", { name: "Alias" }).last()).toHaveValue("gpt-image");
  await page.getByRole("textbox", { name: "Id modelu gpt-image" }).fill("openai/gpt-image-2");
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/Uloženo/);
  const text = project.read("config.yaml");
  expect(text).toContain("  gpt-image: {id: openai/gpt-image-2}\n");
  expect(text).toContain("  chytry:       { id: anthropic/claude-haiku-4.5 }\n"); // ostatní řádky doslova
  // po novém načtení alias v nabídce modelu agenta
  await page.goto(`/#/p/${project.name}/agenti/pisatel`);
  await expect(page.getByRole("combobox", { name: /^model/ }).locator("option", { hasText: "gpt-image — openai/gpt-image-2" })).toHaveCount(1);
});

test("C18 vložení proměnné z nabídky myší i klávesnicí", async ({ page, project }) => {
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: /Krok 1: ask napis/ }).click();
  const prompt = page.getByRole("combobox", { name: /Prompt/ });
  const insert = page.getByRole("button", { name: "Vložit proměnnou" });

  await prompt.fill("Napiš dlouhý text");
  await prompt.click({ position: { x: 72, y: 12 } });
  await insert.click();
  await page.getByRole("menuitem", { name: "inputs.tema" }).click();
  await expect(prompt).toHaveValue(/{{ inputs\.tema }}/);
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  expect(project.read("scenarios/ukazka.yaml")).toContain("{{ inputs.tema }}");

  await prompt.fill("Další text");
  await prompt.press("Tab");
  await expect(insert).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(prompt).toHaveValue(/{{ inputs\.tema }}/);
  await page.getByRole("button", { name: "Uložit" }).click();
  await expect(saveStatus(page)).toHaveText(/^Uloženo ✓/);
  expect(project.read("scenarios/ukazka.yaml")).toContain("Další text{{ inputs.tema }}");
});

test("C19 přejmenování scénáře přepíše call a naviguje na nové jméno", async ({ page, project }) => {
  project.write("scenarios/ukazka.yaml", project.read("scenarios/ukazka.yaml").replace(
    /^name: ukazka$/m, "name: ukazka\ncallable: true"));
  project.write("scenarios/volani.yaml", `version: 1
name: volani
description: Volá ukazka
inputs:
  tema: { type: string, default: káva }
outputs:
  text: { type: string }
steps:
  - id: spust
    call:
      scenario: ukazka
      inputs:
        tema: "{{ inputs.tema }}"
  - id: vystup
    output:
      text: "{{ steps.spust.text }}"
`);
  await page.goto(`/#/p/${project.name}/scenare/ukazka`);
  await page.getByRole("button", { name: "Další akce" }).click();
  await page.getByRole("menuitem", { name: "Přejmenovat" }).click();
  const dialog = page.getByRole("dialog", { name: "Přejmenovat scénář „ukazka“?" });
  await expect(dialog.getByRole("textbox", { name: "Jméno" })).toHaveValue("ukazka");
  await dialog.getByRole("textbox", { name: "Jméno" }).fill("uvod");
  await dialog.getByRole("button", { name: "Přejmenovat" }).click();

  await expect(page).toHaveURL(new RegExp(`/scenare/uvod(?:\\?|$)`));
  await expect(page.getByRole("heading", { name: "uvod", level: 1 })).toBeVisible();
  expect(project.yaml<{ name: string }>("scenarios/uvod.yaml").name).toBe("uvod");
  expect(project.yaml<{ steps: { call: { scenario: string } }[] }>("scenarios/volani.yaml").steps[0].call.scenario).toBe("uvod");
  expect(fs.existsSync(path.join(project.wf, "scenarios/ukazka.yaml"))).toBe(false);
  await expect(page.getByText(/^Přepsáno:/)).toContainText("scenarios/uvod.yaml");
  await expect(page.getByText(/^Přepsáno:/)).toContainText("scenarios/volani.yaml");
});
