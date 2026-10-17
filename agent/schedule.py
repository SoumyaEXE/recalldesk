"""WeeklyRecallSweep as a Temporal Schedule: Thursdays 14:00 America/New_York (CPSC posts recalls on Thursdays).

    python -m agent.schedule create [--shops little-loop flip-garage] [--cron "0 14 * * 4"] [--tz America/New_York]
    python -m agent.schedule create --if-missing    # idempotent (used by `python -m agent.dev --schedule`)
    python -m agent.schedule trigger                # run it right now (demo)
    python -m agent.schedule describe
    python -m agent.schedule delete

The Schedule lives in the Temporal server, not in our process: if every worker is down at 14:00 on Thursday the
run starts as soon as a worker comes back (catchup window 1 day). Overlap policy SKIP. Then it goes quiet until
next Thursday.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from agent.config import TASK_QUEUE, setup_logging, temporal_client

SCHEDULE_ID = "recalldesk-weekly-sweep"
CRON = "0 14 * * 4"
TZ = "America/New_York"


async def main_async(a) -> None:
    from temporalio.client import (Schedule, ScheduleActionStartWorkflow, ScheduleOverlapPolicy, SchedulePolicy,
                                   ScheduleSpec, ScheduleState)
    from temporalio.service import RPCError

    from agent.models import SweepInput
    from agent.workflows import WeeklyRecallSweep

    client = await temporal_client()
    sid = a.id
    if a.cmd == "create":
        if a.if_missing:
            try:
                await client.get_schedule_handle(sid).describe()
                print(f"schedule {sid} already exists")
                return
            except RPCError:
                pass
        handle = await client.create_schedule(
            sid,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    WeeklyRecallSweep.run, SweepInput(shops=a.shops), id="weekly-sweep", task_queue=TASK_QUEUE),
                spec=ScheduleSpec(cron_expressions=[a.cron], time_zone_name=a.tz),
                policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP, catchup_window=timedelta(days=1)),
                state=ScheduleState(note="RecallDesk: fetch this week's CPSC recalls, re-check every watched shop"),
            ),
        )
        desc = await handle.describe()
        print(f"created schedule {sid}: cron '{a.cron}' ({a.tz}) shops={a.shops or 'all watched'}")
        print("next runs:", ", ".join(t.isoformat() for t in desc.info.next_action_times[:3]))
    elif a.cmd == "trigger":
        await client.get_schedule_handle(sid).trigger(overlap=ScheduleOverlapPolicy.ALLOW_ALL)
        print(f"triggered {sid} - see GET /api/runs or the Temporal UI (http://localhost:8233)")
    elif a.cmd == "describe":
        d = await client.get_schedule_handle(sid).describe()
        print(f"schedule {sid}: paused={d.schedule.state.paused} actions_taken={d.info.num_actions}")
        cal = d.schedule.spec.calendars[0] if d.schedule.spec.calendars else None
        print("spec:", (f"day_of_week={cal.day_of_week} hour={cal.hour}" if cal else d.schedule.spec.cron_expressions),
              d.schedule.spec.time_zone_name)
        print("next runs:", ", ".join(t.isoformat() for t in d.info.next_action_times[:3]))
        for r in d.info.recent_actions[-5:]:
            print("recent:", r.started_at.isoformat(), getattr(r.action, "workflow_id", ""))
    elif a.cmd == "delete":
        await client.get_schedule_handle(sid).delete()
        print(f"deleted {sid}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["create", "trigger", "describe", "delete"])
    ap.add_argument("--id", default=SCHEDULE_ID)
    ap.add_argument("--shops", nargs="*", default=[])
    ap.add_argument("--cron", default=CRON, help="default: Thursdays 14:00")
    ap.add_argument("--tz", default=TZ)
    ap.add_argument("--if-missing", action="store_true")
    setup_logging("schedule", "WARNING")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
