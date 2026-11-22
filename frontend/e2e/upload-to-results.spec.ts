import path from "node:path";
import fs from "node:fs";
import { expect, test } from "@playwright/test";

const VIDEO = path.resolve(
  __dirname,
  "..",
  "..",
  "backend",
  "tests",
  "fixtures",
  "videos",
  "standard.mp4",
);

test.beforeAll(() => {
  if (!fs.existsSync(VIDEO)) {
    throw new Error(`Missing ${VIDEO}. Run "make test-videos" first.`);
  }
});

test("upload a synthetic video in mock mode and reach a results page with steps", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("replayed");

  await page.locator('input[type="file"]').setInputFiles(VIDEO);
  await expect(page.getByText("standard.mp4")).toBeVisible();
  await page.getByRole("button", { name: /use example recipe/i }).click();
  await page.getByLabel(/^Title/).fill("E2E omelette");
  await page.getByRole("button", { name: /upload and create my replay/i }).click();

  await page.waitForURL(/\/jobs\/[a-f0-9]{32}$/);
  await expect(page.getByRole("list", { name: /processing stages/i })).toBeVisible();

  await page.waitForURL(/\/results\/[a-f0-9]{32}$/, { timeout: 150_000 });
  await expect(page.getByText("Mock mode")).toBeVisible();
  const steps = page.getByTestId("step-list").locator("li[data-step]");
  await expect(steps.first()).toBeVisible();
  expect(await steps.count()).toBeGreaterThanOrEqual(3);
  await expect(page.getByTestId("chapter-timeline")).toBeVisible();
  await expect(page.getByTestId("verdict")).toContainText("steps completed");

  // Clicking a step seeks the main player and highlights the card.
  await steps
    .nth(1)
    .getByRole("button", { name: /seek the video/i })
    .click();
  await expect(steps.nth(1)).toHaveAttribute("aria-current", "step");

  // Search finds a step by meaning and answers with a timestamp.
  await page.getByLabel("Search the video").fill("when did I whisk the eggs?");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("list", { name: "Search results" })).toBeVisible();
  await expect(page.getByText(/\d+:\d\d/).first()).toBeVisible();

  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});
