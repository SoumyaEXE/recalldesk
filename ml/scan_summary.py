"""Run the chosen classifier over ALL scanned eBay listings -> ml/results/scan_summary.json (the headline).

    python -m ml.scan_summary [--provider heuristic|tinker|openai] [--corpus AB]

Every (recall, listing) found by that recall's search is classified (not just the top-15 used for pairs).
Verdicts are cached in ml/results/scan_preds.<provider>.jsonl so reruns don't re-spend. human_verified_match
counts flagged pairs whose blind human label (ml.label_ui -> data/gold/labels.jsonl) is also "match". No human review
has been done for this project yet, so it is 0: every flag is a model verdict, not a confirmed recall.
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from ml.common import (GOLD, LISTINGS, RESULTS, load_listings, load_recalls, load_specs, now_iso, read_jsonl, spend_stage,
                       specs_path, utf8_stdout, write_json, write_jsonl)
from ml.infer import active_provider, classify_batch
from ml.make_pairs import pair_id


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None)
    ap.add_argument("--corpus", default="AB")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    prov = active_provider(args.provider)
    recs = {r["recall_number"]: r for r in load_recalls(args.corpus)}
    specs, listings = load_specs(), load_listings()
    index = [r for r in read_jsonl(LISTINGS / "search_index.jsonl") if r["recall_number"] in recs]
    if not index:
        raise SystemExit("no scanned listings - run: python -m ml.serp_scan --corpus A --max-searches N")
    cache_p = RESULTS / f"scan_preds.{prov.split()[0]}.jsonl"
    cache = {(r["recall_number"], r["listing_id"]): r for r in read_jsonl(cache_p)}
    todo, keys = [], []
    for row in index:
        rn = row["recall_number"]
        spec = specs.get(rn)
        for lid in row.get("listing_ids", []):
            if (rn, lid) in cache or lid not in listings or not spec:
                continue
            todo.append((spec, listings[lid]))
            keys.append((rn, lid))
    print(f"provider={prov} specs={specs_path().name}: {len(cache)} cached verdicts, {len(todo)} to classify")
    if todo:
        results = classify_batch(todo, provider=prov, max_workers=args.workers)
        for (rn, lid), (v, meta) in zip(keys, results):
            cache[(rn, lid)] = {"recall_number": rn, "listing_id": lid, "verdict": v.model_dump(),
                                "provider": meta.get("provider"), "model": meta.get("model")}
        write_jsonl(cache_p, cache.values())

    gold = {}
    for g in read_jsonl(GOLD / "labels.jsonl"):
        gold[g["pair_id"]] = g["label"]
    by_recall = defaultdict(lambda: {"listings": 0, "match": 0, "check": 0, "m_ex": [], "c_ex": []})
    seen_listings = set()
    human_match = human_checked = 0
    for row in index:
        rn = row["recall_number"]
        for lid in dict.fromkeys(row.get("listing_ids", [])):
            p = cache.get((rn, lid))
            if not p:
                continue
            seen_listings.add(lid)
            b = by_recall[rn]
            b["listings"] += 1
            v = p["verdict"]["verdict"]
            if v in ("match", "check"):
                b[v] += 1
                b["m_ex" if v == "match" else "c_ex"].append(lid)
                g = gold.get(pair_id(rn, lid))
                if g is not None:
                    human_checked += 1
                    human_match += g == "match"
    out_rows = []
    for rn, b in by_recall.items():
        out_rows.append({"recall_number": rn, "title": recs[rn]["title"], "is_childrens": recs[rn].get("is_childrens"),
                         "listings": b["listings"], "match": b["match"], "check": b["check"],
                         "examples": (b["m_ex"] + b["c_ex"])[:5]})
    out_rows.sort(key=lambda x: (-x["match"], -x["check"], x["recall_number"]))
    summary = {
        "recalls_scanned": len({r["recall_number"] for r in index}),
        "searches_spent": spend_stage("serp_scan").get("searches_spent", 0),
        "listings_seen": len(seen_listings),
        "pairs_classified": sum(b["listings"] for b in by_recall.values()),
        "flagged_match": sum(b["match"] for b in by_recall.values()),
        "flagged_check": sum(b["check"] for b in by_recall.values()),
        "human_verified_match": human_match, "human_reviewed_flags": human_checked,
        "childrens_flagged": sum(b["match"] + b["check"] for rn, b in by_recall.items() if recs[rn].get("is_childrens")),
        "childrens_recalls_with_flags": sum(1 for rn, b in by_recall.items()
                                            if recs[rn].get("is_childrens") and b["match"] + b["check"]),
        "recalls_with_match": sum(1 for b in by_recall.values() if b["match"]),
        "classifier": {"provider": prov, "model": next(iter(cache.values()), {}).get("model"),
                       "specs": specs_path().name},
        "by_recall": out_rows, "generated_at": now_iso(),
        "note": ("flagged_* are model verdicts, not confirmed recalls. human_verified_match counts flags a person "
                 "confirmed in the blind label UI"
                 + (f" ({human_checked} flags reviewed)." if human_checked
                    else "; no human review has been done yet, so it is 0.")),
    }
    write_json(RESULTS / "scan_summary.json", summary)
    print({k: v for k, v in summary.items() if k not in ("by_recall",)})


if __name__ == "__main__":
    main()
