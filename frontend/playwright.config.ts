import { defineConfig, devices } from "@playwright/test";

// E2e (#128): draait tegen een reeds draaiende frontend + backend. De basis-URL
// is instelbaar via E2E_BASE_URL (default localhost:3000). In CI start een
// non-blocking job de stack en zet die var.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
