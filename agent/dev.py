"""One-command dev stack: Temporal dev server + worker + FastAPI.

    python -m agent.dev                 # server :7233, Temporal UI http://localhost:8233, API http://localhost:8000
    python -m agent.dev --server-only   # just the Temporal dev server (for demo_crash / manual workers)
    python -m agent.dev --no-server     # worker + API against an existing TEMPORAL_ADDRESS (e.g. Temporal Cloud)
    python -m agent.dev --schedule      # also create the Thursday 14:00 America/New_York Schedule if missing

The dev server is the official Temporal CLI dev server, downloaded once by
temporalio.testing.WorkflowEnvironment.start_local() and persisted to agent/state/temporal-dev.db.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import subprocess
import sys

from agent.config import ROOT, STATE_DIR, setup_logging

log = logging.getLogger("recalldesk")


def port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


async def start_dev_server(port: int = 7233, ui_port: int = 8233):
    from temporalio.testing import WorkflowEnvironment

    log.info("starting Temporal dev server on :%d (UI http://localhost:%d) - first run downloads the CLI...",
             port, ui_port)
    env = await WorkflowEnvironment.start_local(
        port=port, ui=True, ui_port=ui_port,
        dev_server_database_filename=str(STATE_DIR / "temporal-dev.db"),
        dev_server_log_level="error",
    )
    log.info("Temporal dev server ready on localhost:%d", port)
    return env


def spawn(args: list[str], name: str) -> subprocess.Popen:
    log.info("spawning %s: %s", name, " ".join(args[1:]))
    return subprocess.Popen(args, cwd=str(ROOT), env=os.environ.copy())


async def main_async(a) -> None:
    env = None
    host, port = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233").rsplit(":", 1)
    if not a.no_server:
        if port_open("127.0.0.1", int(port)):
            log.info("something is already listening on :%s - reusing it as the Temporal server", port)
        else:
            env = await start_dev_server(int(port), a.ui_port)
    procs: list[subprocess.Popen] = []
    if not a.server_only:
        if not a.no_worker:
            procs.append(spawn([sys.executable, "-m", "agent.worker"], "worker"))
        if not a.no_api:
            procs.append(spawn([sys.executable, "-m", "uvicorn", "agent.api:app", "--host", a.host,
                                "--port", str(a.api_port), "--log-level", "warning"], "api"))
            log.info("API on http://localhost:%d  (try /api/health, /api/recalls, POST /api/check)", a.api_port)
    if a.schedule or os.environ.get("RECALLDESK_SCHEDULE_ON_BOOT") == "1":
        subprocess.Popen([sys.executable, "-m", "agent.schedule", "create", "--if-missing"], cwd=str(ROOT),
                         env=os.environ.copy())
    try:
        while True:
            await asyncio.sleep(1)
            for p in list(procs):
                if p.poll() is not None:
                    log.warning("child pid=%d exited with %s", p.pid, p.returncode)
                    procs.remove(p)
            if not procs and not env and not a.server_only:
                return
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for p in procs:
            p.terminate()
        if env:
            await env.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-only", action="store_true")
    ap.add_argument("--no-server", action="store_true")
    ap.add_argument("--no-worker", action="store_true")
    ap.add_argument("--no-api", action="store_true")
    ap.add_argument("--schedule", action="store_true", help="create the weekly Schedule if missing")
    ap.add_argument("--api-port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--ui-port", type=int, default=8233)
    setup_logging("dev")
    try:
        asyncio.run(main_async(ap.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
