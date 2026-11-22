import path from "node:path";
import os from "node:os";
import { defineConfig, devices } from "@playwright/test";

// Isolated backend (mock providers, throwaway data dir) + frontend on their own ports.
const API_PORT = 8100;
const WEB_PORT = 3100;
const dataDir = path.join(os.tmpdir(), `replay-e2e-${process.pid}`);
const backendDir = path.resolve(__dirname, "..", "backend");

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run uvicorn app.main:app --port ${API_PORT}`,
      cwd: backendDir,
      url: `http://localhost:${API_PORT}/api/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        DATA_DIR: dataDir,
        DEMO_DIR: path.join(dataDir, "demo"),
        VLM_PROVIDER: "mock",
        LLM_PROVIDER: "mock",
        EMBEDDING_BACKEND: "hash",
        WHISPER_ENABLED: "false",
        SEED_DEMOS_ON_STARTUP: "false",
        CORS_ORIGINS: `http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}`,
      },
    },
    {
      command: `npm run dev -- --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: { NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}` },
    },
  ],
});
