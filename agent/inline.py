"""Degraded mode: run the InventoryCheck pipeline in-process when no Temporal server is reachable.

Same steps and card as the workflow but NOT durable (no retries across process death). Used only by the API
so a static/free deploy still answers POST /api/check. Clearly labelled `"mode": "inline (no Temporal)"`.
"""
from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime, timezone

from agent import backboard_memory, pipeline
from agent.activities import write_card
from agent.config import RUNS_DIR, load_inventory, safe_name
from agent.models import ComposeInput, Item, StoreScan


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(shop_id: str) -> str:
    return f"local-{shop_id}-{datetime.now(timezone.utc):%Y-%m-%d}-{secrets.token_hex(2)}"


def _save(run: dict) -> None:
    (RUNS_DIR / f"{safe_name(run['workflow_id'])}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1),
                                                                    encoding="utf-8")


STEPS = ["load_specs", "load_shop_memories", "check_items", "scan_ebay_store", "compose_card", "publish_card"]


def init_run(wid: str, shop_id: str) -> dict:
    run = {"workflow_id": wid, "workflow_type": "InventoryCheckWorkflow", "shop_id": shop_id, "status": "running",
           "started_at": _ts(), "ended_at": None, "mode": "inline (no Temporal)",
           "steps": [{"name": n, "status": "pending", "attempt": 0, "started_at": None, "ended_at": None}
                     for n in STEPS]}
    _save(run)
    return run


def run_inline(wid: str, shop_id: str, items: list[dict], corpus: str | None = None) -> dict:
    run = json.loads((RUNS_DIR / f"{safe_name(wid)}.json").read_text(encoding="utf-8"))
    steps = {s["name"]: s for s in run["steps"]}

    def start(n):
        steps[n].update(status="running", attempt=1, started_at=_ts())
        _save(run)

    def done(n, note=None, status="completed", error=None):
        steps[n].update(status=status, ended_at=_ts())
        if note:
            steps[n]["note"] = note
        if error:
            steps[n]["error"] = error
        _save(run)

    try:
        its = [Item(**i) for i in (items or load_inventory(shop_id))]
        start("load_specs")
        ss = pipeline.load_spec_set(shop_id, corpus)
        done("load_specs", f"{ss.count} recalls (corpus {ss.corpus}); {ss.source}")
        start("load_shop_memories")
        mem: dict[str, list] = {}
        try:
            for i, it in enumerate(its):
                hits = asyncio.run(backboard_memory.search(shop_id, pipeline.memory_query(it), limit=3))
                if hits:
                    mem[str(i)] = hits
            backboard_memory.merge_listed(mem, [pipeline.item_text(it) for it in its],
                                          asyncio.run(backboard_memory.list_memories(shop_id)))
            done("load_shop_memories", f"backend={backboard_memory.backend()}")
        except Exception as e:
            done("load_shop_memories", status="failed", error=type(e).__name__)
        start("check_items")
        cands = pipeline.retrieve(its, ss, 3)
        results = [pipeline.check_one(shop_id, i, it, cands[i], mem.get(str(i), [])) for i, it in enumerate(its)]
        done("check_items", f"{len(results)}/{len(its)} items")
        start("scan_ebay_store")
        done("scan_ebay_store", "inline mode: store scan runs only in the Temporal worker", status="skipped")
        start("compose_card")
        card = pipeline.compose(ComposeInput(shop_id=shop_id, shop_name="", week_of=ss.week_of, new_recalls=ss.new_recalls,
                                             results=results, store=StoreScan(source="skipped (inline)", skipped=True),
                                             workflow_id=wid, generated_at=_ts(), model="",
                                             notes=["inline mode (Temporal unreachable): not durable"],
                                             memory_backend=backboard_memory.backend()))
        done("compose_card")
        start("publish_card")
        write_card(card)
        done("publish_card", card["id"])
        run.update(status="completed", ended_at=_ts(), card=card)
    except Exception as e:
        run.update(status="failed", ended_at=_ts(), error=f"{type(e).__name__}: {e}"[:300])
    _save(run)
    return run
