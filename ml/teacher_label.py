"""Teacher (Qwen3.5-397B-A17B on Tinker) labels ALL (recall, listing) pairs -> data/labeled/teacher.jsonl.

    python -m ml.teacher_label [--limit N] [--concurrency 32] [--split all|train|test]

Same definitions as ml/LABELING.md (ml/prompts.TEACHER_SYSTEM). The teacher sees the spec, the original CPSC
description (privileged info the student never gets) and the listing. Strict JSON MatchVerdict, 2 retries on
invalid JSON, resume-safe (valid rows are skipped on rerun). Rows:
{"pair_id","verdict":MatchVerdict|null,"valid","latency_ms","tokens_in","tokens_out","attempts","error","model"}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter

from ml.common import (LABELED, PAIRS, TEACHER_MODEL, add_spend, load_listings, load_recalls, load_specs, make_renderer,
                       read_jsonl, require_key, sample_cost_usd, specs_path, utf8_stdout, write_jsonl)
from ml.prompts import teacher_messages

OUT = LABELED / "teacher.jsonl"


async def main_async(args) -> None:
    import tinker

    from ml.tinker_sampling import classify_many

    pairs = read_jsonl(PAIRS / "pairs.jsonl")
    if not pairs:
        raise SystemExit("data/pairs/pairs.jsonl missing - run: python -m ml.make_pairs")
    if args.split != "all":
        pairs = [p for p in pairs if p["split"] == args.split]
    recs = {r["recall_number"]: r for r in load_recalls("AB")}
    specs = load_specs()
    listings = load_listings()
    print(f"specs: {specs_path().name}")
    existing = {r["pair_id"]: r for r in read_jsonl(OUT)}
    todo = [p for p in pairs if not (existing.get(p["pair_id"]) or {}).get("valid")]
    if args.limit:
        todo = todo[: args.limit]
    print(f"teacher={TEACHER_MODEL}: {len(pairs)} pairs, {len(pairs) - len(todo)} done, {len(todo)} to do")
    if not todo:
        return
    _tok, renderer = make_renderer(TEACHER_MODEL)
    service = tinker.ServiceClient()
    sc = await service.create_sampling_client_async(base_model=TEACHER_MODEL)
    by_id = {p["pair_id"]: p for p in todo}
    done = 0
    t0 = time.time()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    f = OUT.open("a", encoding="utf-8")

    def on_result(key, r):
        nonlocal done
        row = {"pair_id": key, "verdict": r.verdict.model_dump() if r.verdict else None, "valid": r.verdict is not None,
               "latency_ms": round(r.latency_ms, 1), "tokens_in": r.prompt_tokens, "tokens_out": r.completion_tokens,
               "attempts": r.attempts, "error": r.error, "raw_output": r.text[:1500], "model": TEACHER_MODEL}
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        done += 1
        if done % 50 == 0 or done == len(todo):
            print(f"  {done}/{len(todo)}  ({time.time() - t0:.0f}s)")

    items = []
    for p in todo:
        rec = recs.get(p["recall_number"])
        spec = specs.get(p["recall_number"])
        lst = listings.get(p["listing_id"])
        if not (rec and spec and lst):
            continue
        items.append((p["pair_id"], teacher_messages(spec, lst, rec)))
    if len(items) < len(todo):
        print(f"WARNING: {len(todo) - len(items)} pairs skipped (missing recall/spec/listing)")
    try:
        await classify_many(sc, renderer, items, concurrency=args.concurrency, on_result=on_result,
                            max_tokens=220, retries=2, temperature=0.0)
    finally:
        f.close()

    # compact: latest row per pair (valid preferred), in pairs order
    latest: dict[str, dict] = {}
    for r in read_jsonl(OUT):
        if r["pair_id"] not in latest or r.get("valid") or not latest[r["pair_id"]].get("valid"):
            latest[r["pair_id"]] = r
    all_pairs = read_jsonl(PAIRS / "pairs.jsonl")
    ordered = [latest[p["pair_id"]] for p in all_pairs if p["pair_id"] in latest]
    write_jsonl(OUT, ordered)
    pt = sum(r.get("tokens_in", 0) * max(1, r.get("attempts", 1)) for r in ordered)
    ct = sum(r.get("tokens_out", 0) for r in ordered)
    usd = sample_cost_usd(TEACHER_MODEL, pt, ct)
    add_spend("teacher_label", {"model": TEACHER_MODEL, "rows": len(ordered), "prompt_tokens": pt,
                                "completion_tokens": ct, "est_usd": round(usd, 4)})
    valid = [r for r in ordered if r.get("valid")]
    print(f"{len(valid)}/{len(ordered)} valid; first-try valid {sum(r.get('attempts') == 1 and r['valid'] for r in ordered)}; "
          f"est ${usd:.3f}")
    print("verdicts:", dict(Counter(r["verdict"]["verdict"] for r in valid)))


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--split", default="all", choices=["all", "train", "test"])
    args = ap.parse_args()
    require_key("TINKER_API_KEY", "teacher labeling")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
