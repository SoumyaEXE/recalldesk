/**
 * Blog screenshot set -> ../docs/blog-shots/ (2x device scale, light theme).
 *
 *   node scripts/blog-shots.mjs                 # web on :3000 (pointing at the live API on :8000)
 *   node scripts/blog-shots.mjs --only web      # just the dashboard shots
 *   node scripts/blog-shots.mjs --only label    # just the label UI (LABEL_BASE, default http://localhost:8790)
 *   node scripts/blog-shots.mjs --only temporal # just the Temporal Web UI (TEMPORAL_UI, default http://localhost:8233)
 *
 * Env: BASE (web), LABEL_BASE, TEMPORAL_UI, CRASH_WF (workflow id substring for the crash run, default "crashdemo").
 * Read-only by design: it never presses a label key in the label UI and never submits a correction.
 * The /check shot does start one InventoryCheckWorkflow for the UI's demo shop (shop_id demo-shop).
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE ?? "http://localhost:3000";
const LABEL_BASE = process.env.LABEL_BASE ?? "http://localhost:8790";
const TUI = process.env.TEMPORAL_UI ?? "http://localhost:8233";
const CRASH = process.env.CRASH_WF ?? "crashdemo";
const OUT = path.resolve(here, "../../docs/blog-shots");
const only = process.argv.includes("--only") ? process.argv[process.argv.indexOf("--only") + 1] : null;
const issues = [];
const wrote = [];

fs.mkdirSync(OUT, { recursive: true });

async function settle(page, ms = 1200) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(ms);
}

async function ctxFor(browser, width, height) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 2, colorScheme: "light" });
  await ctx.addInitScript(() => {
    try {
      localStorage.setItem("boardui:theme", "light");
    } catch {}
  });
  return ctx;
}

async function save(target, name, opts = {}) {
  const p = path.join(OUT, `${name}.png`);
  await target.screenshot({ path: p, animations: "disabled", ...opts });
  wrote.push(name);
  console.log(`  ${name}.png`);
}

/** Screenshot an element, clipped to at most maxH css px tall. */
async function shootEl(page, locator, name, { pad = 0, maxH = 1800 } = {}) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const box = await locator.boundingBox();
  if (!box) {
    issues.push(`${name}: element not found`);
    return;
  }
  const sy = await page.evaluate(() => window.scrollY);
  const clip = { x: Math.max(0, box.x - pad), y: Math.max(0, box.y + sy - pad), width: box.width + 2 * pad, height: Math.min(box.height + 2 * pad, maxH) };
  await save(page, name, { fullPage: true, clip });
}

async function liveChip(page, name) {
  const txt = await page.locator("body").innerText();
  if (/Demo data/i.test(txt)) issues.push(`${name}: page shows "Demo data" (API down or placeholder payload)`);
}

async function webShots(browser) {
  console.log("dashboard ->", BASE);
  // 1440 light
  let ctx = await ctxFor(browser, 1440, 1000);
  let page = await ctx.newPage();
  page.on("pageerror", (e) => issues.push(`pageerror: ${e.message}`));

  await page.goto(BASE + "/");
  await settle(page, 1500);
  await liveChip(page, "home");
  const card = page.locator("article[aria-label^='Recall check for']").first();
  await shootEl(page, card, "home-card-1440", { pad: 16, maxH: 3000 });
  await shootEl(page, card, "home-card-1440-top", { pad: 16, maxH: 900 });

  await page.goto(BASE + "/check");
  await settle(page, 800);
  await page.getByRole("button", { name: "Use sample" }).click();
  await page.getByRole("button", { name: /^Check \d+ items?$/ }).click();
  await page.getByRole("article").first().waitFor({ timeout: 120_000 }).catch(() => issues.push("check run did not finish"));
  await page.waitForTimeout(1200);
  await shootEl(page, page.locator("main#main"), "check-done-1440", { maxH: 2200 });
  const steps = page.locator("ol[aria-label='Workflow steps']").first();
  if (await steps.count()) await shootEl(page, steps, "check-steps-1440", { pad: 20 });

  await page.goto(BASE + "/recalls");
  await settle(page);
  // a recall whose identifier is physically hidden (the post's hook): Woodure 26658, "engraved on the underside
  // of the bottom step". RECALL_SHOT overrides; falls back to the first row.
  const rq = process.env.RECALL_SHOT ?? "26658";
  const search = page.getByPlaceholder(/Brand, product, model/);
  if (await search.count()) {
    await search.fill(rq);
    await page.waitForTimeout(500);
  }
  await page.locator("button[aria-label^='Expand recall']").first().click();
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(600);
  await shootEl(page, page.locator("main#main"), "recalls-expanded-1440", { maxH: 1700 });

  for (const [name, url, maxH] of [["scan-1440", "/scan", 1700], ["lab-1440", "/lab", 2600]]) {
    await page.goto(BASE + url);
    await settle(page, 1500);
    await liveChip(page, name);
    await shootEl(page, page.locator("main#main"), name, { maxH });
  }

  await page.goto(BASE + "/runs");
  await settle(page, 1500);
  const crashBtn = page.locator("ul[aria-label='Workflow runs'] button", { hasText: CRASH }).first();
  if (await crashBtn.count()) {
    await crashBtn.click();
    await page.waitForTimeout(800);
  } else issues.push(`runs: no run matching "${CRASH}" in the list`);
  await shootEl(page, page.locator("main#main"), "runs-crash-1440", { maxH: 2000 });

  await page.goto(BASE + "/about");
  await settle(page);
  await shootEl(page, page.locator("section[aria-labelledby='who-pays']"), "about-pricing-1440", { pad: 24 });
  await ctx.close();

  // 390 mobile: the card
  ctx = await ctxFor(browser, 390, 844);
  page = await ctx.newPage();
  await page.goto(BASE + "/");
  await settle(page, 1500);
  await shootEl(page, page.locator("article[aria-label^='Recall check for']").first(), "home-card-390", { pad: 8, maxH: 4000 });
  await save(page, "home-390-viewport");
  await ctx.close();
}

async function labelShots(browser) {
  console.log("label UI ->", LABEL_BASE);
  const ctx = await ctxFor(browser, 1440, 1000);
  const page = await ctx.newPage();
  // read-only: block every non-GET request to the label server, so nothing can be written
  await page.route(`${LABEL_BASE}/**`, (r) => (r.request().method() === "GET" ? r.continue() : r.abort()));
  try {
    await page.goto(LABEL_BASE + "/", { waitUntil: "networkidle", timeout: 20_000 });
    await page.waitForTimeout(1500);
    await save(page, "label-ui-1440", { fullPage: false });
    await save(page, "label-ui-1440-full", { fullPage: true });
  } catch (e) {
    issues.push(`label UI: ${e.message.split("\n")[0]}`);
  }
  await ctx.close();
}

async function temporalShots(browser) {
  console.log("Temporal UI ->", TUI);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "light" });
  const page = await ctx.newPage();
  try {
    await page.goto(`${TUI}/namespaces/default/workflows`, { waitUntil: "networkidle", timeout: 30_000 });
    await page.waitForTimeout(2500);
    await save(page, "temporal-workflows", { fullPage: false });
    const link = page.locator(`a[href*="${CRASH}"]`).first();
    if (!(await link.count())) {
      issues.push(`Temporal UI: no workflow link matching "${CRASH}"`);
    } else {
      const href = await link.getAttribute("href");
      const base = new URL(href, TUI).toString().replace(/\/(history|timeline|summary|workers|pending-activities|stack-trace|queries|call-stack|relationships)\/?$/, "");
      await page.setViewportSize({ width: 1440, height: 1400 });
      await page.goto(base + "/timeline", { waitUntil: "networkidle", timeout: 30_000 }).catch(() => {});
      await page.waitForTimeout(4000);
      await save(page, "temporal-crash-timeline", { fullPage: false });
      // the Timeline chart only (activity bars incl. the retried attempts), not the Input/Result JSON panels
      const h = page.getByRole("heading", { name: "Timeline" }).last();
      if (await h.count()) {
        await h.scrollIntoViewIfNeeded();
        const sy = await page.evaluate(() => window.scrollY);
        const b = await h.boundingBox();
        const full = await page.evaluate(() => document.documentElement.scrollHeight);
        const y = b.y + sy - 12;
        await save(page, "temporal-crash-timeline-chart", { fullPage: true, clip: { x: 260, y, width: 1180, height: Math.min(1500, full - y) } });
      }
      await page.goto(base + "/history", { waitUntil: "networkidle", timeout: 30_000 }).catch(() => {});
      await page.waitForTimeout(3000);
      await save(page, "temporal-crash-history", { fullPage: false });
    }
  } catch (e) {
    issues.push(`Temporal UI: ${e.message.split("\n")[0]}`);
  }
  await ctx.close();
}

const browser = await chromium.launch();
try {
  if (!only || only === "web") await webShots(browser);
  if (!only || only === "label") await labelShots(browser);
  if (!only || only === "temporal") await temporalShots(browser);
} finally {
  await browser.close();
}
console.log(`wrote ${wrote.length} image(s) to ${OUT}`);
console.log(issues.length ? `issues:\n  ${issues.join("\n  ")}` : "no issues");
