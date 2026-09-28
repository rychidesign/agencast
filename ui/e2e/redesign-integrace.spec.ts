// Vlna C redesignu V3: jedna hlavička na sekci (G1–G4) a rozložení na tabletu (G14).
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

const noOverflow = async (page: Page, w: number) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(w);

test("IC1 sekce projektu: jedno h1, nejvýš jedno Uložit a Načíst znovu v ⋯", async ({ page, project }) => {
  const sections: [string, string, string[]][] = [
    ["", "Scénáře", ["Nový scénář"]],
    ["/agenti", "Agenti", ["Nový agent", "Uložit"]],
    ["/skilly", "Skilly", ["Nový skill"]],
    ["/behy", "Běhy", []],
    ["/config", "Config", ["Uložit"]],
  ];
  for (const [path, title, buttons] of sections) {
    await page.goto(`/#/p/${project.name}${path}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText([title]);
    const header = page.locator("main header");
    for (const b of buttons) await expect(header.getByRole("button", { name: b })).toBeVisible();
    expect(await page.getByRole("button", { name: "Uložit" }).count()).toBeLessThanOrEqual(1);
    expect(await page.getByRole("radiogroup", { name: "Zobrazení" }).count()).toBeLessThanOrEqual(1);
    await header.getByRole("button", { name: /^(Další akce|Akce pro .+)$/ }).click();
    await expect(page.getByRole("menuitem").first()).toHaveText("Načíst znovu");
    await page.keyboard.press("Escape");
  }
});

for (const w of [768, 1024]) {
  test(`IC2w${w} tablet: bez přetečení, panel jde zavřít`, async ({ page, project }) => {
    await page.setViewportSize({ width: w, height: 900 });
    for (const path of ["", "/agenti", "/behy", "/config"]) {
      await page.goto(`/#/p/${project.name}${path}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await noOverflow(page, w);
    }
    await page.goto(`/#/p/${project.name}/scenare/ukazka?krok=napis`);
    // pod 1280 px je panel plnoobrazovkový sheet (vlna G), nikdy přes sloupec
    const panel = page.getByRole("dialog", { name: /KROK 1/ });
    expect(await panel.boundingBox()).toEqual({ x: 0, y: 0, width: w, height: 900 });
    await panel.getByRole("button", { name: "Zavřít" }).click();
    await expect(panel).toBeHidden();
    await noOverflow(page, w);
  });
}
