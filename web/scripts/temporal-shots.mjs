// Screenshots of the local Temporal Web UI (localhost:8233) for the blog post.
// usage: node scripts/temporal-shots.mjs <runId>
import { chromium } from "playwright";
const RID = process.argv[2];
const WID = "trailcard-2026-10-10-havo-yell-zion-5b7d";
const out = (n) => new URL("../../docs/images/" + n, import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "light" });
await page.goto("http://localhost:8233/namespaces/default/workflows", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
await page.screenshot({ path: out("temporal-ui-runs.png"), clip: { x: 256, y: 60, width: 1184, height: 760 } });
await page.setViewportSize({ width: 1440, height: 2000 });
await page.goto(`http://localhost:8233/namespaces/default/workflows/${WID}/${RID}/timeline`, { waitUntil: "networkidle" });
await page.waitForTimeout(4000);
const h = page.getByRole("heading", { name: "Timeline" }).last();
const top = (await h.boundingBox()).y - 16;
const bottom = await page.evaluate(() => {
  const els = [...document.querySelectorAll("*")].filter((e) => e.children.length === 0 && /classify_alert|fetch_alerts|publish_card/.test(e.textContent || ""));
  return Math.max(...els.map((e) => e.getBoundingClientRect().bottom));
});
// the Timeline chart only (activity bars with the red attempt-2 retries); skip the Input/Result JSON panels
await page.screenshot({ path: out("temporal-ui-crash.png"), clip: { x: 272, y: top, width: 1140, height: bottom - top + 28 } });
await browser.close();
console.log("ok");
