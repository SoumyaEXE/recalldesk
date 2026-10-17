"""RecallDesk API (FastAPI). Endpoints exactly as in CONTRACT.md (+ a few read-only extras marked "extra").

    uvicorn agent.api:app --port 8000          (or: python -m agent.dev)

Data sources, in order:
  /api/recalls        data/recalls/recalls.jsonl + data/specs/*.jsonl -> agent/cache CPSC snapshot -> shared/fixtures
  /api/scan, /eval    ml/results/*.json -> shared/fixtures/*.json
  /api/check, cards   Temporal (TEMPORAL_ADDRESS). If Temporal is unreachable, POST /api/check runs the same
                      pipeline inline (non-durable, labelled "mode": "inline (no Temporal)").
  /api/shops/*        Backboard memories (BACKBOARD_API_KEY) -> local JSON store (labelled)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import backboard_memory, inline, ml_bridge
from agent.config import (CARDS_DIR, CHAOS, CORPUS_A_START, DATA_DIR, FIXTURES_DIR, ML_RESULTS, RUNS_DIR,
                          TEMPORAL_ADDRESS, has_key, load_inventory, load_shops, resolve_shop_id, safe_name,
                          setup_logging, temporal_client)
from agent.telemetry import init_sentry

setup_logging("api")
init_sentry("api")
log = logging.getLogger("recalldesk")

app = FastAPI(title="RecallDesk API", version="0.1.0",
              description="Before you list it, check it. Weekly CPSC recall check for resale shops.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"]
    + [o.strip() for o in os.environ.get("RECALLDESK_CORS_ORIGINS", "").split(",") if o.strip()],
    allow_origin_regex=r"https://([a-z0-9-]+\.)*(onrender\.com|vercel\.app|recalldesk\.tech)",
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = None
_client_err_at = 0.0
_inline_tasks: set[asyncio.Task] = set()


async def get_client():
    """Cached Temporal client; after a failure retry at most every 10s (keeps endpoints fast)."""
    global _client, _client_err_at
    if _client is not None:
        return _client
    if time.time() - _client_err_at < 10:
        return None
    try:
        _client = await asyncio.wait_for(temporal_client(), timeout=3)
        log.info("connected to Temporal at %s", TEMPORAL_ADDRESS)
    except Exception as e:
        _client_err_at = time.time()
        log.warning("Temporal unreachable at %s (%s) - inline mode", TEMPORAL_ADDRESS, type(e).__name__)
    return _client


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _first(*paths: Path) -> tuple[object, str]:
    for p in paths:
        if p.exists():
            try:
                return _json(p), str(p.relative_to(DATA_DIR.parent)).replace("\\", "/")
            except (OSError, json.JSONDecodeError):
                continue
    raise HTTPException(404, f"{paths[-1].name} not found")


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


# ------------------------------------------------------------------------------------------ health
@app.get("/api/health")
async def health():
    client = await get_client()
    return {
        "ok": True,
        "temporal": client is not None,
        "temporal_address": TEMPORAL_ADDRESS,
        "model": ml_bridge.describe(),
        "memory_backend": backboard_memory.backend(),
        "keys": {k: has_key(k) for k in ("TINKER_API_KEY", "SERPAPI_API_KEY", "BACKBOARD_API_KEY", "SENTRY_DSN")},
        "chaos": CHAOS,
        "data": {"recalls": (DATA_DIR / "recalls" / "recalls.jsonl").exists(),
                 "teacher_specs": (DATA_DIR / "specs" / "specs.jsonl").exists(),
                 "eval": (ML_RESULTS / "eval.json").exists(),
                 "scan": (ML_RESULTS / "scan_summary.json").exists()},
    }


# ----------------------------------------------------------------------------------------- recalls
_RECALL_CACHE: dict = {}
_MODEL_KINDS = ("model", "item", "style", "sku", "part", "product_id", "ref")
_WHERE = re.compile(r"\b(printed|located|found|stamped|embossed|engraved|etched|molded|moulded|imprinted|sewn|"
                    r"label|tag|sticker|underside|bottom of|back of|inside of)\b", re.I)
_WHAT = re.compile(r"\b(model|item|batch|lot|date|code|number|serial|upc|style|sku)\b", re.I)


def _ids_only_in_description(r: dict) -> bool:
    """docs/charts/README.md "buried" definition (73 of 151 for corpus A): a model/item/style/SKU/part/product-id/ref
    number appears in the description (ml.regex_ids typed extraction, exclusions dropped) and none of them is in the
    title or product names."""
    from ml.regex_ids import extract_ids_typed, norm_id

    ms = [x["id"] for x in extract_ids_typed(r.get("description") or "", r.get("upcs") or [])
          if not x["excluded"] and x["kind"] in _MODEL_KINDS]
    hay = norm_id((r.get("title") or "") + " " + " ".join(r.get("product_names") or []))
    return bool(ms) and not any(norm_id(m) in hay for m in ms)


def _where_to_look(r: dict) -> str | None:
    """fallback.label_hint, widened to 'engraved/etched/molded/underside...' (e.g. Woodure 26658)."""
    from agent.fallback import label_hint

    hint = label_hint(r)
    if hint:
        return hint
    for sent in re.split(r"(?<=[.!?])\s+", r.get("description") or ""):
        if _WHERE.search(sent) and _WHAT.search(sent):
            return sent.strip()[:240]
    return None


def _recalls_with_specs() -> tuple[list[dict], str]:
    from agent.cpsc import load_corpus

    key = tuple((p.name, p.stat().st_mtime) for p in [DATA_DIR / "recalls" / "recalls.jsonl",
                                                       DATA_DIR / "specs" / "specs.jsonl",
                                                       DATA_DIR / "specs" / "specs.heuristic.jsonl"] if p.exists())
    if _RECALL_CACHE.get("key") != key:
        rows, src = load_corpus(since="2023-01-01")
        if src == "shared/fixtures/recalls.json":
            out = [{**r, "ids_only_in_description": _ids_only_in_description(r)} for r in rows]  # spec already in
        else:
            out = []
            for r in rows:
                spec, ssrc = ml_bridge.spec_for(r, allow_model=False)
                sd = spec.model_dump()
                sd["spec_source"] = "teacher" if "teacher" in ssrc else ("hand-checked" if "hand" in ssrc else "heuristic")
                sd["look_for"] = _where_to_look(r)
                out.append({**r, "spec": sd, "spec_source_detail": ssrc,
                            "ids_only_in_description": _ids_only_in_description(r)})
        out.sort(key=lambda r: (r.get("recall_date", ""), r.get("recall_number", "")), reverse=True)
        _RECALL_CACHE.update(key=key, rows=out, src=src)
    return _RECALL_CACHE["rows"], _RECALL_CACHE["src"]


@app.get("/api/recalls")
async def recalls(since: Optional[str] = Query(None, description="YYYY-MM-DD (default 2026-07-18, corpus A)"),
                  childrens: Optional[bool] = None, limit: int = Query(1000, ge=1, le=2000)):
    if since and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
        raise HTTPException(422, "since must be YYYY-MM-DD")
    rows, _ = await asyncio.to_thread(_recalls_with_specs)
    s = since or CORPUS_A_START
    out = [r for r in rows if r.get("recall_date", "") >= s and (childrens is None or bool(r.get("is_childrens")) == childrens)]
    return out[:limit]


# -------------------------------------------------------------------------------------------- scan
@app.get("/api/scan")
async def scan():
    return _first(ML_RESULTS / "scan_summary.json", FIXTURES_DIR / "scan.json")[0]


@app.get("/api/scan/{recall_number}")
async def scan_recall(recall_number: str):
    if not re.fullmatch(r"[0-9A-Za-z-]{2,20}", recall_number):
        raise HTTPException(422, "bad recall number")
    listings = [l for l in _jsonl(DATA_DIR / "listings" / "listings.jsonl") if str(l.get("recall_number")) == recall_number]
    if not listings:
        fx = FIXTURES_DIR / "scan.json"
        by = next((b for b in (_json(fx).get("by_recall", []) if fx.exists() else []) if b.get("recall_number") == recall_number), None)
        return {"recall_number": recall_number, "listings": [], "source": "none yet", "placeholder": True,
                "summary": by, "note": "no eBay listings scanned for this recall yet (SerpApi scan pending)"}
    pairs = {(p["recall_number"], p["listing_id"]): p["pair_id"] for p in _jsonl(DATA_DIR / "pairs" / "pairs.jsonl")}
    teacher = {t["pair_id"]: t.get("verdict") for t in _jsonl(DATA_DIR / "labeled" / "teacher.jsonl")}
    gold = {g["pair_id"]: g.get("label") for g in _jsonl(DATA_DIR / "gold" / "labels.jsonl")}
    preds = {}
    for name in ("scan_predictions.jsonl", "predictions_scan.jsonl"):
        for p in _jsonl(ML_RESULTS / name):
            if p.get("listing_id"):
                preds[(str(p.get("recall_number")), p["listing_id"])] = p
    rec = next((r for r in (await asyncio.to_thread(_recalls_with_specs))[0] if r["recall_number"] == recall_number), None)
    out = []
    for l in listings:
        key = (recall_number, l["listing_id"])
        v, vs = None, None
        if key in preds:
            v, vs = preds[key].get("verdict"), preds[key].get("model", "model")
        elif pairs.get(key) in teacher:
            v, vs = teacher[pairs[key]], "teacher"
        elif rec is not None:
            from shared.schema import Listing, RecallSpec

            mv, _ = ml_bridge.heuristic(RecallSpec.model_validate(rec["spec"]), Listing.model_validate(l))
            v, vs = mv.model_dump(), "heuristic (live)"
        l = {k: v_ for k, v_ in l.items() if k not in ("seller", "seller_username")}
        if not v:
            v, vs = {"verdict": "no_match", "identifiers_found": [], "conflicts": [], "reason": "not classified yet"}, "none"
        row = {**l, "verdict": v, "verdict_source": vs}
        g = gold.get(pairs.get(key, ""))
        if g:
            row["human_verified"] = g == (v or {}).get("verdict")
            row["gold_label"] = g
        out.append(row)
    return {"recall_number": recall_number, "listings": out, "source": "data/listings/listings.jsonl"}


# ------------------------------------------------------------------------------------------- check
class CheckItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=300)


class CheckRequest(BaseModel):
    shop_id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9-]*$")
    items: list[CheckItemIn] = Field(default_factory=list, max_length=500)
    corpus: Optional[Literal["A", "AB"]] = None


@app.post("/api/check")
async def check(req: CheckRequest):
    req.shop_id = resolve_shop_id(req.shop_id)
    items = [i.model_dump(exclude_none=True) for i in req.items]
    if not items and not load_inventory(req.shop_id):
        raise HTTPException(422, f"no items given and shop {req.shop_id!r} has no inventory file")
    client = await get_client()
    if client is not None:
        from agent.runs import start_check_workflow

        try:
            wid = await start_check_workflow(client, req.shop_id, items, req.corpus)
            log.info("started InventoryCheckWorkflow %s shop=%s items=%s", wid, req.shop_id, len(items) or "inventory")
            return {"workflow_id": wid, "mode": "temporal"}
        except Exception as e:
            log.warning("start_workflow failed (%s) - falling back to inline", e)
    wid = inline.new_id(req.shop_id)
    inline.init_run(wid, req.shop_id)
    task = asyncio.create_task(asyncio.to_thread(inline.run_inline, wid, req.shop_id, items, req.corpus))
    _inline_tasks.add(task)
    task.add_done_callback(_inline_tasks.discard)
    return {"workflow_id": wid, "mode": "inline (no Temporal)"}


def _cached_run(wid: str) -> dict | None:
    p = RUNS_DIR / f"{safe_name(wid)}.json"
    return _json(p) if p.exists() else None


def _fixture_run(wid: str) -> dict | None:
    fx = FIXTURES_DIR / "runs.json"
    if not fx.exists():
        return None
    run = next((r for r in _json(fx) if r.get("workflow_id") == wid), None)
    if run is None:
        return None
    card = FIXTURES_DIR / f"card_{run.get('shop_id')}.json"
    return {**run, "card": _json(card) if card.exists() else None, "mode": "fixture"}


@app.get("/api/cards/latest")
async def latest_card(shop_id: str = Query("little-loop", pattern=r"^[a-z0-9][a-z0-9-]*$")):
    shop_id = resolve_shop_id(shop_id)
    p = CARDS_DIR / f"latest_{safe_name(shop_id)}.json"
    if p.exists():
        return _json(p)
    fx = FIXTURES_DIR / f"card_{shop_id}.json"
    if fx.exists():
        return _json(fx)
    raise HTTPException(404, "no card yet for this shop")


@app.get("/api/cards/{workflow_id}")
async def get_card(workflow_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", workflow_id):
        raise HTTPException(422, "bad workflow id")
    run = _cached_run(workflow_id)
    if run is None and not workflow_id.startswith("local-"):
        client = await get_client()
        if client is not None:
            from agent.runs import get_run

            try:
                run = await get_run(client, workflow_id)
            except Exception as e:
                if "not found" not in str(e).lower():
                    raise HTTPException(502, f"temporal error: {type(e).__name__}")
    if run is None:
        run = _fixture_run(workflow_id)
    if run is None:
        raise HTTPException(404, "workflow not found")
    out = {"status": run["status"], "steps": run.get("steps", []), "workflow_id": workflow_id,
           "workflow_type": run.get("workflow_type"), "shop_id": run.get("shop_id"),
           "started_at": run.get("started_at"), "ended_at": run.get("ended_at")}
    for k in ("card", "mode", "note", "workers", "resumed_after_crash", "children", "error"):
        if run.get(k) is not None:
            out[k] = run[k]
    return out


def _summary(run: dict) -> dict:
    card = run.pop("card", None)
    steps = run.get("steps") or []
    ev = RUNS_DIR / f"{safe_name(run.get('workflow_id', ''))}.events.jsonl"
    n_err = sum(1 for e in _jsonl(ev) if e.get("kind") == "error") if ev.exists() else 0
    run["retries"] = max(n_err, sum(max(0, (s.get("attempt") or 1) - 1) for s in steps))
    if card:
        run["card_id"] = card.get("id")
        run["summary"] = {"card_id": card.get("id"), "do_not_sell": len(card.get("do_not_sell", [])),
                          "check_label": len(card.get("check_label", [])), "items_checked": card.get("items_checked"),
                          "applied_memories": len(card.get("applied_memories", []))}
    return run


@app.get("/api/runs")
async def runs(limit: int = Query(20, ge=1, le=100)):
    client = await get_client()
    out: list[dict] = []
    if client is not None:
        from agent.runs import list_runs

        try:
            out = await asyncio.wait_for(list_runs(client, limit), timeout=10)
        except Exception as e:
            log.warning("list_runs failed: %s", e)
    seen = {safe_name(r["workflow_id"]) for r in out}
    for p in sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if p.stem not in seen and len(out) < limit:
            try:
                out.append(_json(p))
            except (OSError, json.JSONDecodeError):
                pass
    out = [_summary(dict(r)) for r in out if r.get("steps") or r.get("status") == "running"]
    if not out:
        fx = FIXTURES_DIR / "runs.json"
        out = _json(fx) if fx.exists() else []
    out.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return out[:limit]


# ------------------------------------------------------------------------------------------ shops
class CorrectionIn(BaseModel):
    listing_or_item: str = Field(min_length=1, max_length=300)
    recall_number: str = Field(min_length=2, max_length=20, pattern=r"^[0-9A-Za-z-]+$")
    correct_verdict: Literal["match", "check", "no_match"]
    note: str = Field("", max_length=500)


@app.get("/api/shops")
async def shops():  # extra
    return [{k: v for k, v in s.items() if k not in ("inventory_csv",)} | {"items": len(load_inventory(s["shop_id"]))}
            for s in load_shops().values()]


@app.post("/api/shops/{shop_id}/corrections")
async def add_correction(shop_id: str, body: CorrectionIn):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", shop_id):
        raise HTTPException(422, "bad shop id")
    shop_id = resolve_shop_id(shop_id)
    text = backboard_memory.correction_text(body.listing_or_item, body.recall_number, body.correct_verdict, body.note)
    try:
        mid, be = await backboard_memory.add_correction(shop_id, text, {
            "recall_number": body.recall_number, "correct_verdict": body.correct_verdict,
            "item": body.listing_or_item, "note": body.note})
    except Exception as e:
        raise HTTPException(502, f"memory backend error: {type(e).__name__}")
    log.info("memory %s added for %s (%s): recall %s -> %s", mid, shop_id, be, body.recall_number, body.correct_verdict)
    return {"memory_id": mid, "backend": be, "text": text}


@app.get("/api/shops/{shop_id}/memories")
async def memories(shop_id: str):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", shop_id):
        raise HTTPException(422, "bad shop id")
    shop_id = resolve_shop_id(shop_id)
    try:
        hits = await backboard_memory.list_memories(shop_id)
    except Exception as e:
        raise HTTPException(502, f"memory backend error: {type(e).__name__}")
    return [memory_row(h, shop_id) for h in hits]


def memory_row(h, shop_id: str) -> dict:
    md = h.metadata or {}
    return {"memory_id": h.memory_id, "shop_id": shop_id, "text": h.text, "recall_number": md.get("recall_number"),
            "correct_verdict": md.get("correct_verdict"), "item": md.get("item"), "note": md.get("note"),
            "created_at": md.get("created_at"), "backend": h.backend}


# ------------------------------------------------------------------------------------------- eval
@app.get("/api/eval")
async def eval_results():
    return _first(ML_RESULTS / "eval.json", FIXTURES_DIR / "eval.json")[0]
