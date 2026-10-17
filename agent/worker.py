"""Temporal worker: hosts WeeklyRecallSweep + InventoryCheckWorkflow + activities on task queue `recalldesk`.

    python -m agent.worker            # connects to TEMPORAL_ADDRESS (default localhost:7233)
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import timedelta

from agent.config import CHAOS, TASK_QUEUE, TEMPORAL_ADDRESS, load_shops, setup_logging, temporal_client
from agent.telemetry import init_sentry

log = logging.getLogger("recalldesk")


async def run_worker() -> None:
    from temporalio.worker import Worker

    from agent import backboard_memory, ml_bridge
    from agent.activities import ALL_ACTIVITIES
    from agent.workflows import InventoryCheckWorkflow, WeeklyRecallSweep

    for shop_id in load_shops():  # demo correction(s), only if the shop has no memories yet
        try:
            n = await backboard_memory.ensure_seeded(shop_id)
            if n:
                log.info("seeded %d demo memory(ies) for %s (backend=%s)", n, shop_id, backboard_memory.backend())
        except Exception as e:
            log.warning("memory seed for %s skipped: %s", shop_id, type(e).__name__)
    client = await temporal_client()
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[InventoryCheckWorkflow, WeeklyRecallSweep],
        activities=ALL_ACTIVITIES,
        max_concurrent_activities=16,
        # if a worker dies its sticky queue goes silent; fall back to the shared queue fast
        sticky_queue_schedule_to_start_timeout=timedelta(seconds=2),
    )
    d = ml_bridge.describe()
    log.info("worker pid=%d up: temporal=%s queue=%s provider=%s model=%s memory=%s chaos=%s sentry=%s", os.getpid(),
             TEMPORAL_ADDRESS, TASK_QUEUE, d.get("provider"), d.get("model"), backboard_memory.backend(),
             "ON" if CHAOS else "off", "on" if os.environ.get("SENTRY_DSN") else "off")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):  # Windows
            pass
    async with worker:
        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass


def main() -> None:
    setup_logging("worker")
    init_sentry("worker")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
