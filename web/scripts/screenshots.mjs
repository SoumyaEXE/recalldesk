/**
 * Screenshot generator.
 *
 *   npm run build && npx next start -p 3000     (API on :8000 optional)
 *   node scripts/screenshots.mjs                → ../docs/screenshots (every page, 1440/390, light/dark,
 *                                                 plus the print view, a finished /check run and an expanded recall)
 *
 * Env: BASE (default http://localhost:3000), OFFLINE=1 to block the API and render from fixtures,
 *      CLEAN=1 to hide the demo-data chip (?clean=1).
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE ?? "http://localhost:3000";
const OUT = path.resolve(here, "../../docs/screenshots");
const Q = process.env.CLEAN === "1" ? "?clean=1" : "";
const errors = [];

const PAGES = [
  ["home", "/"],
  ["check", "/check"],
  ["recalls", "/recalls"],
  ["scan", "/scan"],
  ["lab", "/lab"],
  ["runs", "/runs"],
  ["about", "/about"],
];

async function newContext(browser, { width, height, dsf, theme }) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: dsf });
  await ctx.addInitScript((t) => {
    try {
      localStorage.setItem("boardui:theme", t);
    } catch {}
  }, theme);
  if (process.env.OFFLINE === "1") await ctx.route(/localhost:8000/, (r) => r.abort());
  return ctx;
}

async function settle(page, ms = 1200) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(ms);
}

async function shoot(page, name, width, theme) {
  const sw = await page.evaluate(() => document.documentElement.scrollWidth);
  if (sw > width) errors.push(`horizontal overflow: ${name} ${theme} ${width} (${sw}px)`);
  await page.screenshot({ path: path.join(OUT, `${name}-${width}-${theme}.png`), fullPage: true });
}

const browser = await chromium.launch();
try {
  fs.mkdirSync(OUT, { recursive: true });
  for (const theme of ["light", "dark"]) {
    for (const width of [1440, 390]) {
      const ctx = await newContext(browser, { width, height: width > 500 ? 900 : 844, dsf: width > 500 ? 1 : 2, theme });
      const page = await ctx.newPage();
      page.on("pageerror", (e) => errors.push(`${theme} ${width}: ${e.message}`));
      page.on("console", (m) => m.type() === "error" && !/localhost:8000|ERR_CONNECTION|Failed to load resource/.test(m.text()) && errors.push(`console ${theme} ${width}: ${m.text()}`));
      for (const [name, url] of PAGES) {
        await page.goto(BASE + url + Q);
        await settle(page);
        await shoot(page, name, width, theme);
      }

      // /check with the sample inventory, run to completion.
      await page.goto(BASE + "/check" + Q);
      await settle(page, 600);
      await page.getByRole("button", { name: "Use sample" }).click();
      await page.getByRole("button", { name: /^Check \d+ items?$/ }).click();
      await page.getByRole("article").first().waitFor({ timeout: 30_000 }).catch(() => errors.push(`check run did not finish (${theme} ${width})`));
      await page.waitForTimeout(700);
      await shoot(page, "check-done", width, theme);

      // /recalls with the first row expanded.
      await page.goto(BASE + "/recalls" + Q);
      await settle(page);
      await page.locator("button[aria-label^='Expand recall']").first().click();
      await page.waitForTimeout(400);
      await shoot(page, "recalls-expanded", width, theme);
      await ctx.close();
    }
  }

  // Print emulation of this week's card (Letter-ish viewport).
  const ctx = await newContext(browser, { width: 816, height: 1056, dsf: 2, theme: "light" });
  const page = await ctx.newPage();
  await page.goto(BASE + "/" + Q);
  await settle(page);
  await page.emulateMedia({ media: "print" });
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, "home-print.png"), fullPage: true });
  await page.pdf({ path: path.join(OUT, "home-print.pdf"), format: "Letter", printBackground: true });
  const pdfPages = (fs.readFileSync(path.join(OUT, "home-print.pdf"), "latin1").match(/\/Type\s*\/Page[^s]/g) ?? []).length;
  console.log(`home-print.pdf: ${pdfPages} page(s)`);
  if (pdfPages !== 1) errors.push(`print view is ${pdfPages} pages, expected 1`);
  await ctx.close();
  console.log(`wrote ${OUT}`);
} finally {
  await browser.close();
}
console.log(errors.length ? `issues:\n${errors.join("\n")}` : "no issues");
