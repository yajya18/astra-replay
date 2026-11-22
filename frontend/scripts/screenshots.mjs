// Capture README screenshots from a running app (default http://localhost:3000, API :8000).
// Usage: node scripts/screenshots.mjs [webUrl] [apiUrl]
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = process.argv[2] ?? "http://localhost:3000";
const api = process.argv[3] ?? "http://localhost:8000";
const out = path.resolve(here, "..", "..", "docs", "screenshots");
fs.mkdirSync(out, { recursive: true });

const demos = (await (await fetch(`${api}/api/demo`)).json()).items.filter(
  (d) => d.status === "completed",
);
const skipped = demos.find((d) => d.slug.includes("skipped")) ?? demos[0];
if (!skipped) throw new Error("No completed demos. Run `make demo` first.");

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  colorScheme: "dark",
  deviceScaleFactor: 1,
});

async function shot(url, name, prepare) {
  await page.goto(`${web}${url}`, { waitUntil: "load" });
  if (prepare) await prepare();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(out, name) });
  console.log("saved", name);
}

await shot("/", "upload.png");
await shot(`/results/${skipped.job_id}`, "results.png", async () => {
  await page.getByTestId("step-list").waitFor();
});
await shot(`/results/${skipped.job_id}`, "procedure-check.png", async () => {
  await page.getByTestId("verdict").scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -120);
});
await shot(`/results/${skipped.job_id}`, "search.png", async () => {
  const box = page.getByRole("textbox", { name: "Search the video" });
  await box.fill("when did I heat the butter?");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("list", { name: "Search results" }).waitFor();
  await box.scrollIntoViewIfNeeded();
});
await shot(`/xr?job=${skipped.job_id}`, "xr.png", async () => {
  await page.waitForTimeout(2500);
});
await browser.close();
