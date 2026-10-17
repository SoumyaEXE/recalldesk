"""Paths, env and shop config shared by every agent/ module.

Keys come from the repo-root .env (gitignored). Nothing here needs a key: with zero keys the agent runs the
heuristic provider, the local memory store and cached/fixture data, and lights up as keys arrive.
Never log key values.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parent
if str(ROOT) not in sys.path:  # make `shared` and `ml` importable however we're launched
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

# tinker_cookbook (if ml.infer pulls it in) imports transformers; keep worker logs readable.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# ----------------------------------------------------------------------------------------- paths
CACHE_DIR = AGENT_DIR / "cache"              # CPSC snapshots (committed: the zero-key demo data)
SERP_CACHE_DIR = ROOT / "data" / "serp"      # raw SerpApi JSON (gitignored, shared with ml.serp_scan)
STATE_DIR = AGENT_DIR / "state"              # runtime output (gitignored): temporal db, run logs, local memories
RUNS_DIR = STATE_DIR / "runs"
MEMORY_DIR = STATE_DIR / "memories"
CARDS_DIR = AGENT_DIR / "cards"              # published RecallCards: agent/cards/<safe_name>.json
DEMO_LOGS = AGENT_DIR / "demo_logs"
FIXTURES_SRC = AGENT_DIR / "fixtures_src"    # demo shop inventories + store snapshots (fictional shops)
FIXTURES_DIR = ROOT / "shared" / "fixtures"
DATA_DIR = ROOT / "data"
ML_RESULTS = ROOT / "ml" / "results"
SHOPS_FILE = AGENT_DIR / "shops.json"

CORPUS_A_START = "2026-07-18"

# ------------------------------------------------------------------------------------------- env
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
TEMPORAL_API_KEY = os.environ.get("TEMPORAL_API_KEY")  # Temporal Cloud (optional)
TASK_QUEUE = os.environ.get("RECALLDESK_TASK_QUEUE", "recalldesk")

CHAOS = os.environ.get("RECALLDESK_CHAOS", "0") not in ("", "0", "false", "False")
CHECK_DELAY_S = float(os.environ.get("RECALLDESK_CHECK_DELAY", "0"))  # simulated model latency (demo)

CPSC_BASE = "https://www.saferproducts.gov/RestWebServices/Recall"


def has_key(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


for _d in (CACHE_DIR, RUNS_DIR, MEMORY_DIR, CARDS_DIR, DEMO_LOGS):
    _d.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------------- temporal
_RUNTIME = None


def _runtime():
    """Quiet the Rust core's WARN lines (late completions of timed-out activities) unless debugging."""
    global _RUNTIME
    if _RUNTIME is None:
        from temporalio.runtime import LoggingConfig, Runtime, TelemetryConfig, TelemetryFilter

        level = "WARN" if os.environ.get("RECALLDESK_LOG_LEVEL", "").upper() == "DEBUG" else "ERROR"
        _RUNTIME = Runtime(telemetry=TelemetryConfig(
            logging=LoggingConfig(filter=TelemetryFilter(core_level=level, other_level="ERROR"))))
    return _RUNTIME


async def temporal_client():
    """Local dev server by default; Temporal Cloud if TEMPORAL_API_KEY is set."""
    from temporalio.client import Client
    from temporalio.contrib.pydantic import pydantic_data_converter

    kwargs = dict(namespace=TEMPORAL_NAMESPACE, data_converter=pydantic_data_converter, runtime=_runtime())
    if TEMPORAL_API_KEY:
        kwargs.update(api_key=TEMPORAL_API_KEY, tls=True)
    return await Client.connect(TEMPORAL_ADDRESS, **kwargs)


def setup_logging(component: str, level: str | None = None) -> None:
    import logging

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    lvl = getattr(logging, (level or os.environ.get("RECALLDESK_LOG_LEVEL", "INFO")).upper(), logging.INFO)
    logging.basicConfig(level=lvl, format=f"%(asctime)s.%(msecs)03d [{component}] %(message)s",
                        datefmt="%H:%M:%S", force=True)
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if lvl > logging.DEBUG:
        for noisy in ("temporalio.activity", "temporalio.workflow", "temporalio.worker._activity"):
            logging.getLogger(noisy).setLevel(logging.ERROR)


def safe_name(s: str) -> str:
    """Workflow ids from Schedules contain ':' (timestamps) - not allowed in Windows filenames."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


# ----------------------------------------------------------------------------------------- shops
SHOP_ALIASES = {"demo-shop": "little-loop"}  # the UI's DEMO_SHOP_ID


def resolve_shop_id(shop_id: str) -> str:
    return SHOP_ALIASES.get(shop_id, shop_id)


def load_shops() -> dict[str, dict]:
    if not SHOPS_FILE.exists():
        return {}
    return {s["shop_id"]: s for s in json.loads(SHOPS_FILE.read_text(encoding="utf-8"))}


def get_shop(shop_id: str) -> dict:
    shop_id = resolve_shop_id(shop_id)
    return load_shops().get(shop_id) or {"shop_id": shop_id, "shop_name": shop_id, "watched": False}


def load_inventory(shop_id: str) -> list[dict]:
    """Shop inventory as API items: [{name, brand?, model?, notes?}]."""
    shop = get_shop(resolve_shop_id(shop_id))
    path = shop.get("inventory_csv")
    if not path:
        return []
    p = (AGENT_DIR / path) if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            item = {k: (row.get(k) or "").strip() for k in ("name", "brand", "model", "notes")}
            if item["name"]:
                out.append({k: v for k, v in item.items() if v or k == "name"})
    return out
