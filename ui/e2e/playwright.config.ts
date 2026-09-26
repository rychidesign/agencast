// E2E podle docs/ui/uzivatelske-cesty.md: sestavené GUI ze `agencast serve --fake` (jeden server na worker,
// fixtures.ts), headless Chromium. Spouští `npm run e2e` (nejdřív `npm run build`).
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  outputDir: "test-results",
  fullyParallel: false,
  workers: process.env.CI ? 2 : 4,
  timeout: 60_000,
  expect: { timeout: 8_000 },
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    ...devices["Desktop Chrome"],
    viewport: { width: 1400, height: 900 },
    locale: "cs-CZ",
    timezoneId: "Europe/Prague",
    trace: "retain-on-failure",
    actionTimeout: 10_000,
  },
});
