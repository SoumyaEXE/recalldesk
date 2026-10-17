"""Durability demo: hard-kill the worker in the middle of an inventory check, start a fresh one, prove from
Temporal's event history that nothing finished was re-run.

    python -m agent.demo_crash                          # little-loop, kill after 18 items
    python -m agent.demo_crash --shop flip-garage --kill-after 10 --delay 1.2

Needs a Temporal server on TEMPORAL_ADDRESS (starts a throwaway dev server itself if none is running).
The worker is a real separate OS process killed with taskkill /F (Windows) / SIGKILL - no graceful shutdown.
Uses a private task queue so no other worker (e.g. the one from `python -m agent.dev`) can steal the work.
The transcript is saved to agent/demo_logs/04_crash_resume.txt.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import threading
import time
from datetime import timezone

from agent.config import DEMO_LOGS, ROOT, TEMPORAL_ADDRESS, setup_logging, temporal_client

T0 = time.time()
DEMO_QUEUE = f"recalldesk-demo-crash-{os.getpid()}"
REAL_PID: dict[str, str] = {}
LINES: list[str] = []
_lock = threading.Lock()


def emit(line: str) -> None:
    with _lock:
        LINES.append(line)
        print(line, flush=True)


def say(msg: str = "") -> None:
    emit(f"[demo t+{time.time() - T0:5.1f}s] {msg}" if msg else "")


def spawn_worker(tag: str, delay: float) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", RECALLDESK_CHECK_DELAY=str(delay),
               RECALLDESK_CHAOS="0", RECALLDESK_TASK_QUEUE=DEMO_QUEUE, RECALLDESK_LOG_LEVEL="INFO")
    p = subprocess.Popen([sys.executable, "-m", "agent.worker"], cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

    def pump():
        for line in p.stdout:  # type: ignore[union-attr]
            if "worker pid=" in line:
                REAL_PID[tag] = line.split("worker pid=")[1].split()[0]
            emit(f"    {tag} | {line.rstrip()}")

    threading.Thread(target=pump, daemon=True).start()
    return p


def hard_kill(p: subprocess.Popen) -> None:
    if os.name == "nt":  # kill the venv launcher AND the real interpreter it spawned
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()
    p.wait(timeout=10)


async def progress(handle):
    from agent.workflows import InventoryCheckWorkflow

    try:
        return await asyncio.wait_for(handle.query(InventoryCheckWorkflow.progress), timeout=2)
    except Exception:
        return None


async def history_stats(handle, crash_ts: float) -> dict:
    from temporalio.api.enums.v1 import EventType

    hist = await handle.fetch_history()
    sched: dict[int, tuple[str, str]] = {}  # event id -> (activity type, activity id)
    before = after = retried = n = 0
    per_activity_completions: dict[str, int] = {}
    for ev in hist.events:
        n += 1
        if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            a = ev.activity_task_scheduled_event_attributes
            sched[ev.event_id] = (a.activity_type.name, a.activity_id)
        elif ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
            a = ev.activity_task_started_event_attributes
            if sched.get(a.scheduled_event_id, ("",))[0] == "check_item" and a.attempt > 1:
                retried += 1
        elif ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
            a = ev.activity_task_completed_event_attributes
            typ, aid = sched.get(a.scheduled_event_id, ("", ""))
            per_activity_completions[aid] = per_activity_completions.get(aid, 0) + 1
            if typ != "check_item":
                continue
            t = ev.event_time.ToDatetime().replace(tzinfo=timezone.utc).timestamp()
            if t < crash_ts:
                before += 1
            else:
                after += 1
    n_check = sum(1 for t, _ in sched.values() if t == "check_item")
    ids = [aid for t, aid in sched.values() if t == "check_item"]
    return {"events": n, "scheduled": n_check, "distinct": len(set(ids)), "before": before, "after": after,
            "retried": retried, "completed_twice": sum(1 for v in per_activity_completions.values() if v > 1)}


async def main_async(a) -> int:
    from agent.ml_bridge import describe
    from agent.run_check import fmt_step, print_card
    from agent.runs import get_run, new_workflow_id, start_check_workflow

    env = None
    try:
        client = await temporal_client()
        await client.count_workflows()
    except Exception:
        from temporalio.testing import WorkflowEnvironment

        say("no Temporal server found - starting a throwaway local dev server")
        env = await WorkflowEnvironment.start_local(port=int(TEMPORAL_ADDRESS.rsplit(":", 1)[1]))
        client = await temporal_client()

    say(f"Temporal server: {TEMPORAL_ADDRESS}  (the event history is the source of truth, not the worker)")
    m = describe()
    say(f"model: {m['provider']} / {m['model']}" + (f" + {a.delay}s simulated latency per item" if a.delay else ""))
    say("1) starting worker #1")
    w1 = spawn_worker("worker#1", a.delay)
    await asyncio.sleep(4)

    wid = new_workflow_id(a.shop) + "-crashdemo"
    await start_check_workflow(client, a.shop, [], None, workflow_id=wid, task_queue=DEMO_QUEUE)
    handle = client.get_workflow_handle(wid)
    say(f"2) started InventoryCheckWorkflow id={wid} shop={a.shop} (whole inventory)")

    cs = p = None
    while True:
        p = await progress(handle)
        cs = next((s for s in p.steps if s.name == "check_items"), None) if p else None
        if cs and cs.note and cs.status == "running" and "/" in cs.note.split()[0]:
            done, total = (int(x) for x in cs.note.split()[0].split("/"))
            if done >= a.kill_after or (total and done >= total - 3):
                break
        await asyncio.sleep(0.2)
    say("")
    say(f"3) progress before crash: check_items {cs.note}")
    for s in p.steps:
        emit("   " + fmt_step(s.model_dump()).replace("\n", "\n   "))
    say("")
    say(f"4) [CRASH] hard-killing worker #1 (pid {REAL_PID.get('worker#1', w1.pid)}) in the middle of check_items "
        "- no graceful shutdown")
    crash_ts = time.time()
    hard_kill(w1)
    say("   worker #1 is dead. No process is running the agent right now.")
    desc = await handle.describe()
    pend = list(desc.raw_description.pending_activities)
    say(f"   Temporal says: status={desc.status.name if desc.status else '?'}, "
        f"history length={desc.raw_description.workflow_execution_info.history_length}, "
        f"{len(pend)} check_item activities in flight (orphaned)")
    say(f"   waiting {a.downtime}s of downtime...")
    await asyncio.sleep(a.downtime)

    say("")
    say("5) starting worker #2 (fresh process, no memory of worker #1)")
    w2 = spawn_worker("worker#2", a.delay)
    say("   it replays the event history: finished activities are NOT re-run; orphaned in-flight ones are")
    say("   retried once their 10s heartbeat timeout fires.")
    card = await handle.result()
    await asyncio.sleep(0.5)
    p = await progress(handle)
    say("")
    say("6) workflow COMPLETED after the crash:")
    if p:
        for s in p.steps:
            emit("   " + fmt_step(s.model_dump()).replace("\n", "\n   "))
    st = await history_stats(handle, crash_ts)
    say("")
    say("7) proof from Temporal event history:")
    say(f"   check_item activities scheduled     : {st['scheduled']} ({st['distinct']} distinct ids - one per item, "
        f"none scheduled twice)")
    say(f"   completed before the crash          : {st['before']}  (kept; NOT re-run by worker #2)")
    say(f"   completed after restart             : {st['after']}")
    say(f"   activities completed twice          : {st['completed_twice']}")
    say(f"   check_item attempts >= 2 (retried)  : {st['retried']}  (were in flight when worker #1 died)")
    say(f"   total history events                : {st['events']}")
    print_card(card, out=lambda s: emit("   " + s))
    run = await get_run(client, wid)  # caches the run record (steps + workers) for /api/runs
    say(f"   workers that touched this run: {run.get('workers')}  resumed_after_crash={run.get('resumed_after_crash')}")
    hard_kill(w2)
    if env:
        await env.shutdown()
    ok = st["scheduled"] == st["distinct"] and st["completed_twice"] == 0 and st["before"] + st["after"] == st["distinct"]
    say(f"RESULT: {'PASS' if ok else 'FAIL'} - no activity ran to completion twice")
    out = DEMO_LOGS / a.out
    out.write_text(f"$ python -m agent.demo_crash --shop {a.shop} --kill-after {a.kill_after} --delay {a.delay}"
                   f" --out {a.out}\n"
                   + "\n".join(LINES) + "\n", encoding="utf-8")
    print(f"transcript saved to {out}")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shop", default="little-loop")
    ap.add_argument("--kill-after", type=int, default=18, help="kill once this many items are checked")
    ap.add_argument("--delay", type=float, default=None,
                    help="simulated model latency per item (s); default 0 with a real model, 1.2 with heuristic")
    ap.add_argument("--downtime", type=float, default=3.0)
    ap.add_argument("--out", default="04_crash_resume.txt", help="transcript file name under agent/demo_logs/")
    setup_logging("demo", "WARNING")
    a = ap.parse_args()
    if a.delay is None:
        from agent.ml_bridge import provider

        a.delay = 0.0 if provider() != "heuristic" else 1.2
    sys.exit(asyncio.run(main_async(a)))


if __name__ == "__main__":
    main()
