"""Start an InventoryCheckWorkflow from the terminal, watch its steps, print the card.

    python -m agent.run_check little-loop            # whole inventory CSV
    python -m agent.run_check flip-garage --corpus A
    python -m agent.run_check sweep                  # WeeklyRecallSweep now (same as the Thursday schedule)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

from agent.config import TASK_QUEUE, setup_logging, temporal_client

MARK = {"pending": "[  ]", "running": "[..]", "retrying": "[!!]", "completed": "[OK]", "failed": "[XX]",
        "skipped": "[--]"}


def fmt_step(s: dict) -> str:
    line = f"{MARK.get(s['status'], '[??]')} {s['name']:<22} {s['status']:<9} attempt={s.get('attempt', 0)}"
    if s.get("note"):
        line += f"  {s['note']}"
    if s.get("error"):
        line += f"\n       -> {s['error']}"
    return line


def print_card(card: dict, out=print) -> None:
    out("")
    out(f"=== RECALL CARD {card['id']}  {card.get('shop_name')}  (week of {card['week_of']}) ===")
    out(f"  {card['new_recalls']} new recalls this week | {card['items_checked']} items checked | model: {card['model']}")
    out(f"  DO NOT SELL ({len(card['do_not_sell'])})")
    for d in card["do_not_sell"]:
        out(f"    x {d['item']}  -> CPSC {d['recall_number']}: {d.get('recall_title', '')[:70]}")
        out(f"        why: {d.get('why', '')[:150]}")
        out(f"        remedy: {d.get('remedy', '')[:100]}")
    out(f"  CHECK LABEL ({len(card['check_label'])})")
    for c in card["check_label"]:
        out(f"    ? {c['item']}  -> CPSC {c['recall_number']}")
        out(f"        look for: {c.get('look_for', '')[:160]}")
    if card.get("applied_memories"):
        out(f"  SHOP MEMORIES APPLIED ({len(card['applied_memories'])})")
        for m in card["applied_memories"]:
            out(f"    * {m['memory_id']}: {m.get('text', '')[:150]}")
    u = card.get("usage") or {}
    if u.get("model_calls"):
        out(f"  model usage: {u['model_calls']} classify calls for {u['items']} items | p50 {u['p50_item_latency_ms']} ms/item "
            f"(p90 {u['p90_item_latency_ms']}, mean {u['mean_call_latency_ms']} ms/call) | tokens {u['tokens_in']} in + "
            f"{u['tokens_out']} out | est. ${u['cost_usd']:.4f} at Tinker list price")
    for n in card.get("notes") or []:
        out(f"  note: {n}")
    out(f"  workflow: {card['workflow_id']}   memory: {card.get('memory_backend')}")


async def main_async(a) -> int:
    from agent.models import SweepInput
    from agent.runs import new_workflow_id, start_check_workflow
    from agent.workflows import InventoryCheckWorkflow, WeeklyRecallSweep

    client = await temporal_client()
    if a.shop == "sweep":
        wid = f"weekly-sweep-manual-{int(time.time())}"
        handle = await client.start_workflow(WeeklyRecallSweep.run, SweepInput(since=a.since), id=wid,
                                             task_queue=TASK_QUEUE)
        q = WeeklyRecallSweep.progress
    else:
        wid = await start_check_workflow(client, a.shop, [], a.corpus, workflow_id=new_workflow_id(a.shop))
        handle = client.get_workflow_handle(wid)
        q = InventoryCheckWorkflow.progress
    print(f"started {wid}")
    t0 = time.time()
    last = None
    task = asyncio.ensure_future(handle.result())
    while not task.done():
        await asyncio.sleep(a.every)
        try:
            p = await asyncio.wait_for(handle.query(q), timeout=3)
        except Exception:
            continue
        if p is None:
            continue
        snap = "\n".join(fmt_step(s.model_dump()) for s in p.steps)
        if snap != last:
            print(f"--- t+{time.time() - t0:5.1f}s")
            print(snap)
            last = snap
    res = task.result()
    p = await handle.query(q)
    print(f"--- t+{time.time() - t0:5.1f}s  workflow=completed")
    print("\n".join(fmt_step(s.model_dump()) for s in p.steps))
    if a.shop != "sweep":
        print_card(res)
    else:
        print(res)
        for cid in res.get("children", []):
            card = await client.get_workflow_handle(cid).result()
            print_card(card)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("shop", help="shop id from agent/shops.json, or 'sweep'")
    ap.add_argument("--corpus", choices=["A", "AB"], default=None)
    ap.add_argument("--since", default=None, help="sweep only: YYYY-MM-DD (default 7 days ago)")
    ap.add_argument("--every", type=float, default=0.7)
    setup_logging("run", "WARNING")
    sys.exit(asyncio.run(main_async(ap.parse_args())))


if __name__ == "__main__":
    main()
