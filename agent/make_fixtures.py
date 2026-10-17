"""Build shared/fixtures/*.json from REAL data (CPSC recalls + real workflow runs + heuristic verdicts).

    python -m agent.make_fixtures

  recalls.json            corpus A (since 2026-07-18) RecallRecord & {spec, spec_source}
  card_<shop>.json        latest published card per demo shop (agent/cards/latest_<shop>.json; computed inline if none)
  runs.json               run records (steps, workers) of those cards' workflows (Temporal if reachable)
  memories.json           {shop_id: [memories]} from the memory backend
  scan.json               ml/results/scan_summary.json if present, else a PLACEHOLDER (clearly marked)
  eval.json               ml/results/eval.json if present, else a PLACEHOLDER (clearly marked)

UI-named copies (the names web/lib/api.ts falls back to): card.json + card_status.json (little-loop),
scan_summary.json (= scan.json), scan_listings.json ({recall_number: ScanDetail}), memories.json is a flat
Memory[] across shops (the per-shop map is memories_by_shop.json).

The UI agent copies these to web/public/fixtures/ for the static demo.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from agent import backboard_memory, inline
from agent.config import CARDS_DIR, CORPUS_A_START, FIXTURES_DIR, ML_RESULTS, RUNS_DIR, load_shops, safe_name, setup_logging


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _w(name: str, obj) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURES_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote shared/fixtures/{name}")


async def _run_record(wid: str) -> dict | None:
    p = RUNS_DIR / f"{safe_name(wid)}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    try:
        from agent.config import temporal_client
        from agent.runs import get_run

        client = await asyncio.wait_for(temporal_client(), timeout=3)
        return await get_run(client, wid)
    except Exception:
        return None


async def main_async() -> None:
    from agent.api import _recalls_with_specs, _summary, memory_row

    rows, src = _recalls_with_specs()
    a = [r for r in rows if r.get("recall_date", "") >= CORPUS_A_START]
    _w("recalls.json", a)

    runs, mems = [], {}
    for shop_id in load_shops():
        p = CARDS_DIR / f"latest_{safe_name(shop_id)}.json"
        if p.exists():
            card = json.loads(p.read_text(encoding="utf-8"))
        else:
            wid = inline.new_id(shop_id)
            inline.init_run(wid, shop_id)
            card = inline.run_inline(wid, shop_id, [])["card"]
        _w(f"card_{shop_id}.json", card)
        run = await _run_record(card["workflow_id"])
        if run:
            run = _summary({**run, "card": card})
            runs.append(run)
            if shop_id == "little-loop":
                _w("card.json", card)
                _w("card_status.json", {"status": "completed", "workflow_id": card["workflow_id"],
                                        "steps": run.get("steps", []), "card": card, "shop_id": shop_id})
        mems[shop_id] = [memory_row(h, shop_id) for h in await backboard_memory.list_memories(shop_id)]
    # include the crash-demo run if there is one: it is the durability proof the UI can show
    for p in sorted(RUNS_DIR.glob("*crashdemo*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:1]:
        runs.append(_summary(json.loads(p.read_text(encoding="utf-8"))))
    runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    _w("runs.json", runs)
    _w("memories_by_shop.json", mems)
    _w("memories.json", [m for v in mems.values() for m in v])

    scan = ML_RESULTS / "scan_summary.json"
    if scan.exists():
        summary = json.loads(scan.read_text(encoding="utf-8"))
    else:
        summary = {
            "placeholder": True,
            "note": "PLACEHOLDER - no SerpApi eBay scan has run yet. Real numbers replace this when ml/ writes "
                    "ml/results/scan_summary.json. Recall list below is real (CPSC, since 2026-07-18).",
            "recalls_scanned": 0, "searches_spent": 0, "listings_seen": 0, "flagged_match": 0, "flagged_check": 0,
            "human_verified_match": 0, "childrens_flagged": 0,
            "by_recall": [{"recall_number": r["recall_number"], "title": r["title"], "listings": 0, "match": 0,
                           "check": 0, "examples": [], "is_childrens": bool(r.get("is_childrens"))} for r in a],
            "generated_at": _now()}
    _w("scan.json", summary)
    _w("scan_summary.json", summary)
    from agent.api import scan_recall

    listings = {}
    for b in summary.get("by_recall", []):
        if b.get("listings"):
            listings[b["recall_number"]] = await scan_recall(b["recall_number"])
    _w("scan_listings.json", listings)
    ev = ML_RESULTS / "eval.json"
    if ev.exists():
        _w("eval.json", json.loads(ev.read_text(encoding="utf-8")))
    else:
        zero = {"acc": 0, "acc_ci": [0, 0], "macro_f1": 0, "risky_caught": "0/0", "false_alarms": "0/0",
                "json_valid": 0, "p50_latency_ms": 0, "cost_per_1k_usd": 0}
        _w("eval.json", {
            "placeholder": True,
            "note": "PLACEHOLDER - every number is 0 until the ML agent writes ml/results/eval.json "
                    "(human blind gold labels on held-out recalls). Do not quote.",
            "test_size": 0, "generated_at": _now(), "gold": "human (blind)",
            "models": [{"name": "Qwen3.5-397B-A17B (teacher)", "role": "teacher", **zero},
                       {"name": "Qwen3.5-4B (base)", "role": "base", **zero},
                       {"name": "Qwen3.5-4B (base, guided prompt)", "role": "base_guided", **zero},
                       {"name": "qwen3.5-4b-recalldesk-lora", "role": "lora", **zero},
                       {"name": "heuristic-rules", "role": "heuristic", **zero}],
            "paired": [{"a": "lora", "b": "base", "gain": 0, "ci": [0, 0], "only_a": 0, "only_b": 0, "p": 1}],
            "confusion": {"lora": {"labels": ["match", "check", "no_match"], "matrix": [[0, 0, 0], [0, 0, 0], [0, 0, 0]]}},
            "training": {"base_model": "Qwen/Qwen3.5-4B", "rank": 32, "steps": 0, "epochs": 0, "lr": 0,
                         "loss_curve": [], "test_nll": []},
            "examples": []})
    print(f"recalls source: {src}")


def main() -> None:
    setup_logging("fixtures", "WARNING")
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
