import { defineConfig, devices } from "@playwright/test";

// End-to-end tests against the production images behind Caddy (ADR-013):
// start them with `docker compose -f compose.yaml -f compose.prod.yaml up
// --detach --wait`, then `pnpm e2e`. The site is on HTTPS_PORT 8443, as in
// the README and in CI; E2E_BASE_URL points elsewhere.
export default defineConfig({
  testDir: ".",
  // Relative to this file; by default it would be next to package.json.
  outputDir: "test-results",
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://localhost:8443",
    // Caddy's certificate comes from its internal CA (ADR-004).
    ignoreHTTPSErrors: true,
    locale: "en-US",
    // Kept only when a test fails; CI uploads them (ADR-013).
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  // Desktop Chromium on every pull request; mobile Chromium and WebKit
  // come before the pilot (ADR-013).
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
