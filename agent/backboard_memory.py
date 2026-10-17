"""Per-shop correction memory: Backboard (https://app.backboard.io/api) when BACKBOARD_API_KEY is set,
else a local JSON store (agent/state/memories/<shop>.json), clearly labelled `local`.

    await add_correction(shop_id, text, metadata={recall_number, correct_verdict, item, note}) -> memory_id
    await search(shop_id, query, limit=5) -> [MemoryHit]       semantic search (Backboard) / token overlap (local)
    await list_memories(shop_id) -> [MemoryHit]
    applies_to(hit, recall_number, item_text) -> bool         the CODE rule that lets a memory override a verdict

One Backboard assistant per shop ("recalldesk-<shop_id>"). We only use the explicit memory endpoints
(POST/GET /assistants/{id}/memories, POST .../memories/search) - never chat with memory="Auto", which writes
model-generated summaries into memory (lesson from a previous project). Endpoints mirror backboard-sdk 1.5.19.

Backboard may run a fact-extraction pass over added content, so every memory is also written to a local ledger
(agent/state/memories/<shop>.ledger.json) keyed by memory_id, and the content carries a machine-readable tag
"[recall=27027 verdict=no_match]" - metadata survives even if the service rewrites or drops it.

    python -m agent.backboard_memory seed little-loop      # add the demo correction (idempotent)
    python -m agent.backboard_memory list little-loop
    python -m agent.backboard_memory search little-loop "Nordi toddler tower"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any

import httpx

from agent.config import FIXTURES_SRC, MEMORY_DIR, STATE_DIR, safe_name
from agent.fallback import tokens
from agent.models import MemoryHit

log = logging.getLogger("recalldesk")

BASE = os.environ.get("BACKBOARD_BASE_URL", "https://app.backboard.io/api").rstrip("/")
_ASSISTANTS_FILE = STATE_DIR / "backboard_assistants.json"
_TAG = re.compile(r"\[recall=(\w+) verdict=(match|check|no_match)\]")
_ITEM = re.compile(r"^Shop correction: '(.+?)' (?:is NOT|IS|needs)")
FACT_PROMPT = ("Each message is a shop owner's correction to a product-recall check. Store it as ONE fact, verbatim, "
               "including the bracketed [recall=... verdict=...] tag. Do not summarize, merge or infer anything.")


def backend() -> str:
    return "backboard" if os.environ.get("BACKBOARD_API_KEY", "").strip() else "local (no BACKBOARD_API_KEY)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read(path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _write(path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def correction_text(item: str, recall_number: str, correct_verdict: str, note: str = "") -> str:
    say = {"no_match": "is NOT the recalled product", "match": "IS the recalled product (do not sell)",
           "check": "needs a label check"}[correct_verdict]
    return (f"Shop correction: '{item}' {say} for CPSC recall {recall_number}."
            + (f" {note.strip()}" if note and note.strip() else "") + f" [recall={recall_number} verdict={correct_verdict}]")


# ----------------------------------------------------------------------------------------- local
def _local_path(shop_id: str):
    return MEMORY_DIR / f"{safe_name(shop_id)}.json"


def _ledger_path(shop_id: str):
    return MEMORY_DIR / f"{safe_name(shop_id)}.ledger.json"


def _overlap_score(query: str, m: dict) -> float:
    q = set(tokens(query))
    d = set(tokens(m.get("text", "") + " " + str((m.get("metadata") or {}).get("item", ""))))
    return len(q & d) / (len(q) or 1)


# ------------------------------------------------------------------------------------- backboard
def _headers() -> dict:
    return {"X-API-Key": os.environ["BACKBOARD_API_KEY"].strip()}


async def _bb(client: httpx.AsyncClient, shop_id: str, method: str, suffix: str, **kw) -> httpx.Response:
    """Request against this shop's assistant. A 404 means the cached assistant id is stale (key/account changed,
    assistant deleted): drop it from the cache, find/create the assistant again, retry once."""
    for fresh in (False, True):
        aid = await _assistant_id(client, shop_id, fresh=fresh)
        r = await client.request(method, f"{BASE}/assistants/{aid}{suffix}", headers=_headers(), **kw)
        if r.status_code != 404 or fresh:
            r.raise_for_status()
            return r
        log.warning("[backboard] assistant %s for %s not found - looking it up again", aid, shop_id)
    raise AssertionError("unreachable")


async def _assistant_id(client: httpx.AsyncClient, shop_id: str, fresh: bool = False) -> str:
    cache = _read(_ASSISTANTS_FILE) or {}
    if shop_id in cache and not fresh:
        return cache[shop_id]
    name = f"recalldesk-{shop_id}"
    r = await client.get(f"{BASE}/assistants", params={"skip": 0, "limit": 100}, headers=_headers())
    r.raise_for_status()
    items = r.json()
    items = items.get("assistants", items) if isinstance(items, dict) else items
    aid = next((str(a.get("assistant_id") or a.get("id")) for a in items or [] if a.get("name") == name), None)
    if not aid:
        r = await client.post(f"{BASE}/assistants", headers=_headers(), json={
            "name": name, "description": f"RecallDesk correction memory for shop {shop_id}",
            "system_prompt": "You store recall-check corrections for one resale shop.",
            "custom_fact_extraction_prompt": FACT_PROMPT})
        r.raise_for_status()
        a = r.json()
        aid = str(a.get("assistant_id") or a.get("id"))
        log.info("[backboard] created assistant %s for shop %s", aid, shop_id)
    cache[shop_id] = aid
    _write(_ASSISTANTS_FILE, cache)
    return aid


def _hit_from(m: dict, ledger: dict, backend_name: str) -> MemoryHit:
    mid = str(m.get("id") or m.get("memory_id") or "")
    text = m.get("content") or m.get("memory") or m.get("text") or ""
    md = dict(m.get("metadata") or {})
    led = ledger.get(mid) or next((v for v in ledger.values() if v.get("text") == text), None)
    if led and not md.get("recall_number"):
        md = {**led.get("metadata", {}), **md}
    t = _TAG.search(text)
    if t and not md.get("recall_number"):
        md.update(recall_number=t.group(1), correct_verdict=t.group(2))
    # Backboard's search results carry no metadata: without the local ledger (another machine, a fresh deploy)
    # the item must come from the content itself, or applies_to() can never match.
    it = _ITEM.search(text)
    if it and not md.get("item"):
        md["item"] = it.group(1)
    return MemoryHit(memory_id=mid, text=text, metadata=md, score=m.get("score"), backend=backend_name)


# --------------------------------------------------------------------------------------- public
async def add_correction(shop_id: str, text: str, metadata: dict) -> tuple[str, str]:
    """Returns (memory_id, backend)."""
    metadata = {k: v for k, v in metadata.items() if v not in (None, "")}
    metadata.setdefault("shop_id", shop_id)
    metadata.setdefault("created_at", _now())
    if backend() == "backboard":
        async with httpx.AsyncClient(timeout=30) as client:
            r = await _bb(client, shop_id, "POST", "/memories", json={"content": text, "metadata": metadata})
            body = r.json() if r.content else {}
            mid = str(body.get("memory_id") or body.get("id") or "")
            op = body.get("operation_id")
            for _ in range(10):  # async add: poll the operation for the id (bounded, ~5s)
                if mid or not op:
                    break
                await asyncio.sleep(0.5)
                s = await client.get(f"{BASE}/assistants/memories/operations/{op}", headers=_headers())
                if s.status_code == 200:
                    ids = s.json().get("memory_ids") or []
                    if ids:
                        mid = str(ids[0] if not isinstance(ids[0], dict) else ids[0].get("id"))
            mid = mid or f"bb_op_{op or secrets.token_hex(4)}"
        led = _read(_ledger_path(shop_id)) or {}
        led[mid] = {"text": text, "metadata": metadata}
        _write(_ledger_path(shop_id), led)
        return mid, "backboard"
    rows = _read(_local_path(shop_id)) or []
    mid = f"local_{secrets.token_hex(5)}"
    rows.append({"memory_id": mid, "text": text, "metadata": metadata})
    _write(_local_path(shop_id), rows)
    return mid, backend()


async def list_memories(shop_id: str) -> list[MemoryHit]:
    if backend() == "backboard":
        async with httpx.AsyncClient(timeout=30) as client:
            r = await _bb(client, shop_id, "GET", "/memories")
            body = r.json()
            ms = body.get("memories", body) if isinstance(body, dict) else body
            led = _read(_ledger_path(shop_id)) or {}
            return [_hit_from(m, led, "backboard") for m in ms or []]
    return [MemoryHit(memory_id=m["memory_id"], text=m["text"], metadata=m.get("metadata") or {}, backend=backend())
            for m in _read(_local_path(shop_id)) or []]


async def search(shop_id: str, query: str, limit: int = 5, client: httpx.AsyncClient | None = None) -> list[MemoryHit]:
    if backend() == "backboard":
        own = client is None
        client = client or httpx.AsyncClient(timeout=30)
        try:
            r = await _bb(client, shop_id, "POST", "/memories/search", json={"query": query, "limit": limit})
            body = r.json()
            ms = body.get("memories", body.get("results", [])) if isinstance(body, dict) else body
            led = _read(_ledger_path(shop_id)) or {}
            return [_hit_from(m, led, "backboard") for m in ms or []]
        finally:
            if own:
                await client.aclose()
    rows = _read(_local_path(shop_id)) or []
    scored = sorted(((_overlap_score(query, m), m) for m in rows), key=lambda x: -x[0])
    return [MemoryHit(memory_id=m["memory_id"], text=m["text"], metadata=m.get("metadata") or {}, score=round(s, 3),
                      backend=backend()) for s, m in scored[:limit] if s >= 0.25]


def applies_to(hit: MemoryHit, recall_number: str, item_text: str) -> bool:
    """Code decides: same recall AND the remembered item is (nearly) this item."""
    md = hit.metadata or {}
    if str(md.get("recall_number", "")) != str(recall_number) or md.get("correct_verdict") not in (
            "match", "check", "no_match"):
        return False
    mem_item = set(tokens(str(md.get("item") or "")))
    if not mem_item:
        return False
    here = set(tokens(item_text))
    return len(mem_item & here) / len(mem_item) >= 0.6


# ------------------------------------------------------------------------------------------ seed
def seed_rows(shop_id: str) -> list[dict]:
    p = FIXTURES_SRC / "seed_memories.json"
    return [r for r in (_read(p) or []) if r.get("shop_id") == shop_id]


async def ensure_seeded(shop_id: str) -> int:
    """Add the demo correction(s) for a shop if it has no memories yet. Returns how many were added."""
    try:
        if await list_memories(shop_id):
            return 0
    except Exception as e:
        log.warning("[memory] could not list memories for %s (%s) - not seeding", shop_id, type(e).__name__)
        return 0
    n = 0
    for r in seed_rows(shop_id):
        text = correction_text(r["item"], r["recall_number"], r["correct_verdict"], r.get("note", ""))
        await add_correction(shop_id, text, {"recall_number": r["recall_number"], "correct_verdict": r["correct_verdict"],
                                             "item": r["item"], "note": r.get("note"), "seeded": True})
        n += 1
    return n


def main() -> None:
    from agent.config import setup_logging

    setup_logging("memory")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seed", "list", "search"])
    ap.add_argument("shop_id")
    ap.add_argument("query", nargs="?", default="")
    a = ap.parse_args()
    print(f"backend: {backend()}")
    if a.cmd == "seed":
        print(f"added {asyncio.run(ensure_seeded(a.shop_id))} seed memories")
    elif a.cmd == "list":
        for h in asyncio.run(list_memories(a.shop_id)):
            print(h.memory_id, "|", h.text, "|", h.metadata)
    else:
        for h in asyncio.run(search(a.shop_id, a.query)):
            print(h.score, h.memory_id, "|", h.text)


if __name__ == "__main__":
    main()
