/**
 * In-browser fallback for the static demo: deterministic identifier/keyword
 * rules (the same idea as the `heuristic` provider), used ONLY when the API is
 * down. The card it produces is labelled "heuristic (in-browser demo)".
 */
import type { CheckLabel, DoNotSell, InventoryItem, Memory, RecallCard, RecallRecord, Verdict } from "./types";
import type { LocalCorrection } from "./api";

const norm = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[™®’']/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
const compact = (s: string) => norm(s).replace(/\s+/g, "");

const STOP = new Set(["the", "and", "with", "for", "of", "a", "in", "on", "to", "from", "set", "sets", "kit", "pack", "new", "used", "baby", "kids", "toy", "toys", "recalls", "recalled"]);
const words = (s: string) => norm(s).split(" ").filter((w) => w.length > 2 && !STOP.has(w));

function brandHit(brand: string, text: string): boolean {
  const b = norm(brand.replace(/\(.*?\)/g, ""));
  if (!b || b === "unknown") return false;
  return ` ${norm(text)} `.includes(` ${b} `) || compact(text).includes(compact(b));
}

function idHit(ids: string[], text: string): string[] {
  const t = compact(text);
  return ids.filter((id) => {
    const c = compact(id);
    return c.length >= 4 && t.includes(c);
  });
}

export interface ItemVerdict {
  recall: RecallRecord;
  verdict: Verdict;
  ids: string[];
}

export function classifyItem(item: InventoryItem, recalls: RecallRecord[]): ItemVerdict | null {
  const text = [item.name, item.brand, item.model, item.notes].filter(Boolean).join(" ");
  const tw = new Set(words(text));
  let best: ItemVerdict | null = null;
  let bestScore = 0;
  for (const r of recalls) {
    const spec = r.spec;
    const brand = spec?.brand ?? "";
    const ids = [...new Set([...(spec?.model_numbers ?? []), ...(spec?.other_identifiers ?? []), ...r.regex_ids])];
    const found = idHit(ids, text);
    const b = brandHit(brand, text);
    const productWords = words(`${spec?.product_type ?? ""} ${spec?.product_name ?? r.product_names.join(" ")}`).filter((w) => !words(brand).includes(w));
    const overlap = productWords.filter((w) => tw.has(w) || tw.has(w.replace(/s$/, ""))).length;
    let verdict: Verdict | null = null;
    let score = 0;
    if (b && found.length) [verdict, score] = ["match", 10 + found.length];
    else if (b && overlap >= 2) [verdict, score] = ["check", 6 + overlap];
    else if (b && overlap >= 1) [verdict, score] = ["check", 4 + overlap];
    else if (found.some((f) => compact(f).length >= 6)) [verdict, score] = ["check", 5];
    if (verdict && score > bestScore) {
      best = { recall: r, verdict, ids: found };
      bestScore = score;
    }
  }
  return best;
}

export function matchItems(args: {
  items: InventoryItem[];
  recalls: RecallRecord[];
  corrections: LocalCorrection[];
  memories: Memory[];
  shopId: string;
  shopName: string;
  workflowId: string;
  generatedAt: string;
}): RecallCard {
  const { items, recalls, corrections } = args;
  const latest = recalls.reduce((m, r) => (r.recall_date > m ? r.recall_date : m), "");
  const dns: DoNotSell[] = [];
  const chk: CheckLabel[] = [];
  const applied = new Map<string, string>();
  for (const item of items) {
    const v = classifyItem(item, recalls);
    if (!v) continue;
    const label = [item.name, item.model && !item.name.includes(item.model) ? item.model : null].filter(Boolean).join(" — ");
    const cor = corrections.find((c) => c.recall_number === v.recall.recall_number && norm(c.listing_or_item) === norm(label));
    const verdict = cor ? cor.correct_verdict : v.verdict;
    if (cor) applied.set(cor.memory_id, cor.note || `${cor.listing_or_item}: marked ${cor.correct_verdict.replace("_", " ")}`);
    const spec = v.recall.spec;
    if (verdict === "match") {
      dns.push({ item: label, recall_number: v.recall.recall_number, recall_title: v.recall.title, why: spec?.hazard_short ?? v.recall.hazards[0] ?? "", remedy: spec?.remedy_short ?? v.recall.remedies[0] ?? "" });
    } else if (verdict === "check") {
      chk.push({ item: label, recall_number: v.recall.recall_number, recall_title: v.recall.title, look_for: spec?.look_for ?? (spec?.model_numbers.length ? `Model no. on the label: ${spec.model_numbers.slice(0, 3).join(", ")}` : "Brand and model on the product label") });
    }
  }
  return {
    id: `card_${latest}_${args.shopId}`,
    week_of: latest,
    shop_id: args.shopId,
    shop_name: args.shopName,
    new_recalls: recalls.filter((r) => r.recall_date === latest).length,
    items_checked: items.length,
    do_not_sell: dns,
    check_label: chk,
    applied_memories: [...applied].map(([memory_id, text]) => ({ memory_id, text })),
    workflow_id: args.workflowId,
    model: "heuristic (in-browser demo)",
    generated_at: args.generatedAt,
    placeholder: true,
  };
}

/** Parse pasted lines or CSV (name,brand,model,notes; header optional). */
export function parseItems(input: string): InventoryItem[] {
  const lines = input
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length) return [];
  const header = splitCsv(lines[0]).map((h) => h.toLowerCase());
  const isCsv = header.includes("name") && lines[0].includes(",");
  if (!isCsv) return lines.map((name) => ({ name }));
  const idx = (k: string) => header.indexOf(k);
  return lines.slice(1).flatMap((l) => {
    const c = splitCsv(l);
    const name = c[idx("name")]?.trim();
    if (!name) return [];
    const get = (k: string) => (idx(k) >= 0 ? c[idx(k)]?.trim() || undefined : undefined);
    return [{ name, brand: get("brand"), model: get("model"), notes: get("notes") }];
  });
}

function splitCsv(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (q) {
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') q = false;
      else cur += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out;
}
