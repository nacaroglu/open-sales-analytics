/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import { configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Node's process, declared by hand: @types/node is not installed. Only the e2e
// run sets E2E_BACKEND_PORT (see playwright.config.ts); normally it is 8000.
declare const process: { env: Record<string, string | undefined> };
const backendPort = process.env.E2E_BACKEND_PORT ?? "8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": `http://127.0.0.1:${backendPort}`,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
