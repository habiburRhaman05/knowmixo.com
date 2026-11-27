import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Backend DB round trips are currently ~2.5-3s each (confirmed directly
  // against the backend, independent of the frontend/BFF -- see report),
  // so generous timeouts here are tolerating real infra latency, not
  // masking a frontend bug.
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // The default 1280x720 viewport clips wide dialogs (e.g. the
    // "Add a knowledge source" modal) off the right/bottom edge.
    viewport: { width: 1600, height: 1000 },
  },
  projects: [
    {
      name: "setup",
      testMatch: /global\.setup\.ts/,
    },
    {
      name: "chromium",
      // devices["Desktop Chrome"] carries its own 1280x720 viewport, which
      // was silently overriding the top-level `use.viewport` above (project
      // `use` merges OVER the top-level one) -- re-assert it after the
      // spread so the wider viewport actually applies.
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 1600 }, storageState: "e2e/.auth/user.json" },
      dependencies: ["setup"],
    },
  ],
});
