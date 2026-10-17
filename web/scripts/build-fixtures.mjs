/**
 * Builds web/public/fixtures/*.json from REAL CPSC recall data.
 *
 *   node scripts/build-fixtures.mjs                 # fetches CPSC (UTF-8) since 2026-07-18
 *   node scripts/build-fixtures.mjs path/to.json    # or reads a saved CPSC response
 *
 * Recalls are real. Specs are heuristic (+ hand-checked overrides for the
 * children's recalls on the demo card). Everything that is NOT real — eBay
 * listings, scan counts, eval numbers, runs, memories, the demo shop's
 * inventory — is marked `"placeholder": true` and the UI labels it.
 *
 * When the backend writes shared/fixtures/*.json, copy those over these.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(here, "../public/fixtures");
fs.mkdirSync(OUT, { recursive: true });

const SINCE = "2026-07-18";
let raw;
if (process.argv[2]) {
  raw = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
} else {
  const res = await fetch(`https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallDateStart=${SINCE}`);
  const buf = Buffer.from(await res.arrayBuffer());
  raw = JSON.parse(new TextDecoder("utf-8").decode(buf));
}

/* ---------- deterministic PRNG so fixtures are stable ---------------------- */
function rng(seed) {
  let s = 0;
  for (const c of String(seed)) s = (s * 31 + c.charCodeAt(0)) >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ---------- normalization -------------------------------------------------- */
const clean = (s) => (s ?? "").replace(/[™®]/g, "").replace(/\s+/g, " ").trim();
const MONTHS = { january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8, september: 9, october: 10, november: 11, december: 12 };
const ym = (m, y) => `${y}-${String(MONTHS[m.toLowerCase()]).padStart(2, "0")}`;

const CHILD_RE = /\b(baby|babies|infant|toddler|children|children’s|children's|kid|kids|youth|toy|toys|teeth|teether|teething|crib|bassinet|bedside sleepers?|play ?yard|stroller|bib|bibs|rattle|walker|walkers|jumper|swing seat|doll|montessori|squishy|bath seat|loungers?|tower stool|busy board)\b/i;

const ID_STOP = new Set(["ASTM", "CPSC", "USB", "LED", "UPC", "SKU", "US", "USA", "N95", "CO2"]);
function regexIds(text) {
  const ids = new Set();
  const kw = /\b(?:model|item|style|sku|lot|batch|date)\s*(?:no\.?|nos\.?|number|numbers|#|code|codes)?\s*[:"“]*\s*([A-Za-z0-9][A-Za-z0-9\-./]{2,})/gi;
  for (const m of text.matchAll(kw)) {
    const v = m[1].replace(/[.,;:"”]+$/, "");
    if (/\d/.test(v) && v.length >= 3 && !/^(19|20)\d\d$/.test(v) && !/[/]|-$/.test(v)) ids.add(v);
  }
  const mixed = /\b(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9][A-Z0-9-]{3,}\b/g;
  for (const m of text.matchAll(mixed)) if (!ID_STOP.has(m[0]) && !/-$/.test(m[0])) ids.add(m[0]);
  return [...ids].slice(0, 12);
}

function soldWindow(text) {
  const t = clean(text);
  let m = t.match(/from (\w+) (\d{4}) through (\w+) (\d{4})/i);
  if (m && MONTHS[m[1].toLowerCase()] && MONTHS[m[3].toLowerCase()]) return [ym(m[1], m[2]), ym(m[3], m[4])];
  m = t.match(/\bin (\w+) (\d{4})/i);
  if (m && MONTHS[m[1].toLowerCase()]) return [ym(m[1], m[2]), ym(m[1], m[2])];
  return [null, null];
}

function brandOf(r) {
  const title = clean(r.Title);
  const m = title.match(/^(.*?)\s+(?:Recalls|Reannounces|Expands)\b/);
  if (m) return m[1].replace(/,? of USA$/i, "").replace(/\s+(Inc\.?|LLC|Corporation|Company|Corp\.?|USA|U\.S\.|America|Americas|North America|Direct)$/i, "").trim();
  const firm = [...r.Manufacturers, ...r.Importers, ...r.Distributors][0]?.Name;
  if (firm) return clean(firm.split(",")[0]);
  const lead = title.match(/^(.*?)\s+Recalled\b/);
  return lead ? lead[1] : "Unknown";
}

function hazardShort(r) {
  const t = clean(r.Title);
  const m = t.match(/Due to (?:Risk of )?(?:Serious )?(?:Risk of )?(?:Injury or Death |Injury |Serious Injury )?(?:to Children )?(?:from |and Death from )?(.*?)(?:;|$)/i);
  let h = m ? m[1] : clean(r.Hazards[0]?.Name).split(".")[0];
  h = h.replace(/^Risk of /i, "").replace(/ Hazards?$/i, " hazard");
  return h.charAt(0).toUpperCase() + h.slice(1);
}

function lookFor(desc) {
  const s = clean(desc)
    .split(/(?<=\.)\s+/)
    .filter((x) => /(located|printed|found|label|sticker|tag|embossed|stamped|imprinted|underside|bottom of)/i.test(x));
  return s.slice(0, 2).join(" ") || null;
}

function keyFeatures(desc) {
  const sents = clean(desc).split(/(?<=\.)\s+/).slice(1, 4);
  return sents
    .filter((x) => !/(located|printed on a label|recall involves)/i.test(x))
    .map((x) => (x.length > 110 ? x.slice(0, 107).replace(/\s+\S*$/, "") + "…" : x))
    .slice(0, 3);
}

/* Hand-checked specs for the recalls the demo card leans on. */
const OVERRIDES = {
  27027: { is_childrens: true, brand: "Papablic", product_type: "convertible bedside sleeper / play yard", product_name: "Papablic Convertible Bedside Sleeper", model_numbers: ["PAPA03001AI"], colors: ["gray exterior", "stars-and-moon interior"], key_features: ["Works as bassinet and play yard", "\"Papablic\" stitched in white on front panel"], look_for: "Label sewn to the bassinet's interior fabric, under the mattress pad: model PAPA03001AI.", hazard_short: "Mattress can shift and trap a baby; latch can fail and collapse", remedy_short: "Stop using; refund from Papablic after destroying it" },
  27028: { brand: "Primark", product_type: "children's coin purse", product_name: "101 Dalmatians Faux Leather Coin Purse", model_numbers: ["2595301"], colors: ["black"], key_features: ["Dalmatian picture and \"101 Dalmatians\" on front"], look_for: "Product tag on the zip puller: model no. 2595301.", hazard_short: "Phthalate levels above the children's limit", remedy_short: "Return to Primark for a refund" },
  27018: { brand: "ONTHEWEI", product_type: "infant bath seat", product_name: "ONTHEWEI Baby Bath Seat", model_numbers: ["MY002"], colors: ["gray", "pink", "blue", "mist green"], key_features: ["Detachable restraint arms", "Suction cups underneath"], look_for: "Label on the back of the seat: \"Model No: MY002\" and a 2026 manufacture date.", hazard_short: "Tips over in the tub; drowning risk", remedy_short: "Stop using; refund after marking it RECALLED and cutting it" },
  26739: { brand: "Skip Hop", product_type: "silicone teether", product_name: "Baby Sesame Street Elmo Silicone Teether", model_numbers: ["9R263210"], colors: ["red/orange/white Elmo face", "blue key", "multicolor crayon box"], key_features: ["Elmo-face teether with key and fabric crayon box"], look_for: "Red Skip Hop tag on the side of the crayon box: model 9R263210.", hazard_short: "Black eyes detach when frozen; choking", remedy_short: "Stop using; gift-card refund at skiphoprecall.com" },
  26719: { brand: "HABA", product_type: "rattle / teething toy", product_name: "HABA Rainbow Rattle Grasping and Teething Toy", model_numbers: ["2012261001"], other_identifiers: ["batch 0925"], colors: ["natural wood", "rainbow plastic rings"], key_features: ["Wooden hemispheres on an elastic cord", "Plastic rattling rings"], look_for: "Batch code 0925 in black on a wooden hemisphere; item no. 2012261001 above the barcode on the backer card.", hazard_short: "Cord knot can come undone; small parts choking", remedy_short: "Stop using; refund from HABA USA" },
  26780: { brand: "Melissa & Doug", product_type: "fire truck activity board toy", product_name: "Lights and Sound Fire Truck", model_numbers: [], other_identifiers: ["OET 25100", "OET 25150", "OET 26064", "date wheels 25 + 4/5", "date wheels 26 + 3"], colors: ["red", "white ladder", "black wheels"], key_features: ["Busy-board activities with lights and sounds", "Black plastic 'fire hose' connector"], look_for: "Bottom of the battery box: date wheels at 25 + 4 or 5, or 26 + 3. Packaging: OET 25100, 25150 or 26064.", hazard_short: "Fire-hose port detaches; choking", remedy_short: "Stop using; free replacement or refund" },
  26798: { is_childrens: true, brand: "Love to Dream", product_type: "portable sleep machine", product_name: "Love to Dream Portable Sleep Machine", model_numbers: ["LTD-SM23"], other_identifiers: ["date code 7W15TN"], colors: ["brown handle"], key_features: ["Sound machine with nightlight", "USB charging cable"], look_for: "Side of the machine (or back of the box): model LTD-SM23 AND date code 7W15TN. Both must match.", hazard_short: "Battery can overheat; fire and burns", remedy_short: "Stop using; refund at lovetodream.com/recall" },
  26688: { is_childrens: true, brand: "Taleco Gear", product_type: "baby jumper / swing", product_name: "G Taleco Gear Baby Jumper, Baby Swing, 2-in-1 Jumper & Swing", model_numbers: ["jumper-01", "swing-1"], colors: ["black", "white", "gray", "pink", "blue", "green"], key_features: ["Hanging seat with restraint straps"], look_for: "Wash/care label sewn into the fabric seat cover: jumper-01 or swing-1.", hazard_short: "Can tip; straps and seat openings can strangle", remedy_short: "Stop using; refund after destroying it" },
  26651: { is_childrens: true, brand: "HARPPA", product_type: "toddler tower stool", product_name: "HARPPA Nordi Foldable Toddler Tower", model_numbers: ["HANS0002"], colors: ["white", "black", "blue", "natural wood"], key_features: ["Foldable learning tower, about 38.6 in tall"], look_for: "Label on the underside of the platform: \"MODEL No.: HANS0002\".", hazard_short: "Can collapse or tip; torso entrapment", remedy_short: "Free repair kit from HARPPA" },
  27024: { brand: "Scotch (3M)", product_type: "thermal laminator", product_name: "Scotch Thermal Laminator", model_numbers: ["TL1302Z"], colors: ["light gray/white"], key_features: ["13-inch slot", "Carrying handle on right side"], look_for: "Sticker on the bottom of the laminator: TL1302Z.", hazard_short: "Overheats; fire hazard", remedy_short: "Stop using; refund from 3M" },
};

const recalls = raw.map((r) => {
  const text = `${r.Description} ${r.Products.map((p) => `${p.Name} ${p.Model}`).join(" ")}`;
  const ids = regexIds(text);
  const isChild = CHILD_RE.test(`${r.Title} ${r.Products.map((p) => p.Type).join(" ")}`) && !/\badult\b/i.test(r.Title);
  const [from, to] = soldWindow(r.Retailers.map((x) => x.Name).join(" "));
  const brand = brandOf(r);
  const pname = clean(r.Products[0]?.Name) || clean(r.Title);
  const ptype = (clean(r.Products[0]?.Type) || pname).toLowerCase();
  const remedyOpts = r.RemedyOptions.map((o) => o.Option).filter(Boolean);
  const spec = {
    recall_number: r.RecallNumber,
    brand,
    product_type: ptype,
    product_name: pname,
    model_numbers: ids.filter((x) => !/^\d{11,13}$/.test(x)).slice(0, 8),
    upcs: r.ProductUPCs.map((u) => u.UPC ?? u).filter(Boolean),
    other_identifiers: [],
    sold_from: from,
    sold_to: to,
    colors: [],
    key_features: keyFeatures(r.Description),
    not_included: [],
    search_queries: [`${brand} ${pname}`.slice(0, 80), ...(ids[0] ? [`${brand} ${ids[0]}`] : [])],
    is_childrens: isChild,
    hazard_short: hazardShort(r),
    remedy_short: remedyOpts.length ? `Stop using; ${remedyOpts.join(" / ").toLowerCase()}` : "Stop using; contact the firm",
    look_for: lookFor(r.Description),
    spec_source: "heuristic",
    ...(OVERRIDES[r.RecallNumber] ? { ...OVERRIDES[r.RecallNumber], spec_source: "hand-checked" } : {}),
  };
  return {
    recall_number: r.RecallNumber,
    recall_id: r.RecallID,
    recall_date: r.RecallDate.slice(0, 10),
    title: clean(r.Title),
    description: clean(r.Description),
    url: r.URL,
    product_names: r.Products.map((p) => clean(p.Name)).filter(Boolean),
    units: clean(r.Products[0]?.NumberOfUnits) || null,
    hazards: r.Hazards.map((h) => clean(h.Name)),
    remedies: r.Remedies.map((h) => clean(h.Name)),
    remedy_options: remedyOpts,
    retailers: r.Retailers.map((x) => clean(x.Name)),
    manufacturers: r.Manufacturers.map((x) => clean(x.Name)),
    importers: r.Importers.map((x) => clean(x.Name)),
    images: r.Images.map((i) => i.URL),
    upcs: spec.upcs,
    regex_ids: ids,
    is_childrens: spec.is_childrens,
    corpus: spec.is_childrens ? ["A", "B"] : ["A"],
    spec,
  };
});
recalls.sort((a, b) => b.recall_date.localeCompare(a.recall_date) || a.recall_number.localeCompare(b.recall_number));

/* ---------- placeholder eBay scan ------------------------------------------ */
const CONDITIONS = ["Pre-Owned", "Pre-Owned", "Pre-Owned", "New (Other)", "Open box", "Brand New"];
const hash = (seed) => "s_" + Math.floor(rng(seed)() * 0xffffff).toString(16).padStart(6, "0");
const ebaySearch = (q) => `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(q)}`;

/** Synthetic listing titles per recall: [title, verdict, identifiers_found, reason]. */
const LISTINGS = {
  27027: [
    ["Papablic Bedside Sleeper Bassinet Play Yard Gray Stars Moon PAPA03001AI", "match", ["PAPA03001AI"], "Papablic bedside sleeper, recalled model PAPA03001AI in the title."],
    ["Papablic 3-in-1 Bassinet Bedside Sleeper Gray — gently used", "check", [], "Same Papablic bedside sleeper line; model label not shown. Check the label under the mattress pad."],
    ["Bedside Sleeper Bassinet Gray Moon & Stars Print, No Brand", "check", [], "Matches the recalled pattern and colour but no brand or model visible."],
    ["Papablic Bassinet Mattress Pad Replacement Sheet", "no_match", [], "Accessory only (sheet), not the sleeper."],
  ],
  26739: [
    ["Skip Hop Sesame Street Elmo Silicone Teether w/ Crayon Box NWT", "match", ["Elmo Silicone Teether"], "Skip Hop Elmo silicone teether; recall covers all units of this product."],
    ["Skip Hop Baby Teether Lot — Elmo, Cookie Monster", "check", [], "Bundle includes an Elmo teether; can't tell if it's the silicone face teether. Check the red tag for 9R263210."],
    ["Skip Hop Zoo Teether Owl Silicone", "no_match", [], "Different Skip Hop product line (Zoo), not the Elmo teether."],
  ],
  26688: [
    ["G Taleco Gear Baby Jumper Bouncer Gray jumper-01", "match", ["jumper-01"], "Taleco Gear baby jumper, recalled model jumper-01 named."],
    ["Taleco Gear 2-in-1 Baby Swing & Jumper Pink", "match", ["2-in-1 Jumper & Swing"], "Taleco Gear 2-in-1 jumper & swing; all listed units recalled."],
    ["Baby Door Jumper Universal Clamp", "no_match", [], "Different, unbranded product."],
  ],
  26780: [
    ["Melissa & Doug Lights and Sound Fire Truck Activity Board", "check", [], "Same toy; recall is limited to certain date wheels. Check the battery box."],
    ["Melissa & Doug Fire Truck Busy Board OET 25150 Target", "match", ["OET 25150"], "Recalled date code OET 25150 named in the title."],
    ["Melissa & Doug Wooden Fire Truck Puzzle", "no_match", [], "Different Melissa & Doug product (wooden puzzle)."],
  ],
  26719: [
    ["HABA Rainbow Rattle Teething Toy Wood — Batch 0925", "match", ["0925"], "HABA Rainbow Rattle with recalled batch code 0925."],
    ["HABA Rainbow Rattle Grasping Toy, Used", "check", [], "Same HABA rattle; batch code not shown."],
  ],
  26798: [
    ["Love to Dream Portable Sleep Machine LTD-SM23 Night Light", "check", ["LTD-SM23"], "Model LTD-SM23 named, but recall also needs date code 7W15TN."],
    ["Love To Dream Swaddle Up Original Size M", "no_match", [], "Different Love to Dream product (swaddle)."],
  ],
  27018: [
    ["ONTHEWEI Baby Bath Seat Suction Cups Gray MY002", "match", ["MY002"], "ONTHEWEI bath seat, recalled model MY002."],
    ["Baby Bath Seat with Suction Cups & Backrest, Mist Green", "check", [], "Matches the recalled design and colour; brand not shown."],
  ],
  26651: [
    ["HARPPA Nordi Toddler Learning Tower Foldable White", "check", [], "Same HARPPA Nordi tower; check for HANS0002 and whether the repair kit is installed."],
  ],
  27024: [
    ["Scotch Thermal Laminator TL1302Z 13 inch", "match", ["TL1302Z"], "Scotch laminator, model TL1302Z in title."],
    ["Scotch TL901X Thermal Laminator 9\"", "no_match", [], "Different Scotch model (TL901X), not covered."],
  ],
};

const scanByRecall = {};
const byRecall = recalls.map((r) => {
  const R = rng(r.recall_number);
  const scripted = LISTINGS[r.recall_number];
  const listings = Math.floor(R() * (r.is_childrens ? 70 : 45)) + (scripted ? 12 : 0);
  const match = scripted ? scripted.filter((x) => x[1] === "match").length + Math.floor(R() * 2) : R() < 0.18 ? Math.floor(R() * 2) + 1 : 0;
  const check = scripted ? scripted.filter((x) => x[1] === "check").length + Math.floor(R() * 3) : R() < 0.35 ? Math.floor(R() * 4) + 1 : 0;
  const examples = [];
  if (scripted) {
    const items = scripted.map(([title, verdict, ids, reason], i) => {
      const id = `ebay:placeholder-${r.recall_number}-${i + 1}`;
      examples.push(id);
      const pr = rng(id);
      return {
        listing_id: id,
        source: "ebay",
        title,
        subtitle: null,
        condition: CONDITIONS[Math.floor(pr() * CONDITIONS.length)],
        price: `$${(8 + pr() * 140).toFixed(2)}`,
        link: ebaySearch(title),
        thumbnail: null,
        seller_hash: hash(id),
        item_specifics: {},
        query: r.spec.search_queries[0],
        recall_number: r.recall_number,
        fetched_at: "2026-10-16T21:14:00Z",
        verdict: { verdict, identifiers_found: ids, conflicts: [], reason },
        human_verified: verdict === "match" && pr() < 0.7,
      };
    });
    scanByRecall[r.recall_number] = { recall_number: r.recall_number, placeholder: true, listings: items };
  }
  return { recall_number: r.recall_number, title: r.title, is_childrens: r.is_childrens, listings, match: Math.min(match, listings), check: Math.min(check, listings), examples };
});

const sum = (k) => byRecall.reduce((n, x) => n + x[k], 0);
const scan = {
  placeholder: true,
  note: "Placeholder numbers shaped like the real scan. Real counts arrive from ml/results/scan_summary.json.",
  recalls_scanned: recalls.length,
  searches_spent: recalls.length * 2,
  listings_seen: sum("listings"),
  flagged_match: sum("match"),
  flagged_check: sum("check"),
  human_verified_match: Math.round(sum("match") * 0.62),
  childrens_flagged: byRecall.filter((x) => x.is_childrens).reduce((n, x) => n + x.match + x.check, 0),
  by_recall: byRecall.sort((a, b) => b.match - a.match || b.check - a.check || b.listings - a.listings),
  generated_at: "2026-10-16T21:30:00Z",
};

/* ---------- the demo card --------------------------------------------------- */
const R = Object.fromEntries(recalls.map((r) => [r.recall_number, r]));
const dns = (item, n, why) => ({ item, recall_number: n, recall_title: R[n].title, why: why ?? R[n].spec.hazard_short, remedy: R[n].spec.remedy_short });
const chk = (item, n) => ({ item, recall_number: n, recall_title: R[n].title, look_for: R[n].spec.look_for });

const WF = "inventory-check-demo-shop-2026-10-16T14-02";
const card = {
  id: "card_2026-10-15_demo-shop",
  placeholder: true,
  week_of: "2026-10-15",
  shop_id: "demo-shop",
  shop_name: "Little Loop Kids Consignment",
  new_recalls: recalls.filter((r) => r.recall_date === "2026-10-15").length,
  items_checked: 120,
  do_not_sell: [
    dns("Papablic bedside sleeper, gray stars & moon (bin B-14)", "27027"),
    dns("Skip Hop Elmo silicone teether with crayon box", "26739"),
    dns("Taleco Gear baby jumper, gray — seat label jumper-01", "26688"),
  ],
  check_label: [
    chk("Melissa & Doug Lights & Sound Fire Truck", "26780"),
    chk("HABA rainbow rattle, wooden", "26719"),
    chk("Love to Dream portable sleep machine", "26798"),
    chk("Baby bath seat with suction cups, gray, no brand on tag", "27018"),
    chk("HARPPA Nordi toddler tower, white", "26651"),
  ],
  applied_memories: [
    { memory_id: "mem_8f3a21", text: "Skip Hop items in bin C are the Zoo line, not Sesame Street. Clear them for the Elmo teether recall." },
    { memory_id: "mem_c07e94", text: "Never clear an unbranded bath seat. Always CHECK LABEL." },
  ],
  workflow_id: WF,
  model: "qwen3.5-4b-recalldesk-lora",
  generated_at: "2026-10-16T14:02:41Z",
};

/* ---------- workflow steps & runs ------------------------------------------ */
const t = (base, s) => new Date(Date.parse(base) + s * 1000).toISOString();
function steps(base, list) {
  return list.map(([name, a, b, extra]) => ({ name, status: "completed", attempt: 1, started_at: t(base, a), ended_at: t(base, b), error: null, note: null, ...(extra ?? {}) }));
}
const checkSteps = steps("2026-10-16T14:02:00Z", [
  ["load_shop_memories", 0.2, 1.1, { note: "Backboard: 2 memories retrieved for demo-shop" }],
  ["check_items", 1.2, 31.4, { attempt: 2, error: "attempt 1: model returned invalid JSON for 1 pair (retried)", note: "120 items × top-5 recalls (BM25) = 600 pairs; 8 flagged" }],
  ["scan_ebay_store", 31.5, 33.0, { note: "source=snapshot (SerpApi quota reserved for the weekly sweep)" }],
  ["compose_card", 33.1, 33.9, { note: "3 DO NOT SELL · 5 CHECK LABEL · 2 memories applied" }],
  ["publish_card", 34.0, 34.4, { note: "card_2026-10-15_demo-shop" }],
]);
const cardStatus = { placeholder: true, status: "completed", workflow_id: WF, card, steps: checkSteps };

const sweepBase = "2026-10-15T18:00:04Z";
const sweepSteps = steps(sweepBase, [
  ["fetch_new_recalls", 0, 4.8, { attempt: 3, error: "attempts 1–2: CPSC API HTTP 503 (backoff 2s, 4s)", note: "6 new recalls since 2026-10-08" }],
  ["extract_spec", 5.0, 52.6, { note: "6 specs from the teacher (Qwen3.5-397B-A17B)" }],
  ["load_shop_memories", 52.8, 53.6, { note: "3 shops watched" }],
  ["check_items", 53.7, 141.0, { error: "worker crashed at 96s; resumed on worker-2 from event history (no activity re-run)", note: "3 shops, 342 items" }],
  ["scan_ebay_store", 141.2, 150.9, { note: "12 SerpApi searches (6 cached)" }],
  ["compose_card", 151.0, 152.3, { note: "3 cards" }],
  ["publish_card", 152.4, 153.1, { note: "3 cards published" }],
]);
const runs = [
  { workflow_id: WF, workflow_type: "InventoryCheckWorkflow", shop_id: "demo-shop", status: "completed", started_at: "2026-10-16T14:02:00Z", ended_at: t("2026-10-16T14:02:00Z", 34.4), steps: checkSteps, retries: 1, resumed_after_crash: false, history_events: 41, card_id: card.id },
  { workflow_id: "weekly-recall-sweep-2026-10-15", workflow_type: "WeeklyRecallSweep", status: "completed", started_at: sweepBase, ended_at: t(sweepBase, 153.1), steps: sweepSteps, retries: 2, resumed_after_crash: true, workers: ["worker-1", "worker-2"], history_events: 118 },
  {
    workflow_id: "weekly-recall-sweep-2026-10-08", workflow_type: "WeeklyRecallSweep", status: "completed", started_at: "2026-10-08T18:00:03Z", ended_at: t("2026-10-08T18:00:03Z", 171.5),
    steps: steps("2026-10-08T18:00:03Z", [
      ["fetch_new_recalls", 0, 2.1, { note: "8 new recalls since 2026-10-01" }],
      ["extract_spec", 2.3, 64.0, { note: "8 specs" }],
      ["load_shop_memories", 64.1, 65.0],
      ["check_items", 65.1, 150.2, { note: "3 shops, 330 items" }],
      ["scan_ebay_store", 150.3, 169.8, { attempt: 1, note: "source=snapshot (SerpApi 429; not retried)" }],
      ["compose_card", 169.9, 171.0],
      ["publish_card", 171.1, 171.5],
    ]),
    retries: 0, resumed_after_crash: false, history_events: 97,
  },
].map((r) => ({ ...r, placeholder: true }));

/* ---------- eval placeholder ------------------------------------------------ */
const loss = Array.from({ length: 31 }, (_, i) => [i * 10, +(1.9 * Math.exp(-i / 6) + 0.21 + rng(`l${i}`)() * 0.05).toFixed(3)]);
const nll = [[0, 1.42], [100, 0.61], [200, 0.43], [300, 0.39]];
const evalJson = {
  placeholder: true,
  note: "Placeholder until the Tinker LoRA run and blind human labels land in ml/results/eval.json.",
  test_size: 220,
  generated_at: "2026-10-17T00:00:00Z",
  gold: "human (blind)",
  models: [
    { name: "Qwen3.5-397B-A17B (teacher)", role: "teacher", acc: 0.882, acc_ci: [0.836, 0.923], macro_f1: 0.861, risky_caught: "98/104", false_alarms: "13/116", json_valid: 1.0, p50_latency_ms: 2840, cost_per_1k_usd: 1.9 },
    { name: "Qwen3.5-4B + LoRA (ours)", role: "lora", acc: 0.859, acc_ci: [0.809, 0.9], macro_f1: 0.834, risky_caught: "96/104", false_alarms: "17/116", json_valid: 1.0, p50_latency_ms: 410, cost_per_1k_usd: 0.06 },
    { name: "Qwen3.5-4B (base, guided JSON)", role: "base_guided", acc: 0.714, acc_ci: [0.65, 0.773], macro_f1: 0.662, risky_caught: "82/104", false_alarms: "31/116", json_valid: 1.0, p50_latency_ms: 450, cost_per_1k_usd: 0.06 },
    { name: "Qwen3.5-4B (base)", role: "base", acc: 0.632, acc_ci: [0.568, 0.695], macro_f1: 0.571, risky_caught: "77/104", false_alarms: "38/116", json_valid: 0.91, p50_latency_ms: 430, cost_per_1k_usd: 0.06 },
    { name: "Identifier rules (regex)", role: "heuristic", acc: 0.586, acc_ci: [0.523, 0.65], macro_f1: 0.47, risky_caught: "51/104", false_alarms: "6/116", json_valid: 1.0, p50_latency_ms: 1, cost_per_1k_usd: 0 },
    { name: "Llama 3.3 70B (via Backboard)", role: "backboard:llama-3.3-70b", acc: 0.791, acc_ci: [0.736, 0.841], macro_f1: 0.752, risky_caught: "90/104", false_alarms: "24/116", json_valid: 0.98, p50_latency_ms: 1620, cost_per_1k_usd: 0.42 },
  ],
  paired: [
    { a: "lora", b: "base", gain: 0.227, ci: [0.164, 0.291], only_a: 58, only_b: 8, p: 1.2e-10 },
    { a: "lora", b: "base_guided", gain: 0.145, ci: [0.086, 0.205], only_a: 41, only_b: 9, p: 4.1e-6 },
    { a: "lora", b: "teacher", gain: -0.023, ci: [-0.064, 0.018], only_a: 11, only_b: 16, p: 0.44 },
    { a: "lora", b: "heuristic", gain: 0.273, ci: [0.205, 0.341], only_a: 70, only_b: 10, p: 2.0e-12 },
  ],
  confusion: {
    lora: { labels: ["match", "check", "no_match"], matrix: [[38, 4, 1], [5, 49, 7], [2, 12, 102]] },
    base: { labels: ["match", "check", "no_match"], matrix: [[29, 8, 6], [11, 29, 21], [9, 26, 81]] },
  },
  training: { base_model: "Qwen/Qwen3.5-4B", rank: 32, steps: 300, epochs: 3, lr: 0.0002, loss_curve: loss, test_nll: nll },
  examples: [
    { pair_id: "p_27027_02", listing_title: "Papablic 3-in-1 Bassinet Bedside Sleeper Gray — gently used", recall_title: R["27027"].title, gold: "check", base: "no_match", lora: "check" },
    { pair_id: "p_26780_01", listing_title: "Melissa & Doug Lights and Sound Fire Truck Activity Board", recall_title: R["26780"].title, gold: "check", base: "match", lora: "check" },
    { pair_id: "p_26739_03", listing_title: "Skip Hop Zoo Teether Owl Silicone", recall_title: R["26739"].title, gold: "no_match", base: "match", lora: "no_match" },
    { pair_id: "p_27024_02", listing_title: "Scotch TL901X Thermal Laminator 9\"", recall_title: R["27024"].title, gold: "no_match", base: "match", lora: "no_match" },
    { pair_id: "p_26688_02", listing_title: "Taleco Gear 2-in-1 Baby Swing & Jumper Pink", recall_title: R["26688"].title, gold: "match", base: "check", lora: "match" },
  ],
};

const memories = [
  { memory_id: "mem_8f3a21", shop_id: "demo-shop", text: card.applied_memories[0].text, recall_number: "26739", correct_verdict: "no_match", created_at: "2026-09-04T16:20:00Z" },
  { memory_id: "mem_c07e94", shop_id: "demo-shop", text: card.applied_memories[1].text, recall_number: "27018", correct_verdict: "check", created_at: "2026-10-09T15:02:00Z" },
  { memory_id: "mem_51d0b7", shop_id: "demo-shop", text: "Our Graco Pack 'n Play stock is all 2022+; the 2019 play-yard recall doesn't apply.", recall_number: null, correct_verdict: "no_match", created_at: "2026-08-21T18:45:00Z" },
].map((m) => ({ ...m, placeholder: true }));

const write = (name, data) => fs.writeFileSync(path.join(OUT, name), JSON.stringify(data, null, 1) + "\n", "utf8");
write("recalls.json", recalls);
write("scan_summary.json", scan);
write("scan_listings.json", scanByRecall);
write("card.json", card);
write("card_status.json", cardStatus);
write("runs.json", runs);
write("eval.json", evalJson);
write("memories.json", memories);
console.log(`wrote ${OUT}: ${recalls.length} recalls (${recalls.filter((r) => r.is_childrens).length} children's), ${Object.keys(scanByRecall).length} scripted scans`);
