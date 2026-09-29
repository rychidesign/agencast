// A real server outage: kill `serve` mid-edit, wait, start it again.
import { chromium } from "@playwright/test";
import { execSync, spawn } from "node:child_process";
import fs from "node:fs";
const URL = "http://127.0.0.1:28950", S = "/tmp/agencast-qa/srv";
const BIN = `${import.meta.dirname}/../../../framework/.venv/bin/agencast`;
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1440, height: 900 } });
await page.addInitScript(() => localStorage.setItem("agencast.token", "test-token"));
page.setDefaultTimeout(8000);
await page.goto(`${URL}/#/p/demo/scenarios/demo?step=write`);
await page.getByRole("combobox", { name: "Prompt" }).fill("Change during the outage");
execSync(`pkill -f "[s]erve --fake ${S}/fake.yaml"`);
await page.waitForTimeout(500);
await page.getByRole("button", { name: "Save" }).click();
await page.getByTestId("server-bar").waitFor();
console.log("outage: SaveNote =", await page.getByTestId("save-status").textContent());
await page.screenshot({ path: "/tmp/agencast-qa/flows/restart-outage.png" });
const env = { ...process.env, AGENCAST_CONFIG_DIR: `${S}/cfg`, AGENCAST_TOKEN: "test-token", OPENROUTER_API_KEY: "qa" };
spawn(BIN, ["serve", "--fake", `${S}/fake.yaml`, "--host", "127.0.0.1", "--port", "28950"],
  { cwd: S, env, detached: true, stdio: ["ignore", fs.openSync(`${S}/serve.log`, "a"), fs.openSync(`${S}/serve.log`, "a")] }).unref();
await page.getByTestId("server-bar").waitFor({ state: "detached", timeout: 15000 });
console.log("after restart: server-bar gone; SaveNote =", await page.getByTestId("save-status").textContent());
await page.getByRole("button", { name: "Save" }).click();
await page.waitForTimeout(1000);
console.log("save after restart:", await page.getByTestId("save-status").textContent());
await b.close();
