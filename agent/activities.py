"""Temporal activities: the flaky, side-effecting parts of RecallDesk.

fetch_new_recalls(since)      CPSC API (5xx -> retried with backoff; 4xx non-retryable; last attempts -> snapshot)
extract_spec(recall)          cached teacher spec -> live teacher (if TINKER key) -> heuristic spec
load_spec_set(shop, corpus)   which recalls an on-demand check runs against (summary only; specs stay on disk)
load_inventory(shop_id)       the shop's inventory CSV
load_shop_memories(...)       Backboard semantic search per item (local store without a key)
retrieve_candidates(...)      top-k recalls per item (BM25 over specs, identifier hits always included)
check_item(...)               classify item x candidates; heartbeats; invalid JSON retried; final attempt ->
                              heuristic fallback, labelled; memory overrides + code guards applied in code
scan_ebay_store(shop, specs)  SerpApi eBay (cached); quota/429 -> NOT retried, labelled snapshot
compose_card / publish_card   deterministic card; atomic write to agent/cards/<safe_name>.json

RECALLDESK_CHAOS=1 injects fake CPSC 503s, model hangs (heartbeat timeouts) and invalid JSON (incl. a few
"stubborn" items that only the heuristic fallback can answer) so the retries are visible. Chaos never fires on
the final attempt, so a demo run always converges.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime, timezone

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

from agent import backboard_memory, cpsc, ml_bridge, pipeline, serp
from agent.config import CARDS_DIR, CHAOS, CHECK_DELAY_S, RUNS_DIR, get_shop, load_inventory as _load_inv, safe_name
from agent.models import (Candidates, CandidateSpec, CheckItemInput, ComposeInput, FetchResult, Item, ItemResult,
                          MemoryInput, MemorySet, PublishResult, RetrieveInput, SpecResult, SpecSet, StoreListingHit,
                          StoreScan, StoreScanInput)
from agent.telemetry import activity_span, capture

log = logging.getLogger("recalldesk")

CHECK_MAX_ATTEMPTS = 4
CHAOS_503_P = float(os.environ.get("RECALLDESK_CHAOS_503_P", "0.35"))
CHAOS_HANG_P = float(os.environ.get("RECALLDESK_CHAOS_HANG_P", "0.06"))
CHAOS_JSON_P = float(os.environ.get("RECALLDESK_CHAOS_JSON_P", "0.10"))
CHAOS_STUBBORN_P = float(os.environ.get("RECALLDESK_CHAOS_STUBBORN_P", "0.05"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def record_event(step: str, attempt: int, kind: str, msg: str = "") -> None:
    """Append-only per-workflow event log (errors of attempts that later succeeded). Never fails the activity."""
    try:
        wid = activity.info().workflow_id
        if not wid:
            return
        with open(RUNS_DIR / f"{safe_name(wid)}.events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), "step": step, "attempt": attempt, "kind": kind, "msg": msg[:300]}) + "\n")
    except Exception as e:  # observability must never fail the activity
        log.debug("could not record event: %s", e)


def _chaos(p: float, key: str) -> bool:
    if not CHAOS:
        return False
    info = activity.info()
    if info.attempt >= info_max(info):
        return False
    return random.Random(f"{info.workflow_id}:{key}:{info.attempt}:{time.time_ns()}").random() < p


def info_max(info) -> int:
    return CHECK_MAX_ATTEMPTS if info.activity_type == "check_item" else 3


def _stubborn(wid: str, index: int) -> bool:
    """Deterministic per (workflow, item): this item's model output is invalid on every non-final attempt."""
    return CHAOS and random.Random(f"stubborn:{wid}:{index}").random() < CHAOS_STUBBORN_P


async def _heartbeat_while(fn, *args, every: float = 1.0):
    task = asyncio.ensure_future(asyncio.to_thread(fn, *args))
    while not task.done():
        activity.heartbeat()
        await asyncio.wait({task}, timeout=every)
    return task.result()


# --------------------------------------------------------------------------------------- fetch/spec
@activity.defn
async def fetch_new_recalls(since: str) -> FetchResult:
    info = activity.info()
    log.info("[fetch_new_recalls] since=%s attempt=%d", since, info.attempt)
    with activity_span("gen_ai.execute_tool", "execute_tool fetch_new_recalls", since=since):
        try:
            if _chaos(CHAOS_503_P, "cpsc"):
                await asyncio.sleep(0.2)
                raise ApplicationError("CPSC API HTTP 503 Service Unavailable (chaos)", type="CpscUnavailable")
            raw = await asyncio.to_thread(cpsc.fetch_raw, since)
            source = "cpsc-live"
        except ApplicationError as e:
            record_event("fetch_new_recalls", info.attempt, "error", str(e))
            log.warning("[fetch_new_recalls] attempt=%d FAILED: %s -> Temporal retries with backoff", info.attempt, e)
            raise
        except (cpsc.CpscHttpError, httpx.HTTPError, ValueError) as e:
            status = getattr(e, "status", 0)
            msg = f"{type(e).__name__}: {e}"[:200]
            record_event("fetch_new_recalls", info.attempt, "error", msg)
            if 400 <= status < 500 and status != 429:
                raise ApplicationError(msg, type="CpscClientError", non_retryable=True) from None
            snap = cpsc.best_snapshot(since) if info.attempt >= 3 else None
            if snap is None:
                log.warning("[fetch_new_recalls] attempt=%d FAILED: %s -> retry", info.attempt, msg)
                raise ApplicationError(msg, type="CpscUnavailable") from None
            raw, source = snap[0], f"{snap[1]} after CPSC failed: {msg[:80]}"
            log.warning("[fetch_new_recalls] CPSC still failing on attempt %d -> degraded to %s", info.attempt, source)
    recalls = [cpsc.normalize(r) for r in raw]
    log.info("[fetch_new_recalls] OK: %d recalls since %s (source=%s)", len(recalls), since, source)
    record_event("fetch_new_recalls", info.attempt, "ok", f"{len(recalls)} recalls, source={source}")
    return FetchResult(since=since, recalls=recalls, source=source, attempt=info.attempt)


@activity.defn
async def extract_spec(recall: dict) -> SpecResult:
    info = activity.info()
    rn = recall.get("recall_number", "?")
    with activity_span("gen_ai.invoke_agent", "invoke_agent extract_spec", recall_number=rn):
        try:
            spec, source = await _heartbeat_while(ml_bridge.spec_for, recall)
        except Exception as e:
            record_event(f"extract_spec:{rn}", info.attempt, "error", f"{type(e).__name__}: {e}")
            if info.attempt >= 3:  # teacher keeps failing -> heuristic spec, labelled
                spec, source = ml_bridge.spec_for(recall, allow_model=False)
                source += f" (fallback after {info.attempt - 1} teacher failures)"
            else:
                raise ApplicationError(f"spec extraction failed: {e}"[:300], type="SpecError") from None
    return SpecResult(candidate=pipeline.candidate_from_recall(recall, spec), source=source, attempt=info.attempt)


@activity.defn
async def load_spec_set(args: list[str]) -> SpecSet:
    shop_id, corpus = args[0], (args[1] if len(args) > 1 and args[1] else None)
    ss = await asyncio.to_thread(pipeline.load_spec_set, shop_id, corpus)
    ss.attempt = activity.info().attempt
    log.info("[load_spec_set] shop=%s corpus=%s: %d recalls (%s)", shop_id, ss.corpus, ss.count, ss.source)
    return ss


@activity.defn
async def load_inventory(shop_id: str) -> list[Item]:
    items = [Item(**i) for i in _load_inv(shop_id)]
    if not items:
        raise ApplicationError(f"no inventory for shop {shop_id!r}: POST items or add inventory_csv to agent/shops.json",
                               type="NoInventory", non_retryable=True)
    log.info("[load_inventory] shop=%s: %d items", shop_id, len(items))
    return items


# --------------------------------------------------------------------------------------- memory
@activity.defn
async def load_shop_memories(inp: MemoryInput) -> MemorySet:
    info = activity.info()
    be = backboard_memory.backend()
    with activity_span("gen_ai.execute_tool", "execute_tool load_shop_memories", shop_id=inp.shop_id, backend=be):
        try:
            sem = asyncio.Semaphore(8)
            async with httpx.AsyncClient(timeout=30) as client:
                async def one(i: int, it: Item):
                    async with sem:
                        activity.heartbeat(i)
                        return str(i), await backboard_memory.search(inp.shop_id, pipeline.memory_query(it), limit=3,
                                                                     client=client)
                pairs = await asyncio.gather(*(one(i, it) for i, it in enumerate(inp.items)))
            listed = await backboard_memory.list_memories(inp.shop_id)  # one call: safety net for search misses
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            record_event("load_shop_memories", info.attempt, "error", f"Backboard HTTP {code}")
            if code in (401, 403):
                raise ApplicationError(f"Backboard HTTP {code} (check BACKBOARD_API_KEY)", type="BackboardAuth",
                                       non_retryable=True) from None
            raise ApplicationError(f"Backboard HTTP {code}", type="BackboardUnavailable") from None
        except httpx.HTTPError as e:
            record_event("load_shop_memories", info.attempt, "error", type(e).__name__)
            raise ApplicationError(f"Backboard network error: {type(e).__name__}", type="BackboardUnavailable") from None
    by_item = {k: v for k, v in pairs if v}
    n_search = len({h.memory_id for v in by_item.values() for h in v})
    added = backboard_memory.merge_listed(by_item, [pipeline.item_text(it) for it in inp.items], listed)
    total = len({h.memory_id for v in by_item.values() for h in v})
    log.info("[load_shop_memories] shop=%s backend=%s: %d relevant memories for %d items (%d via search, +%d item "
             "match(es) from the memory list)", inp.shop_id, be, total, len(by_item), n_search, added)
    record_event("load_shop_memories", info.attempt, "ok", f"{total} memories, backend={be}")
    return MemorySet(by_item=by_item, backend=be, total=total, attempt=info.attempt)


# ---------------------------------------------------------------------------------------- check
@activity.defn
async def retrieve_candidates(inp: RetrieveInput) -> Candidates:
    per = await _heartbeat_while(pipeline.retrieve, inp.items, inp.spec_set, inp.k)
    n = sum(len(x) for x in per)
    log.info("[retrieve_candidates] %d items -> %d (item, recall) pairs (top-%d)", len(inp.items), n, inp.k)
    return Candidates(per_item=per, source="ml.infer.retrieve" if ml_bridge._mod("ml.infer") and hasattr(
        ml_bridge._mod("ml.infer"), "retrieve") else "BM25 over specs + identifier hits")


@activity.defn
async def check_item(inp: CheckItemInput) -> ItemResult:
    info = activity.info()
    step = f"check_item:{inp.index}"
    last = info.attempt >= CHECK_MAX_ATTEMPTS
    with activity_span("gen_ai.invoke_agent", "invoke_agent RecallDesk", item=inp.item.name[:80],
                       attempt=info.attempt, candidates=len(inp.candidates)):
        try:
            if _chaos(CHAOS_HANG_P, f"hang{inp.index}"):
                log.warning("[check_item] #%d attempt=%d model hung (chaos) - stops heartbeating", inp.index, info.attempt)
                record_event(step, info.attempt, "error", "model call hung; heartbeat timeout (chaos)")
                await asyncio.sleep(14)  # > heartbeat_timeout: server times us out and schedules a retry
                activity.heartbeat()
                await asyncio.sleep(2)
                raise ApplicationError("model call hung (chaos)", type="ModelTimeout")
            if not last and (_stubborn(info.workflow_id, inp.index) or _chaos(CHAOS_JSON_P, f"json{inp.index}")):
                raise ml_bridge.InvalidModelOutput(
                    "model returned invalid JSON: '{\"verdict\": \"mat' (chaos)")
            if CHECK_DELAY_S:
                await _heartbeat_while(time.sleep, CHECK_DELAY_S * random.uniform(0.6, 1.4))
            prev = info.attempt - 1
            use_h = last and prev > 0
            note = f"model output invalid on {prev} attempt(s)" if use_h else ""
            res = await _heartbeat_while(pipeline.check_one, inp.shop_id, inp.index, inp.item, inp.candidates,
                                         inp.memories, use_h, note)
        except ml_bridge.InvalidModelOutput as e:
            record_event(step, info.attempt, "error", str(e))
            log.warning("[check_item] #%d attempt=%d invalid model output -> retry", inp.index, info.attempt)
            raise ApplicationError(str(e)[:300], type="InvalidModelJSON") from None
        except ApplicationError as e:
            record_event(step, info.attempt, "error", str(e))
            raise
        except Exception as e:
            capture(e)
            record_event(step, info.attempt, "error", f"{type(e).__name__}: {e}")
            raise ApplicationError(f"{type(e).__name__}: {e}"[:300], type="CheckError") from None
    res.attempt, res.fallback = info.attempt, bool(use_h)
    flagged = [f"{p.recall_number}:{p.verdict.verdict}" for p in res.pairs if p.verdict.verdict != "no_match"]
    if flagged or info.attempt > 1:
        log.info("[check_item] #%d %s -> %s%s", inp.index, inp.item.name[:40], ", ".join(flagged) or "clear",
                 f" (attempt {info.attempt}{', HEURISTIC FALLBACK' if use_h else ''})" if info.attempt > 1 else "")
    record_event(step, info.attempt, "ok", ", ".join(flagged) or "clear")
    return res


# ----------------------------------------------------------------------------------------- store
@activity.defn
async def scan_ebay_store(inp: StoreScanInput) -> StoreScan:
    info = activity.info()
    shop = get_shop(inp.shop_id)
    seller = (shop.get("ebay_seller") or "").strip()
    if not seller:
        return StoreScan(source="skipped (no eBay store configured for this shop)", skipped=True, attempt=info.attempt)
    # SerpApi's eBay engine needs a query even with the seller filter (_sasl + _saslop=1): a few broad
    # queries per store per week, each cached forever in data/serp/ (cache key shared with ml.serp_scan).
    queries = list(shop.get("ebay_store_queries") or ["baby", "kids"])[:int(os.environ.get("RECALLDESK_STORE_MAX_SEARCHES", "3"))]
    spent, bodies, sources = 0, [], []
    with activity_span("gen_ai.execute_tool", "execute_tool scan_ebay_store", shop_id=inp.shop_id):
        for q in queries:
            activity.heartbeat(q)
            params = serp.store_params(seller, q)
            try:
                body, src = await asyncio.to_thread(serp.search, params)
            except serp.SerpQuotaError as e:  # NOT retried: retrying burns quota and won't succeed this week
                record_event("scan_ebay_store", info.attempt, "error", str(e))
                snap, day = serp.newest_snapshot_for(seller)
                if snap is not None and not bodies:
                    bodies.append(snap)
                sources.append(f"snapshot (SerpApi quota/429, not retried; "
                               f"{'cached ' + day if snap else 'no cached store snapshot'})")
                log.warning("[scan_ebay_store] %s -> %s", e, sources[-1])
                break
            except RuntimeError as e:
                record_event("scan_ebay_store", info.attempt, "error", str(e))
                raise ApplicationError(str(e), type="SerpApiError") from None
            spent += src == "serpapi-live"
            if body is not None:
                bodies.append(body)
            sources.append(src)
        if not bodies and not any(x.startswith("snapshot (SerpApi") for x in sources):
            snap, day = serp.newest_snapshot_for(seller)
            if snap is not None:
                bodies.append(snap)
                sources = [f"snapshot (no SERPAPI_API_KEY; cached {day})"]
    source = ", ".join(dict.fromkeys(sources)) or "none"
    seen_ids: set = set()
    listings = []
    for b in bodies:
        for l in serp.listings_from(b):
            if l["item_id"] not in seen_ids:
                seen_ids.add(l["item_id"])
                listings.append(l)
    cands = pipeline.resolve_specs(inp.spec_set)
    specs = [c.spec for c in cands]
    by_rn = {c.spec.recall_number: c for c in cands}
    titles = {c.spec.recall_number: c.title for c in cands}
    flagged = []
    for i, l in enumerate(listings):
        activity.heartbeat(i)
        lst = pipeline.Listing(listing_id=f"ebay:{l['item_id']}", source="ebay", title=l["title"],
                               subtitle=l.get("subtitle"), condition=l.get("condition"), price=l.get("price"),
                               link=l.get("link"), seller_hash=l.get("seller_hash"))
        for rn in ml_bridge.retrieve(l["title"], specs, titles, k=2):
            c = by_rn.get(rn)
            if not c:
                continue
            v, meta = await asyncio.to_thread(pipeline.classify_pair, c, lst, False)
            if v.verdict != "no_match":
                flagged.append(StoreListingHit(title=l["title"], link=l.get("link"), price=l.get("price"),
                                               pair=pipeline.PairResult(recall_number=rn, recall_title=c.title,
                                                                        verdict=v, source=meta.get("source", ""),
                                                                        model=meta.get("model", ""),
                                                                        look_for=pipeline.look_for(c),
                                                                        why=v.reason, remedy=c.spec.remedy_short)))
    log.info("[scan_ebay_store] shop=%s %d listings, %d flagged (source=%s)", inp.shop_id, len(listings), len(flagged),
             source)
    record_event("scan_ebay_store", info.attempt, "ok", f"{len(listings)} listings, source={source}")
    return StoreScan(source=source, listings_seen=len(listings), searches_spent=spent, flagged=flagged,
                     attempt=info.attempt)


# ------------------------------------------------------------------------------------- compose/publish
@activity.defn
async def compose_card(inp: ComposeInput) -> dict:
    card = pipeline.compose(inp)
    log.info("[compose_card] %s: %d DO NOT SELL, %d CHECK LABEL, %d memories applied", card["id"],
             len(card["do_not_sell"]), len(card["check_label"]), len(card["applied_memories"]))
    record_event("compose_card", activity.info().attempt, "ok", card["id"])
    return card


def write_card(card: dict) -> str:
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(card, ensure_ascii=False, indent=1)
    names = [f"{safe_name(card['workflow_id'])}.json", f"{safe_name(card['id'])}.json",
             f"latest_{safe_name(card['shop_id'])}.json"]
    for name in names:
        tmp = CARDS_DIR / (name + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(CARDS_DIR / name)  # atomic: a crash never leaves a half-written card
    return str(CARDS_DIR / names[0])


@activity.defn
async def publish_card(card: dict) -> PublishResult:
    path = write_card(card)
    log.info("[publish_card] wrote agent/cards/%s", path.replace("\\", "/").rsplit("/", 1)[-1])
    record_event("publish_card", activity.info().attempt, "ok", card["id"])
    return PublishResult(card_id=card["id"], path=path, attempt=activity.info().attempt)


ALL_ACTIVITIES = [fetch_new_recalls, extract_spec, load_spec_set, load_inventory, load_shop_memories,
                  retrieve_candidates, check_item, scan_ebay_store, compose_card, publish_card]
_ = (CandidateSpec,)
