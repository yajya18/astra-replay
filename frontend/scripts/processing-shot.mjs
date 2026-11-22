// Upload a synthetic test video and screenshot the processing page mid-job.
// Usage: node scripts/processing-shot.mjs [webUrl] [apiUrl]
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = process.argv[2] ?? "http://localhost:3000";
const api = process.argv[3] ?? "http://localhost:8000";
const video = path.resolve(
  here,
  "..",
  "..",
  "backend",
  "tests",
  "fixtures",
  "videos",
  "standard.mp4",
);

const form = new FormData();
form.append("video", await fs.openAsBlob(video), "sunday-omelette.mp4");
form.append("title", "Sunday omelette");
form.append(
  "reference_steps",
  "1. Crack the eggs into a bowl\n2. Whisk the eggs with a fork\n3. Chop the chives with a knife\n4. Heat the butter in the pan",
);
const { job_id } = await (await fetch(`${api}/api/jobs`, { method: "POST", body: form })).json();

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
await page.goto(`${web}/jobs/${job_id}`, { waitUntil: "load" });
await page.getByText("Understanding actions").waitFor();
for (let i = 0; i < 120; i++) {
  const active = await page
    .locator('li[aria-current="step"]')
    .first()
    .textContent()
    .catch(() => "");
  if (active?.includes("Understanding")) break;
  await page.waitForTimeout(250);
}
await page.waitForTimeout(700);
await page.screenshot({
  path: path.resolve(here, "..", "..", "docs", "screenshots", "processing.png"),
});
console.log("saved processing.png for job", job_id);
await browser.close();
