import type { FlaggedItem } from "@/components/rd/item-drawer";
import type { InventoryRow } from "./api";
import type { RecallCard, Verdict } from "./types";

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export interface InventoryVerdict {
  inv: InventoryRow;
  verdict: Verdict;
  flag?: FlaggedItem;
}

export function cardFlags(card?: RecallCard): FlaggedItem[] {
  if (!card) return [];
  return [
    ...card.do_not_sell.map((r) => ({ label: r.item, verdict: "match" as const, recall_number: r.recall_number, recall_title: r.recall_title, why: r.why, remedy: r.remedy })),
    ...card.check_label.map((r) => ({ label: r.item, verdict: "check" as const, recall_number: r.recall_number, recall_title: r.recall_title, look_for: r.look_for })),
  ];
}

/**
 * Join card rows back onto inventory rows. Card item labels are
 * "<brand> <name> (model X)" (API) or "<name> — <model>" (in-browser demo), so
 * each flag goes to the inventory row with the longest name it contains.
 */
export function joinInventory(rows: InventoryRow[], card?: RecallCard): { rows: InventoryVerdict[]; flags: FlaggedItem[] } {
  const flags = cardFlags(card);
  const byRow = new Map<number, FlaggedItem>();
  const joined = flags.map((f) => {
    const label = norm(f.label);
    let best = -1;
    let bestLen = 0;
    rows.forEach((r, i) => {
      const n = norm(r.name);
      if (n && label.includes(n) && n.length > bestLen && !byRow.has(i)) {
        best = i;
        bestLen = n.length;
      }
    });
    if (best >= 0) {
      const withInv = { ...f, inv: rows[best] };
      byRow.set(best, withInv);
      return withInv;
    }
    return f;
  });
  return {
    rows: rows.map((inv, i) => {
      const flag = byRow.get(i);
      return flag ? { inv, verdict: flag.verdict, flag } : { inv, verdict: "no_match" as const };
    }),
    flags: joined,
  };
}
