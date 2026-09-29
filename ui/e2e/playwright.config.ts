// E2E per docs/ui/user-journeys.md: the built GUI from `agencast serve --fake` (one server per worker,
// fixtures.ts), headless Chromium. Run by `npm run e2e` (which runs `npm run build` first).
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
    locale: "en-US",
    timezoneId: "Europe/Prague",
    trace: "retain-on-failure",
    actionTimeout: 10_000,
  },
});
