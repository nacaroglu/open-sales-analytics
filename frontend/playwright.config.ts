import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const backendPort = process.env.E2E_BACKEND_PORT ?? "8000";
const frontendPort = process.env.E2E_FRONTEND_PORT ?? "5173";
const externalUrl = process.env.E2E_BASE_URL;

// This file is loaded again in every worker process, so the temporary dataset
// directory is created only when the variable is not set yet; workers inherit
// it. Only the process that created it removes it, when the run ends.
if (!externalUrl && !process.env.E2E_DATASET_DIR) {
  const dir = mkdtempSync(join(tmpdir(), "osa-e2e-"));
  process.env.E2E_DATASET_DIR = dir;
  process.on("exit", () => rmSync(dir, { recursive: true, force: true }));
}

export default defineConfig({
  testDir: "./e2e",
  retries: 0,
  reporter: "list",
  expect: { timeout: 10_000 },
  use: {
    baseURL: externalUrl ?? `http://127.0.0.1:${frontendPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: externalUrl
    ? undefined
    : [
        {
          command: `uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port ${backendPort}`,
          cwd: "..",
          url: `http://127.0.0.1:${backendPort}/api/health`,
          reuseExistingServer: false,
          env: {
            DATASET_DIR: process.env.E2E_DATASET_DIR ?? "",
            PUBLIC_DEMO_MODE: "false",
            // Datasets live one minute so the expiry journey sees a real expiry.
            DATASET_TTL_SECONDS: "60",
          },
        },
        {
          command: `npx vite --host 127.0.0.1 --port ${frontendPort} --strictPort`,
          url: `http://127.0.0.1:${frontendPort}`,
          reuseExistingServer: false,
          env: { E2E_BACKEND_PORT: backendPort },
        },
      ],
});
