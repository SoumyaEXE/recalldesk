"""Build (recall, listing) pairs and a leakage-safe split BY RECALL.

    python -m ml.make_pairs [--per-recall 15] [--test-recalls 28] [--test-pairs 225] [--seed 0]

- For each recall, the top <=15 listings of its eBay search (search order, listing ids deduped).
- Split by recall (held-out recalls never appear in train), stratified by is_childrens, seed 0. Recalls that share
  a query or product name (e.g. "Expands Recall" re-issues) are grouped and always land in the same split.
- Test aims for ~25-30 recalls / ~200-250 pairs with at least half children's recalls (the shop story).
- Any train pair whose listing also appears in a test pair is dropped (no listing text leaks across splits).
Writes data/pairs/pairs.jsonl, data/splits/{train,test}.jsonl, data/splits/split_stats.json.
"""
from __future__ import annotations

import argparse
import random
import re
from collections import Counter, defaultdict

from ml.common import LISTINGS, PAIRS, SPLITS, load_listings, load_recalls, read_jsonl, utf8_stdout, write_json, write_jsonl


def pair_id(recall_number: str, listing_id: str) -> str:
    return f"p_{recall_number}_{listing_id.split(':', 1)[-1]}"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def group_recalls(recs: dict[str, dict], queries: dict[str, str]) -> dict[str, str]:
    """Union-find over shared query / product name -> group id per recall."""
    parent = {r: r for r in recs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    seen: dict[str, str] = {}
    for rn, r in recs.items():
        keys = [("q", _norm(queries.get(rn, "")))] + [("n", _norm(n)) for n in r.get("product_names", [])[:1]]
        for k in keys:
            if not k[1]:
                continue
            if k in seen:
                union(rn, seen[k])
            else:
                seen[k] = rn
    return {rn: find(rn) for rn in recs}


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-recall", type=int, default=15)
    ap.add_argument("--test-recalls", type=int, default=28)
    ap.add_argument("--test-pairs", type=int, default=225)
    ap.add_argument("--max-test-pairs", type=int, default=250)
    ap.add_argument("--min-childrens-frac", type=float, default=0.5)
    ap.add_argument("--min-listings", type=int, default=3, help="recalls with fewer listings never go to test")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    recs = {r["recall_number"]: r for r in load_recalls("AB")}
    listings = load_listings()
    index = read_jsonl(LISTINGS / "search_index.jsonl")
    if not index or not listings:
        raise SystemExit("no listings yet - run: python -m ml.serp_scan --corpus A --max-searches N")

    per_recall: dict[str, list[str]] = defaultdict(list)
    queries: dict[str, str] = {}
    for row in index:
        rn = row["recall_number"]
        if rn not in recs:
            continue
        queries.setdefault(rn, row.get("query", ""))
        for lid in row.get("listing_ids", []):
            if lid in listings and lid not in per_recall[rn] and len(per_recall[rn]) < args.per_recall:
                per_recall[rn].append(lid)
    per_recall = {k: v for k, v in per_recall.items() if v}
    groups = group_recalls({k: recs[k] for k in per_recall}, queries)
    by_group: dict[str, list[str]] = defaultdict(list)
    for rn, g in groups.items():
        by_group[g].append(rn)

    rng = random.Random(args.seed)
    strata: dict[bool, list[str]] = {True: [], False: []}
    for g in sorted(by_group):
        members = by_group[g]
        child = any(recs[m].get("is_childrens") for m in members)
        if all(len(per_recall[m]) >= args.min_listings for m in members):
            strata[child].append(g)
    for k in strata:
        rng.shuffle(strata[k])

    test_groups: list[str] = []
    n_rec = n_pairs = n_child = 0
    want_child = max(args.min_childrens_frac, len(strata[True]) / max(1, len(strata[True]) + len(strata[False])))
    while (n_rec < args.test_recalls or n_pairs < args.test_pairs) and (strata[True] or strata[False]):
        need_child = n_child < want_child * (n_rec + 1)
        src = strata[True] if (need_child and strata[True]) or not strata[False] else strata[False]
        g = src.pop()
        add_pairs = sum(len(per_recall[m]) for m in by_group[g])
        if n_pairs + add_pairs > args.max_test_pairs and n_rec >= 20:
            continue
        test_groups.append(g)
        for m in by_group[g]:
            n_rec += 1
            n_pairs += len(per_recall[m])
            n_child += bool(recs[m].get("is_childrens"))
    test_recalls = {m for g in test_groups for m in by_group[g]}

    pairs, train, test = [], [], []
    test_listing_ids = {lid for rn in test_recalls for lid in per_recall[rn]}
    dropped = 0
    for rn in sorted(per_recall, key=lambda x: (recs[x]["recall_date"], x), reverse=True):
        split = "test" if rn in test_recalls else "train"
        for rank, lid in enumerate(per_recall[rn]):
            row = {"pair_id": pair_id(rn, lid), "recall_number": rn, "listing_id": lid, "split": split}
            if split == "train" and lid in test_listing_ids:
                dropped += 1
                continue
            pairs.append(row)
            full = {**row, "rank": rank, "is_childrens": bool(recs[rn].get("is_childrens")),
                    "group": groups[rn]}
            (test if split == "test" else train).append(full)
    write_jsonl(PAIRS / "pairs.jsonl", pairs)
    write_jsonl(SPLITS / "train.jsonl", train)
    write_jsonl(SPLITS / "test.jsonl", test)
    stats = {
        "seed": args.seed, "per_recall_cap": args.per_recall,
        "recalls_with_listings": len(per_recall), "groups": len(by_group),
        "train_recalls": len({p["recall_number"] for p in train}), "test_recalls": len(test_recalls),
        "train_pairs": len(train), "test_pairs": len(test),
        "test_childrens_recalls": sum(bool(recs[r].get("is_childrens")) for r in test_recalls),
        "train_childrens_recalls": len({p["recall_number"] for p in train if p["is_childrens"]}),
        "test_childrens_pairs": sum(p["is_childrens"] for p in test),
        "train_pairs_dropped_listing_overlap": dropped,
        "test_recalls_by_corpus": dict(Counter("+".join(recs[r].get("corpus", [])) for r in test_recalls)),
        "recall_overlap_train_test": len({p["recall_number"] for p in train} & test_recalls),
        "listing_overlap_train_test": len({p["listing_id"] for p in train} & test_listing_ids),
    }
    write_json(SPLITS / "split_stats.json", stats)
    print(stats)


if __name__ == "__main__":
    main()
