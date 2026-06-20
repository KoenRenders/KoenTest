import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

// Unit-tests voor pure frontend-logica (filter-predicaten, URL-bouw, …).
// E2E-flows blijven in `e2e/` onder Playwright — die sluiten we hier expliciet uit.
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
