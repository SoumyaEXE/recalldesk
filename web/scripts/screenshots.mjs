/**
 * Screenshot generator.
 *
 *   npm run build && npx next start -p 3000     (API on :8000 optional)
 *   node scripts/screenshots.mjs                → ../docs/screenshots (every page, 1440/390, light/dark,
 *                                                 plus the print view, a finished inventory check, an open item
 *                                                 drawer and an open recall drawer)
 *
 * Env: BASE (default http://localhost:3000), OFFLINE=1 to block the API and render from fixtures,
 *      CLEAN=1 to hide the demo-data chip (?clean=1).
 *
 * Legacy names kept for the blog draft: home-* (Overview), check-done-* (inventory check), scan-* (eBay monitor).
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE ?? "http://localhost:3000";
const OUT = path.resolve(here, "../../docs/screenshots");
const Q = process.env.CLEAN === "1" ? "?clean=1" : "";
const q = (url) => (Q ? `${url}${url.includes("?") ? "&" : "?"}clean=1` : url);
const errors = [];

const PAGES = [
  ["home", "/"],
  ["inventory", "/inventory"],
  ["recalls", "/recalls"],
  ["ebay", "/ebay"],
  ["cards", "/cards"],
  ["memory", "/memory"],
  ["runs", "/runs"],
  ["lab", "/lab"],
  ["services", "/settings/services"],
  ["billing", "/settings/billing"],
  ["team", "/settings/team"],
  ["about", "/about"],
];
const ALIAS = { ebay: "scan" };

async function newContext(browser, { width, height, dsf, theme }) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: dsf });
  await ctx.addInitScript((t) => {
    try {
      localStorage.setItem("boardui:theme", t);
      localStorage.removeItem("recalldesk:sim-workflows");
    } catch {}
  }, theme);
  if (process.env.OFFLINE === "1") await ctx.route(/localhost:8000/, (r) => r.abort());
  return ctx;
}

/** Wait for every <img> to finish (CPSC photos can be 2 MB+), capped. */
async function imagesDone(page, ms = 25_000) {
  await page
    .waitForFunction(() => [...document.images].every((i) => i.complete), null, { timeout: ms })
    .catch(() => {});
}

async function settle(page, ms = 1400) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await imagesDone(page);
  await page.waitForTimeout(ms);
}

async function shoot(page, name, width, theme, opts = { fullPage: true }) {
  const sw = await page.evaluate(() => document.documentElement.scrollWidth);
  if (sw > width) errors.push(`horizontal overflow: ${name} ${theme} ${width} (${sw}px)`);
  const file = path.join(OUT, `${name}-${width}-${theme}.png`);
  await page.screenshot({ path: file, animations: "disabled", ...opts });
  if (ALIAS[name]) fs.copyFileSync(file, path.join(OUT, `${ALIAS[name]}-${width}-${theme}.png`));
}

const browser = await chromium.launch();
try {
  fs.mkdirSync(OUT, { recursive: true });
  for (const theme of ["light", "dark"]) {
    for (const width of [1440, 390]) {
      const ctx = await newContext(browser, { width, height: width > 500 ? 900 : 844, dsf: width > 500 ? 1 : 2, theme });
      const page = await ctx.newPage();
      page.on("pageerror", (e) => errors.push(`${theme} ${width}: ${e.message}`));
      page.on("console", (m) => m.type() === "error" && !/localhost:8000|ERR_CONNECTION|Failed to load resource|ERR_BLOCKED_BY_ORB/.test(m.text()) && errors.push(`console ${theme} ${width}: ${m.text()}`));
      for (const [name, url] of PAGES) {
        await page.goto(BASE + q(url));
        await settle(page);
        await shoot(page, name, width, theme);
      }

      // Inventory: paste the sample list and run InventoryCheckWorkflow to completion.
      await page.goto(BASE + q("/inventory?new=1"));
      await settle(page, 600);
      await page.getByRole("button", { name: "Use sample" }).click();
      await page.getByRole("button", { name: /^Check \d+ items?$/ }).click();
      await page.getByRole("heading", { name: "Check complete" }).waitFor({ timeout: 60_000 }).catch(() => errors.push(`check run did not finish (${theme} ${width})`));
      await page.waitForTimeout(900);
      await shoot(page, "check-done", width, theme);

      // Inventory: an item drawer (item vs recall side by side).
      await page.goto(BASE + q("/inventory"));
      await settle(page);
      await page.locator("main button[aria-label^='Open ']:visible").first().click();
      await page.waitForTimeout(700);
      await imagesDone(page);
      await shoot(page, "inventory-drawer", width, theme, { fullPage: false });

      // Recalls: the drawer for a recall whose model number is engraved underneath (Woodure 26658).
      await page.goto(BASE + q("/recalls?open=26658"));
      await settle(page, 900);
      await shoot(page, "recalls-expanded", width, theme, { fullPage: false });
      await ctx.close();
    }
  }

  // Print emulation of this week's card (Letter-ish viewport).
  const ctx = await newContext(browser, { width: 816, height: 1056, dsf: 2, theme: "light" });
  const page = await ctx.newPage();
  await page.goto(BASE + q("/cards"));
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
