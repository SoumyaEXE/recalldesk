"""Shared helpers for the RecallDesk ML pipeline: paths, env, jsonl io, pricing/spend, Tinker setup.

Importing this module is cheap (stdlib + pydantic). Nothing here needs a key at import time.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = Path(os.environ["RECALLDESK_DATA"]) if os.environ.get("RECALLDESK_DATA") else ROOT / "data"  # override for smoke tests
RECALLS = DATA / "recalls"
SPECS = DATA / "specs"
SERP = DATA / "serp"          # raw SerpApi JSON (gitignored; contains seller usernames)
LISTINGS = DATA / "listings"
PAIRS = DATA / "pairs"
SPLITS = DATA / "splits"
GOLD = DATA / "gold"
LABELED = DATA / "labeled"
RESULTS = Path(os.environ["RECALLDESK_RESULTS"]) if os.environ.get("RECALLDESK_RESULTS") else ROOT / "ml" / "results"

# ---------------------------------------------------------------------------------------------
# Models (verified against https://tinker-docs.thinkingmachines.ai/tinker/models.json on 2026-10-17):
# Qwen3.5-397B-A17B and Qwen3.5-4B are offered with no deprecation note. Models marked
# "Retiring October 23" (Nemotron-3-Nano-30B, Qwen3.6-27B, DeepSeek-V3.1) are avoided.
# Teacher and student share the Qwen3.5 tokenizer / chat template (renderer qwen3_5_disable_thinking).
# ---------------------------------------------------------------------------------------------
TEACHER_MODEL = os.environ.get("RECALLDESK_TEACHER", "Qwen/Qwen3.5-397B-A17B")
STUDENT_MODEL = os.environ.get("RECALLDESK_STUDENT", "Qwen/Qwen3.5-4B")
RENDERER_NAME = os.environ.get("RECALLDESK_RENDERER", "qwen3_5_disable_thinking")
LORA_MODEL_NAME = "qwen3.5-4b-recalldesk-lora"
TINKER_OAI_BASE_URL = "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1"

# $/1M tokens, snapshot of https://tinker-docs.thinkingmachines.ai/tinker/models.json (2026-10-17)
PRICING = {
    "Qwen/Qwen3.5-397B-A17B": {"prefill": 1.65, "sample": 7.50, "train": 6.60},
    "Qwen/Qwen3.5-4B": {"prefill": 0.33, "sample": 1.005, "train": 0.737},
    "Qwen/Qwen3.5-9B": {"prefill": 0.30, "sample": 0.807, "train": 1.463},
    "Qwen/Qwen3-8B": {"prefill": 0.195, "sample": 0.60, "train": 0.44},
    "Qwen/Qwen3.6-35B-A3B": {"prefill": 0.45, "sample": 1.335, "train": 1.177},
    "openai/gpt-oss-120b": {"prefill": 0.33, "sample": 0.84, "train": 0.737},
    "openai/gpt-oss-20b": {"prefill": 0.18, "sample": 0.45, "train": 0.396},
}
SERPAPI_NOTE = "SerpApi searches are counted, not priced (plan-dependent)."


def price_of(model: str) -> dict[str, float]:
    return PRICING.get(model.split(":")[0], {"prefill": 0.0, "sample": 0.0, "train": 0.0})


def sample_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = price_of(model)
    return (prompt_tokens * p["prefill"] + completion_tokens * p["sample"]) / 1e6


# ------------------------------------------------------------------------------------- env / io
_ENV_LOADED = False


def load_env() -> None:
    """Load repo-root .env (python-dotenv if installed, else a tiny parser). Never prints values."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    path = ROOT / ".env"
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv as _ld

        _ld(path, override=False)
        return
    except ImportError:
        pass
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


KEY_HELP = {
    "TINKER_API_KEY": "https://tinker-console.thinkingmachines.ai",
    "SERPAPI_API_KEY": "https://serpapi.com/manage-api-key",
    "BACKBOARD_API_KEY": "https://app.backboard.io",
}


def has_key(name: str) -> bool:
    load_env()
    return bool(os.environ.get(name, "").strip())


def require_key(name: str, what: str = "") -> str:
    load_env()
    v = os.environ.get(name, "").strip()
    if not v:
        raise SystemExit(
            f"{name} is not set{' (needed for ' + what + ')' if what else ''}. Put {name}=... in the repo-root .env "
            f"(gitignored) and rerun. Get one at {KEY_HELP.get(name, 'the provider console')}.")
    return v


def utf8_stdout() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # tolerate a torn last line from an interrupted run
    return out


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def seller_hash(username: str | None) -> str | None:
    return None if not username else "s_" + sha1(username.strip().lower())[:6]


def percentile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ------------------------------------------------------------------------------------ loaders
def load_recalls(corpus: str = "AB") -> list[dict]:
    rows = read_jsonl(RECALLS / "recalls.jsonl")
    if not rows:
        raise SystemExit("data/recalls/recalls.jsonl missing - run: python -m ml.fetch_recalls")
    want = set(corpus.upper())
    return [r for r in rows if want & set(r.get("corpus", []))]


def specs_path() -> Path:
    """Teacher specs (data/specs/specs.jsonl) if present, else the heuristic ones (for display/logging)."""
    p = SPECS / "specs.jsonl"
    return p if p.exists() else SPECS / "specs.heuristic.jsonl"


def load_specs(path: Path | None = None) -> dict[str, dict]:
    """Heuristic specs as the base, overridden per recall by teacher specs where they exist."""
    if path is not None:
        return {r["recall_number"]: r for r in read_jsonl(path)}
    out = {r["recall_number"]: r for r in read_jsonl(SPECS / "specs.heuristic.jsonl")}
    out.update({r["recall_number"]: r for r in read_jsonl(SPECS / "specs.jsonl")})
    return out


def load_listings() -> dict[str, dict]:
    return {r["listing_id"]: r for r in read_jsonl(LISTINGS / "listings.jsonl")}


# ------------------------------------------------------------------------------------- spend
def spend_stage(stage: str) -> dict:
    p = RESULTS / "spend.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("stages", {}).get(stage) or {}
    except Exception:  # noqa: BLE001
        return {}


def add_spend(stage: str, entry: dict) -> None:
    """Accumulate token / $ estimates per stage into ml/results/spend.json."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / "spend.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"stages": {}}
    entry = {**entry, "at": now_iso()}
    data["stages"][stage] = entry
    data["total_est_usd"] = round(sum(s.get("est_usd", 0.0) for s in data["stages"].values()), 4)
    data["serpapi_searches_spent"] = sum(s.get("searches_spent", 0) for s in data["stages"].values())
    data["note"] = ("Tinker $ = token counts x list prices (models.json snapshot 2026-10-17); not an invoice. "
                    + SERPAPI_NOTE)
    write_json(p, data)


# ------------------------------------------------------------------------------------- tinker
def make_renderer(model: str):
    """Cookbook tokenizer + renderer for a Tinker model (non-thinking Qwen3.5 chat template)."""
    from tinker_cookbook import renderers
    from tinker_cookbook.tokenizer_utils import get_tokenizer

    tok = get_tokenizer(model)
    return tok, renderers.get_renderer(RENDERER_NAME, tok, model_name=model)


def tinker_model_path() -> str | None:
    load_env()
    p = RESULTS / "model_path.txt"
    return os.environ.get("RECALLDESK_TINKER_MODEL_PATH", "").strip() or (
        p.read_text(encoding="utf-8").strip() if p.exists() else None) or None
