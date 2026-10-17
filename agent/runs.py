"""Turn a Temporal workflow into the API's run shape:
    {workflow_id, workflow_type, shop_id, status, started_at, ended_at, card?, steps:[{name,status,attempt,
     started_at,ended_at,error?,note?}], workers?, resumed_after_crash?}

Sources merged (most authoritative last):
  1. the workflow's `progress` query (step list the workflow maintains itself)
  2. describe() pending activities -> live attempt number + last failure while an activity is retrying
  3. agent/state/runs/<safe_wid>.events.jsonl -> error text of attempts that later succeeded
Finished runs are cached to agent/state/runs/<safe_wid>.json (safe_name: schedule ids contain ':').
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from agent.config import RUNS_DIR, TASK_QUEUE, safe_name

STATUS = {1: "running", 2: "completed", 3: "failed", 4: "canceled", 5: "terminated", 6: "continued_as_new",
          7: "timed_out"}
STEP_OF_ACTIVITY = {"fetch_new_recalls": "fetch_new_recalls", "extract_spec": "extract_specs",
                    "load_spec_set": "load_specs", "load_inventory": "load_inventory",
                    "load_shop_memories": "load_shop_memories", "retrieve_candidates": "check_items",
                    "check_item": "check_items", "scan_ebay_store": "scan_ebay_store", "compose_card": "compose_card",
                    "publish_card": "publish_card"}
WORKFLOW_TYPES = ("InventoryCheckWorkflow", "WeeklyRecallSweep")


def new_workflow_id(shop_id: str) -> str:
    d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"check-{shop_id}-{d}-{secrets.token_hex(2)}"


def _events(wid: str) -> list[dict]:
    p = RUNS_DIR / f"{safe_name(wid)}.events.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _iso(ts) -> str | None:
    if ts is None:
        return None
    return ts.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _step_name(ev_step: str) -> str:
    base = ev_step.split(":", 1)[0]
    return {"check_item": "check_items", "extract_spec": "extract_specs"}.get(base, ev_step)


def polish(run: dict) -> dict:
    """Prefer the real failure text over the workflow's generic 'succeeded on attempt N' note."""
    for st in run.get("steps", []):
        errs = st.pop("attempt_errors", None) or []
        if errs and (not st.get("error") or st["error"].startswith("succeeded on attempt")):
            tail = f" -> succeeded on attempt {st['attempt']}" if st.get("status") == "completed" else ""
            st["error"] = (errs[0] + (f" (+{len(errs) - 1} more)" if len(errs) > 1 else "") + tail)[:300]
    return run


async def start_check_workflow(client, shop_id: str, items: list[dict], corpus: str | None = None,
                               workflow_id: str | None = None, task_queue: str | None = None) -> str:
    from agent.models import CheckInput, Item
    from agent.workflows import InventoryCheckWorkflow

    wid = workflow_id or new_workflow_id(shop_id)
    await client.start_workflow(InventoryCheckWorkflow.run,
                                CheckInput(shop_id=shop_id, items=[Item(**i) for i in items], corpus=corpus),
                                id=wid, task_queue=task_queue or TASK_QUEUE, memo={"shop_id": shop_id})
    return wid


async def get_run(client, wid: str, include_card: bool = True) -> dict:
    cache = RUNS_DIR / f"{safe_name(wid)}.json"
    if cache.exists():
        run = polish(json.loads(cache.read_text(encoding="utf-8")))
        if not include_card:
            run.pop("card", None)
        return run

    from agent.workflows import InventoryCheckWorkflow

    handle = client.get_workflow_handle(wid)
    desc = await handle.describe()
    status = STATUS.get(int(desc.status or 1), "running") if desc.status else "running"
    run: dict = {"workflow_id": wid, "workflow_type": desc.workflow_type, "shop_id": None, "status": status,
                 "started_at": _iso(desc.start_time), "ended_at": _iso(desc.close_time), "steps": []}
    try:
        run["shop_id"] = (await desc.memo()).get("shop_id")
    except Exception:
        pass
    prog = None
    try:  # both workflow types expose the same `progress` query
        prog = await handle.query(InventoryCheckWorkflow.progress, rpc_timeout=timedelta(seconds=3))
    except Exception as e:  # no worker yet / first workflow task not run
        run["note"] = f"progress unavailable ({type(e).__name__}) - waiting for a worker"
    if prog is not None:
        run["shop_id"] = prog.shop_id or run["shop_id"]
        run["steps"] = [s.model_dump() for s in prog.steps]
        if prog.children:
            run["children"] = prog.children
        if prog.card is not None:
            run["card"] = prog.card

    by_step: dict[str, dict] = {s["name"]: s for s in run["steps"]}
    for pa in desc.raw_description.pending_activities:
        name = STEP_OF_ACTIVITY.get(pa.activity_type.name)
        s = by_step.get(name or "")
        if s is None:
            continue
        s["attempt"] = max(s.get("attempt") or 0, pa.attempt)
        if pa.attempt > 1 and s["status"] == "running":
            s["status"] = "retrying"
            if pa.HasField("last_failure"):
                s["error"] = pa.last_failure.message[:300]

    for ev in _events(wid):
        if ev.get("kind") != "error":
            continue
        s = by_step.get(_step_name(ev["step"]))
        if s is None:
            continue
        s.setdefault("attempt_errors", [])
        if len(s["attempt_errors"]) < 5:
            s["attempt_errors"].append(f"attempt {ev['attempt']}: {ev['msg']}"[:240])

    if status == "completed" and "card" not in run and desc.workflow_type == "InventoryCheckWorkflow":
        try:
            run["card"] = await handle.result()
        except Exception:
            pass
    if status != "running":
        try:  # which worker processes touched this run? >1 means it survived a worker crash/restart
            from temporalio.api.enums.v1 import EventType

            ids: list[str] = []
            hist = await handle.fetch_history()
            for ev in hist.events:
                if ev.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_STARTED:
                    ident = ev.workflow_task_started_event_attributes.identity
                elif ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
                    ident = ev.activity_task_started_event_attributes.identity
                else:
                    continue
                if ident and ident not in ids:
                    ids.append(ident)
            run["workers"] = ids
            run["resumed_after_crash"] = len(ids) > 1
            run["history_events"] = len(hist.events)
            if run["resumed_after_crash"]:
                for st in run["steps"]:
                    if (st.get("attempt") or 0) > 1 and not st.get("attempt_errors"):
                        st["error"] = ("worker crashed mid-step; in-flight activities resumed on a fresh worker "
                                       "(finished ones kept from event history)")
        except Exception:
            pass
    polish(run)
    if status in ("completed", "failed", "terminated", "canceled", "timed_out"):
        try:
            cache.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    if not include_card:
        run.pop("card", None)
    return run


async def list_runs(client, limit: int = 20) -> list[dict]:
    out = []
    q = " OR ".join(f'WorkflowType="{t}"' for t in WORKFLOW_TYPES)
    async for wf in client.list_workflows(q, limit=limit):
        try:
            out.append(await get_run(client, wf.id, include_card=True))  # api._summary() swaps the card for counts
        except Exception as e:
            out.append({"workflow_id": wf.id, "workflow_type": wf.workflow_type,
                        "status": STATUS.get(int(wf.status or 1), "unknown"), "steps": [], "note": type(e).__name__})
        if len(out) >= limit:
            break
    return out
