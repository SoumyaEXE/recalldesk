"""RecallDesk durable agent (Temporal).

WeeklyRecallSweep (Temporal Schedule, Thursdays 14:00 America/New_York - CPSC posts on Thursdays):
    fetch_new_recalls(since) -> extract_spec(recall) x N -> InventoryCheckWorkflow (child) per watched shop

InventoryCheckWorkflow (on demand from POST /api/check, or as the sweep's child):
    [load_inventory] -> load_spec_set -> load_shop_memories -> retrieve_candidates -> check_item x items
    (6 concurrent, heartbeats) -> scan_ebay_store -> compose_card -> publish_card

Every completed activity result lives in Temporal's event history: if the worker dies mid-run a fresh worker
replays the history and runs only what had not finished. The `progress` query feeds the UI's step list.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from agent.activities import (CHECK_MAX_ATTEMPTS, check_item, compose_card, extract_spec, fetch_new_recalls,
                                  load_inventory, load_shop_memories, load_spec_set, publish_card,
                                  retrieve_candidates, scan_ebay_store)
    from agent.config import load_shops
    from agent.models import (CheckInput, CheckItemInput, ComposeInput, ItemResult, MemoryInput, Progress,
                              RetrieveInput, SpecSet, Step, StoreScanInput, SweepInput)
    from agent.pipeline import last_thursday

CPSC_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), backoff_coefficient=2.0,
                         maximum_interval=timedelta(seconds=30), maximum_attempts=6,
                         non_retryable_error_types=["CpscClientError"])
SPEC_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0, maximum_attempts=3)
MEMORY_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0,
                           maximum_interval=timedelta(seconds=10), maximum_attempts=5,
                           non_retryable_error_types=["BackboardAuth"])
CHECK_RETRY = RetryPolicy(initial_interval=timedelta(milliseconds=500), backoff_coefficient=2.0,
                          maximum_interval=timedelta(seconds=8), maximum_attempts=CHECK_MAX_ATTEMPTS)
SERP_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), maximum_attempts=3,
                         non_retryable_error_types=["SerpQuota"])  # quota is handled inside: snapshot, not retry
SIMPLE_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=5,
                           non_retryable_error_types=["NoInventory"])
MAX_PARALLEL_CHECK = 6


def _cause(e: BaseException) -> str:
    while getattr(e, "cause", None) is not None:
        e = e.cause  # type: ignore[assignment]
    return str(e)


class _Tracked:
    """Step bookkeeping shared by both workflows (exposed via the `progress` query)."""
    _p: Progress | None

    def _ts(self) -> str:
        return workflow.now().isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _step(self, name: str) -> Step:
        assert self._p
        for s in self._p.steps:
            if s.name == name:
                return s
        s = Step(name=name)
        self._p.steps.append(s)
        return s

    def _start(self, name: str, note: str | None = None) -> Step:
        s = self._step(name)
        s.status, s.started_at, s.attempt = "running", self._ts(), max(s.attempt, 1)
        if note:
            s.note = note
        return s

    def _done(self, name: str, attempt: int = 1, note: str | None = None, status: str = "completed") -> None:
        s = self._step(name)
        s.status, s.ended_at, s.attempt = status, self._ts(), max(s.attempt, attempt)  # type: ignore[assignment]
        if s.started_at is None:
            s.started_at = s.ended_at
        if note:
            s.note = note
        if attempt > 1 and not s.error:
            s.error = f"succeeded on attempt {attempt} after {attempt - 1} retr{'y' if attempt == 2 else 'ies'}"

    def _fail(self, name: str, err: str) -> None:
        s = self._step(name)
        s.status, s.ended_at, s.error = "failed", self._ts(), err[:300]


@workflow.defn
class InventoryCheckWorkflow(_Tracked):
    def __init__(self) -> None:
        self._p = None

    @workflow.query
    def progress(self) -> Progress | None:
        return self._p

    @workflow.run
    async def run(self, inp: CheckInput) -> dict:
        wid = workflow.info().workflow_id
        self._p = Progress(workflow_id=wid, workflow_type="InventoryCheckWorkflow", shop_id=inp.shop_id,
                           started_at=self._ts())
        names = (["load_inventory"] if not inp.items else []) + [
            "load_specs", "load_shop_memories", "check_items", "scan_ebay_store", "compose_card", "publish_card"]
        for n in names:
            self._step(n)
        notes: list[str] = []

        # 0) inventory -------------------------------------------------------------------------
        items = list(inp.items)
        if not items:
            self._start("load_inventory")
            items = await workflow.execute_activity(load_inventory, inp.shop_id,
                                                    start_to_close_timeout=timedelta(seconds=20),
                                                    retry_policy=SIMPLE_RETRY)
            self._done("load_inventory", note=f"{len(items)} items from the shop's inventory file")

        # 1) which recalls --------------------------------------------------------------------
        self._start("load_specs")
        if inp.spec_set is not None:
            spec_set = inp.spec_set
            self._done("load_specs", note=f"{len(spec_set.specs)} new recall specs from this week's sweep")
        else:
            spec_set = await workflow.execute_activity(load_spec_set, [inp.shop_id, inp.corpus or ""],
                                                       start_to_close_timeout=timedelta(seconds=60),
                                                       retry_policy=SIMPLE_RETRY)
            self._done("load_specs", spec_set.attempt,
                       f"{spec_set.count} recalls (corpus {spec_set.corpus}); {spec_set.source}")

        # 2) shop memories (Backboard) ---------------------------------------------------------
        self._start("load_shop_memories")
        try:
            mem = await workflow.execute_activity(load_shop_memories, MemoryInput(shop_id=inp.shop_id, items=items),
                                                  start_to_close_timeout=timedelta(seconds=60),
                                                  heartbeat_timeout=timedelta(seconds=20), retry_policy=MEMORY_RETRY)
            self._done("load_shop_memories", mem.attempt, f"{mem.total} relevant memories; backend={mem.backend}")
        except ActivityError as e:
            self._fail("load_shop_memories", _cause(e))
            notes.append(f"shop memories unavailable ({_cause(e)[:80]}); card shows raw model verdicts")
            mem = None

        # 3) retrieve + classify every item (bounded parallelism) -----------------------------
        cs = self._start("check_items", f"retrieving candidates for {len(items)} items")
        cands = await workflow.execute_activity(retrieve_candidates, RetrieveInput(items=items, spec_set=spec_set, k=3),
                                                start_to_close_timeout=timedelta(seconds=120),
                                                heartbeat_timeout=timedelta(seconds=30), retry_policy=SIMPLE_RETRY)
        sem = asyncio.Semaphore(MAX_PARALLEL_CHECK)
        results: list[ItemResult] = []
        retried = fallbacks = skipped = 0
        n_pairs = sum(len(c) for c in cands.per_item)
        cs.note = f"0/{len(items)} items ({n_pairs} item x recall pairs)"

        async def check(i: int):
            nonlocal retried, fallbacks, skipped
            async with sem:
                try:
                    r = await workflow.execute_activity(
                        check_item,
                        CheckItemInput(workflow_id=wid, shop_id=inp.shop_id, index=i, item=items[i],
                                       candidates=cands.per_item[i],
                                       memories=(mem.by_item.get(str(i), []) if mem else [])),
                        start_to_close_timeout=timedelta(seconds=120),  # real model calls; heartbeat catches hangs
                        heartbeat_timeout=timedelta(seconds=10),
                        retry_policy=CHECK_RETRY)
                except ActivityError as e:
                    workflow.logger.warning("check_item %d failed permanently: %s", i, _cause(e))
                    skipped += 1
                    return
                results.append(r)
                cs.attempt = max(cs.attempt, r.attempt)
                retried += r.attempt > 1
                fallbacks += r.fallback
                cs.note = f"{len(results)}/{len(items)} items ({n_pairs} item x recall pairs)"

        await asyncio.gather(*(check(i) for i in range(len(items))))
        parts = []
        if retried:
            parts.append(f"{retried} item(s) needed retries")
        if fallbacks:
            parts.append(f"{fallbacks} answered by HEURISTIC FALLBACK after invalid model output")
            notes.append(f"{fallbacks} item(s) were classified by the heuristic fallback after the model kept "
                         "returning invalid JSON")
        if skipped:
            parts.append(f"{skipped} item(s) skipped after max retries")
            notes.append(f"{skipped} item(s) could not be checked - check them by hand")
        cs.error = "; ".join(parts) or None
        self._done("check_items", cs.attempt,
                   f"{len(results)}/{len(items)} items, {n_pairs} pairs; retrieval: {cands.source}")
        results.sort(key=lambda r: r.index)

        # 4) eBay store (SerpApi) ---------------------------------------------------------------
        self._start("scan_ebay_store")
        store = None
        try:
            store = await workflow.execute_activity(scan_ebay_store, StoreScanInput(shop_id=inp.shop_id,
                                                                                    spec_set=spec_set),
                                                    start_to_close_timeout=timedelta(seconds=180),
                                                    heartbeat_timeout=timedelta(seconds=30), retry_policy=SERP_RETRY)
            self._done("scan_ebay_store", store.attempt,
                       f"source={store.source}" + ("" if store.skipped else
                                                    f"; {store.listings_seen} listings, {len(store.flagged)} flagged"),
                       status="skipped" if store.skipped else "completed")
        except ActivityError as e:
            self._fail("scan_ebay_store", _cause(e))
            notes.append("eBay store scan failed this week; inventory results are unaffected")

        # 5) compose + publish ------------------------------------------------------------------
        self._start("compose_card")
        week_of = spec_set.week_of or last_thursday(workflow.now().date()).isoformat()
        card = await workflow.execute_activity(
            compose_card,
            ComposeInput(shop_id=inp.shop_id, shop_name="", week_of=week_of,
                         new_recalls=spec_set.new_recalls, results=results, store=store, workflow_id=wid,
                         generated_at=self._ts(), model="", notes=notes,
                         memory_backend=mem.backend if mem else "unavailable"),
            start_to_close_timeout=timedelta(seconds=30), retry_policy=SIMPLE_RETRY)
        self._done("compose_card", note=f"{len(card['do_not_sell'])} DO NOT SELL, {len(card['check_label'])} CHECK LABEL")

        self._start("publish_card")
        pub = await workflow.execute_activity(publish_card, card, start_to_close_timeout=timedelta(seconds=20),
                                              retry_policy=SIMPLE_RETRY)
        self._done("publish_card", pub.attempt, pub.card_id)
        self._p.card = card
        self._p.status = "completed"
        return card


@workflow.defn
class WeeklyRecallSweep(_Tracked):
    def __init__(self) -> None:
        self._p = None

    @workflow.query
    def progress(self) -> Progress | None:
        return self._p

    @workflow.run
    async def run(self, inp: SweepInput) -> dict:
        wid = workflow.info().workflow_id
        now = workflow.now()
        since = inp.since or (now.date() - timedelta(days=7)).isoformat()
        self._p = Progress(workflow_id=wid, workflow_type="WeeklyRecallSweep", started_at=self._ts())
        if inp.shops:
            shops = list(inp.shops)
        else:
            with workflow.unsafe.sandbox_unrestricted():
                shops = [s for s, v in load_shops().items() if v.get("watched")]
        for n in ["fetch_new_recalls", "extract_specs", *[f"check_shop:{s}" for s in shops]]:
            self._step(n)

        self._start("fetch_new_recalls", f"since {since}")
        fetched = await workflow.execute_activity(fetch_new_recalls, since, start_to_close_timeout=timedelta(seconds=60),
                                                  retry_policy=CPSC_RETRY)
        self._done("fetch_new_recalls", fetched.attempt, f"{len(fetched.recalls)} recalls; source={fetched.source}")

        es = self._start("extract_specs", f"0/{len(fetched.recalls)}")
        sem = asyncio.Semaphore(8)
        specs, sources = [], {}

        async def one(r: dict):
            async with sem:
                try:
                    s = await workflow.execute_activity(extract_spec, r, start_to_close_timeout=timedelta(seconds=180),
                                                        heartbeat_timeout=timedelta(seconds=30), retry_policy=SPEC_RETRY)
                except ActivityError as e:
                    workflow.logger.warning("extract_spec %s failed: %s", r.get("recall_number"), _cause(e))
                    return
                specs.append(s.candidate)
                sources[s.source] = sources.get(s.source, 0) + 1
                es.note = f"{len(specs)}/{len(fetched.recalls)}"

        await asyncio.gather(*(one(r) for r in fetched.recalls))
        specs.sort(key=lambda c: c.spec.recall_number)
        self._done("extract_specs", note=f"{len(specs)}/{len(fetched.recalls)} specs; "
                                         + ", ".join(f"{v} {k}" for k, v in sources.items()))
        week_of = last_thursday(now.date()).isoformat()
        spec_set = SpecSet(corpus="new", specs=specs, count=len(specs), new_recalls=len(specs), week_of=week_of,
                           source=f"weekly sweep since {since}")

        cards = {}
        for s in shops:  # one child per shop: each shop's run is its own durable, inspectable workflow
            name = f"check_shop:{s}"
            self._start(name)
            cid = f"{wid}-{s}"
            self._p.children.append(cid)
            try:
                card = await workflow.execute_child_workflow(InventoryCheckWorkflow.run,
                                                             CheckInput(shop_id=s, spec_set=spec_set), id=cid)
                cards[s] = card["id"]
                self._done(name, note=f"{card['id']}: {len(card['do_not_sell'])} DO NOT SELL, "
                                      f"{len(card['check_label'])} CHECK LABEL (child {cid})")
            except Exception as e:  # one shop failing must not cost the others their card
                self._fail(name, _cause(e))
        self._p.status = "completed"
        return {"since": since, "new_recalls": len(specs), "cards": cards, "children": self._p.children}
