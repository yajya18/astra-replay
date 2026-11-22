// Drive the running app (default http://localhost:3000, API :8000, mock providers) through the
// demo story and capture it as screencast frames. Then run docs/media/tools/frames_to_video.py
// and compose_demo.py. Needs `make demo`'s placeholder videos in demo/.
// Usage: node scripts/record-demo.mjs [outDir] [webUrl]
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const web = process.argv[3] ?? "http://localhost:3000";
const D = path.resolve(here, "..", "..", "demo", "omelette-skipped-step") + "/";
const out = path.resolve(process.argv[2] ?? "recording");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
const b = await chromium.launch({ args: ["--force-device-scale-factor=1"] });
const ctx = await b.newContext({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1.5,
  colorScheme: "dark",
});
await ctx.addInitScript(() => {
  window.addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div");
    c.style.cssText =
      "position:fixed;z-index:2147483647;pointer-events:none;width:22px;height:22px;border-radius:50%;background:rgba(255,255,255,.9);border:3px solid #4f46e5;box-shadow:0 2px 8px rgba(0,0,0,.5);left:-50px;top:-50px;transform:translate(-50%,-50%);transition:transform .08s";
    document.documentElement.appendChild(c);
    addEventListener(
      "mousemove",
      (e) => {
        c.style.left = e.clientX + "px";
        c.style.top = e.clientY + "px";
      },
      true,
    );
    addEventListener(
      "mousedown",
      () => (c.style.transform = "translate(-50%,-50%) scale(.7)"),
      true,
    );
    addEventListener("mouseup", () => (c.style.transform = "translate(-50%,-50%) scale(1)"), true);
  });
});
const page = await ctx.newPage();
fs.mkdirSync(out + "/frames");
const cdp = await ctx.newCDPSession(page);
const frames = [];
let n = 0;
cdp.on("Page.screencastFrame", async (f) => {
  const i = n++;
  fs.writeFileSync(
    `${out}/frames/f${String(i).padStart(6, "0")}.jpg`,
    Buffer.from(f.data, "base64"),
  );
  frames.push(f.metadata.timestamp);
  cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
});
await cdp.send("Page.startScreencast", {
  format: "jpeg",
  quality: 92,
  maxWidth: 1920,
  maxHeight: 1080,
  everyNthFrame: 1,
});
const marks = {};
const mark = (n) => {
  marks[n] = Date.now() / 1000;
  console.log(n);
};
const wait = (ms) => page.waitForTimeout(ms);
async function go(loc, { click = true, pause = 350 } = {}) {
  await loc.scrollIntoViewIfNeeded();
  const bb = await loc.boundingBox();
  await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2, { steps: 30 });
  await wait(pause);
  if (click) await loc.click();
}
async function scrollBy(px, steps = 40) {
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, px / steps);
    await wait(25);
  }
}
await page.mouse.move(640, 300);
// landing
await page.goto(web + "/", { waitUntil: "load" });
mark("landing");
await wait(5000);
await page.mouse.move(1000, 200, { steps: 40 });
await wait(2500);
// upload
mark("upload");
await page.locator('input[type="file"]').setInputFiles(D + "placeholder.mp4");
await wait(1800);
await go(page.getByRole("button", { name: /use example recipe/i }));
await wait(1800);
await go(page.getByLabel(/^Title/), { pause: 200 });
await page.getByLabel(/^Title/).fill("");
await page.getByLabel(/^Title/).pressSequentially("Sunday omelette", { delay: 70 });
await wait(900);
await go(page.getByRole("button", { name: /upload and create my replay/i }), { pause: 600 });
await page.waitForURL(/\/jobs\//);
mark("processing");
await wait(2000);
await page.waitForURL(/\/results\//, { timeout: 170000 });
mark("results");
await page.getByTestId("step-list").waitFor();
await wait(3500);
// player + seek
mark("player");
const video = page.locator("video").first();
await go(
  page
    .locator("li[data-step]")
    .nth(2)
    .getByRole("button", { name: /seek the video/i }),
);
await wait(2500);
await go(
  page
    .locator("li[data-step]")
    .nth(4)
    .getByRole("button", { name: /seek the video/i }),
);
await wait(2500);
await go(page.getByTestId("chapter-timeline").locator("button,a").first());
await wait(1500);
await video.evaluate((v) => {
  v.muted = true;
  return v.play();
});
await wait(3000);
mark("clip");
await go(page.locator("li[data-step]").nth(1).getByRole("button", { name: /clip/i }));
await page.getByRole("dialog").waitFor();
await wait(4000);
await page.keyboard.press("Escape");
await wait(800);
// search
mark("search");
const box = page.getByRole("textbox", { name: "Search the video" });
await go(box);
await box.pressSequentially("when did I pour the eggs?", { delay: 60 });
await wait(500);
await page.getByRole("button", { name: "Search" }).click();
await page.getByRole("list", { name: "Search results" }).waitFor();
await wait(4500);
// procedure
mark("procedure");
await page.getByTestId("verdict").scrollIntoViewIfNeeded();
await scrollBy(-120, 20);
await wait(5000);
// reel
mark("reel");
const reel = page.getByRole("heading", { name: /highlight reel/i });
await reel.scrollIntoViewIfNeeded();
await wait(800);
const rv = page.locator("video:visible").last();
await rv.scrollIntoViewIfNeeded();
await rv.evaluate((v) => {
  v.muted = true;
  return v.play();
});
await wait(6000);
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
await wait(1500);
await go(page.getByRole("button", { name: /export/i }));
await wait(3000);
await page.keyboard.press("Escape");
await page.mouse.move(600, 400, { steps: 15 });
await wait(500);
// hood
mark("hood");
const hood = page
  .locator("summary, button")
  .filter({ hasText: /under the hood/i })
  .first();
await go(hood);
await wait(1000);
await scrollBy(500, 30);
await wait(4500);
// xr
mark("xr");
await page.evaluate(() => window.scrollTo({ top: 0 }));
await go(page.getByRole("link", { name: /view in xr/i }));
await page.waitForURL(/\/xr/);
await wait(9000);
mark("end");
await cdp.send("Page.stopScreencast");
fs.writeFileSync(out + "/marks.json", JSON.stringify({ marks, frames }, null, 0));
await ctx.close();
await b.close();
console.log("done");
