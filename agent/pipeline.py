"""Pure pipeline logic shared by the Temporal activities and the inline (no-Temporal) fallback.

Nothing in here touches Temporal; long calls take a `beat` callback so activities can heartbeat.
"Code decides": shop memories override model verdicts here, and two deterministic guards (size/variant
conflict, explicit different brand) can only ever DOWNGRADE a verdict, never invent a recall.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from functools import lru_cache
from typing import Callable

from agent import ml_bridge
from agent.backboard_memory import applies_to
from agent.config import CORPUS_A_START, get_shop
from agent.cpsc import load_corpus
from agent.fallback import _brand_hit, _numeric_conflict, compact, label_hint, tokens
from agent.models import (CandidateSpec, ComposeInput, Item, ItemResult, MemoryHit, PairResult, SpecSet)
from agent.telemetry import model_span
from shared.schema import CARD_ACTION, Listing, MatchVerdict, RecallCard, RecallSpec

log = logging.getLogger("recalldesk")
Beat = Callable[..., None]


def _noop(*a, **k):
    pass


# ----------------------------------------------------------------------------------------- items
def item_text(item: Item) -> str:
    return " ".join(x for x in (item.brand, item.name, item.model, item.notes) if x)


def item_label(item: Item) -> str:
    s = item.name if (not item.brand or item.brand.lower() in item.name.lower()) else f"{item.brand} {item.name}"
    return s + (f" (model {item.model})" if item.model else "")


def item_to_listing(shop_id: str, index: int, item: Item) -> Listing:
    specifics = {k: v for k, v in (("Brand", item.brand), ("Model", item.model)) if v}
    title = item.name if (not item.brand or item.brand.lower() in item.name.lower()) else f"{item.brand} {item.name}"
    return Listing(listing_id=f"inv:{shop_id}:{index}", source="inventory", title=title, subtitle=item.notes,
                   item_specifics=specifics)


# ----------------------------------------------------------------------------------------- specs
def corpus_for(shop_id: str, corpus: str | None) -> str:
    return (corpus or get_shop(shop_id).get("corpus") or "A").upper()


def _corpus_specs(corpus: str) -> tuple[tuple[CandidateSpec, ...], str]:
    return _corpus_specs_v(corpus, ml_bridge.data_version())


@lru_cache(maxsize=4)
def _corpus_specs_v(corpus: str, _version: tuple) -> tuple[tuple[CandidateSpec, ...], str]:
    rows, src = load_corpus(since="2023-01-01" if "B" in corpus else CORPUS_A_START)
    want = set(corpus)
    out = []
    n_teacher = 0
    for r in rows:
        tags = set(r.get("corpus") or (["A"] if r.get("recall_date", "") >= CORPUS_A_START else []))
        if not (tags & want):
            continue
        spec, ssrc = ml_bridge.spec_for(r, allow_model=False)
        n_teacher += "teacher" in ssrc
        out.append(CandidateSpec(spec=spec, title=r.get("title", ""), recall_date=r.get("recall_date", ""),
                                 label_hint=label_hint(r), url=r.get("url", "")))
    return tuple(out), f"{src}; specs: {n_teacher} teacher + {len(out) - n_teacher} heuristic"


def load_spec_set(shop_id: str, corpus: str | None) -> SpecSet:
    c = corpus_for(shop_id, corpus)
    specs, src = _corpus_specs(c)
    latest = max((s.recall_date for s in specs if s.recall_date), default="")
    week_start = (date.fromisoformat(latest) - timedelta(days=6)).isoformat() if latest else ""
    new = sum(1 for s in specs if s.recall_date >= week_start) if latest else 0
    return SpecSet(corpus=c, count=len(specs), new_recalls=new, week_of=latest, source=src)


def resolve_specs(spec_set: SpecSet) -> list[CandidateSpec]:
    return list(spec_set.specs) if spec_set.specs else list(_corpus_specs(spec_set.corpus)[0])


def candidate_from_recall(recall: dict, spec: RecallSpec) -> CandidateSpec:
    return CandidateSpec(spec=spec, title=recall.get("title", ""), recall_date=recall.get("recall_date", ""),
                         label_hint=label_hint(recall), url=recall.get("url", ""))


def retrieve(items: list[Item], spec_set: SpecSet, k: int = 3, beat: Beat = _noop) -> list[list[CandidateSpec]]:
    cands = resolve_specs(spec_set)
    by_rn = {c.spec.recall_number: c for c in cands}
    specs = [c.spec for c in cands]
    titles = {c.spec.recall_number: c.title for c in cands}
    out = []
    for i, it in enumerate(items):
        if i % 10 == 0:
            beat(f"retrieve {i}/{len(items)}")
        rns = ml_bridge.retrieve(item_text(it), specs, titles, k=k) if specs else []
        out.append([by_rn[r] for r in rns if r in by_rn])
    return out


# ------------------------------------------------------------------------------------------ check
def look_for(c: CandidateSpec) -> str:
    s = c.spec
    parts = []
    if s.model_numbers:
        parts.append("model no. " + ", ".join(s.model_numbers[:4]) + ("..." if len(s.model_numbers) > 4 else ""))
    if s.other_identifiers:
        parts.append("lot/date code " + ", ".join(s.other_identifiers[:3]))
    if s.upcs:
        parts.append("UPC " + ", ".join(s.upcs[:2]))
    if s.sold_from or s.sold_to:
        parts.append(f"sold {s.sold_from or '?'} to {s.sold_to or '?'}")
    head = "; ".join(parts) or f"which {s.product_type or 'variant'} it is"
    return f"{head}. {c.label_hint}".strip() if c.label_hint else head


def _guard(v: MatchVerdict, c: CandidateSpec, item: Item) -> str | None:
    """Deterministic downgrade rules applied after the model (never upgrades)."""
    if v.verdict == "no_match":
        return None
    text = item_text(item)
    nc = _numeric_conflict(f"{c.spec.product_name} {c.spec.product_type}", text)
    if nc and not v.identifiers_found:
        return f"size/variant conflict ({nc})"
    if item.brand and not v.identifiers_found and item.brand.lower() not in ("generic", "unbranded", "unknown"):
        ib = compact(item.brand)
        sb = c.spec.brand or ""
        if not _brand_hit(sb, set(tokens(text)), compact(text)) and ib not in compact(sb) and \
                not any(compact(x) and compact(x) in ib for x in re.split(r"[()/,]", sb)):
            return f"item brand '{item.brand}' is not the recalled brand '{sb}'"
    return None


def classify_pair(c: CandidateSpec, listing: Listing, use_heuristic: bool) -> tuple[MatchVerdict, dict]:
    desc = ml_bridge.describe()
    with model_span(desc.get("model", "?"), desc.get("provider", "?"), c.spec.recall_number, listing.title) as span:
        v, meta = (ml_bridge.heuristic if use_heuristic else ml_bridge.classify)(c.spec, listing)
        span.finish_with(meta.get("model", ""), meta.get("latency_ms", 0), v.model_dump_json(),
                         meta.get("tokens_in"), meta.get("tokens_out"), meta.get("cost_usd"), meta.get("source", ""))
    return v, meta


def check_one(shop_id: str, index: int, item: Item, candidates: list[CandidateSpec], memories: list[MemoryHit],
              use_heuristic: bool = False, fallback_note: str = "", beat: Beat = _noop) -> ItemResult:
    listing = item_to_listing(shop_id, index, item)
    text = item_text(item)
    pairs: list[PairResult] = []
    total_ms = calls = tin = tout = 0
    cost = 0.0
    for c in candidates:
        beat(f"{index}:{c.spec.recall_number}")
        v, meta = classify_pair(c, listing, use_heuristic)
        total_ms += int(meta.get("latency_ms") or 0)
        calls += 1
        tin, tout = tin + int(meta.get("tokens_in") or 0), tout + int(meta.get("tokens_out") or 0)
        cost += float(meta.get("cost_usd") or 0.0)
        src = "heuristic-fallback" if (use_heuristic and fallback_note) else (
            "heuristic" if meta.get("provider") == "heuristic" else "model")
        pr = PairResult(recall_number=c.spec.recall_number, recall_title=c.title, verdict=v, model_verdict=v.verdict,
                        source=src, model=meta.get("model", ""), look_for=look_for(c),
                        remedy=c.spec.remedy_short or "See the CPSC notice",
                        why=(v.reason + (f" Hazard: {c.spec.hazard_short}." if c.spec.hazard_short else "")).strip())
        if fallback_note and src == "heuristic-fallback":
            pr.why = f"[heuristic fallback: {fallback_note}] " + pr.why
        g = _guard(v, c, item)
        if g:
            pr.verdict = MatchVerdict(verdict="no_match", identifiers_found=v.identifiers_found,
                                      conflicts=[*v.conflicts, g], reason=f"Code guard: {g}.")
            pr.source, pr.guard = "code-guard", g
        for m in memories:  # shop memory beats the model (and the guards)
            if applies_to(m, c.spec.recall_number, text):
                cv = m.metadata["correct_verdict"]
                pr.verdict = MatchVerdict(verdict=cv, identifiers_found=v.identifiers_found, conflicts=v.conflicts,
                                          reason=f"Shop memory overrides model ({pr.model_verdict} -> {cv}): {m.text}")
                pr.source, pr.applied_memory = "memory-override", m
                break
        if pr.verdict.verdict != "no_match" or pr.applied_memory or pr.guard:
            pairs.append(pr)
    return ItemResult(index=index, item=item, pairs=pairs, latency_ms=total_ms, model_calls=calls, tokens_in=tin,
                      tokens_out=tout, cost_usd=round(cost, 6))


# ---------------------------------------------------------------------------------------- compose
def last_thursday(d: date) -> date:
    return d - timedelta(days=(d.weekday() - 3) % 7)


def usage(results: list[ItemResult]) -> dict:
    """Model usage of the inventory check (store-scan listings not included): per-item latency = sum of that
    item's (item, recall) classify calls; cost = tokens x Tinker list price (ml.common.PRICING)."""
    lat = sorted(r.latency_ms for r in results if r.model_calls)

    def pct(q: float) -> int:
        return lat[min(len(lat) - 1, int(q * len(lat)))] if lat else 0
    calls = sum(r.model_calls for r in results)
    tin, tout = sum(r.tokens_in for r in results), sum(r.tokens_out for r in results)
    return {"items": len(results), "model_calls": calls, "tokens_in": tin, "tokens_out": tout,
            "cost_usd": round(sum(r.cost_usd for r in results), 5),
            "p50_item_latency_ms": (lat[len(lat) // 2] if len(lat) % 2 else (lat[len(lat) // 2 - 1] + lat[len(lat) // 2]) // 2)
            if lat else 0, "p90_item_latency_ms": pct(0.9),
            "mean_call_latency_ms": (sum(lat) // calls) if calls else 0}


def compose(inp: ComposeInput) -> dict:
    if not inp.shop_name:
        inp.shop_name = get_shop(inp.shop_id).get("shop_name", inp.shop_id)
    if not inp.model:
        inp.model = ml_bridge.describe().get("model", "?")
    dns, chk, mems = [], [], {}
    for r in sorted(inp.results, key=lambda r: r.index):
        label = item_label(r.item)
        matched = [p for p in r.pairs if p.verdict.verdict == "match"]
        checks = [p for p in r.pairs if p.verdict.verdict == "check"]
        for p in matched:
            dns.append({"item": label, "recall_number": p.recall_number, "recall_title": p.recall_title,
                        "why": p.why[:400], "remedy": p.remedy, "source": p.source})
        if not matched:
            for p in checks:
                chk.append({"item": label, "recall_number": p.recall_number, "look_for": p.look_for[:300],
                            "recall_title": p.recall_title, "source": p.source})
        for p in r.pairs:
            if p.applied_memory:
                mems[p.applied_memory.memory_id] = {"memory_id": p.applied_memory.memory_id,
                                                    "text": p.applied_memory.text,
                                                    "item": label, "recall_number": p.recall_number,
                                                    "model_verdict": p.model_verdict,
                                                    "applied_verdict": p.verdict.verdict,
                                                    "backend": p.applied_memory.backend}
    if inp.store:
        for h in inp.store.flagged:
            row = {"item": f"eBay listing: {h.title}", "recall_number": h.pair.recall_number,
                   "recall_title": h.pair.recall_title, "link": h.link, "source": h.pair.source}
            if h.pair.verdict.verdict == "match":
                dns.append({**row, "why": h.pair.why[:400], "remedy": "End the listing; " + h.pair.remedy})
            else:
                chk.append({**row, "look_for": h.pair.look_for[:300]})
    fallbacks = sum(1 for r in inp.results if r.fallback)
    model = inp.model + (f" (+{fallbacks} item(s) by heuristic fallback)" if fallbacks else "")
    card = RecallCard(id=f"card_{inp.week_of}_{inp.shop_id}", week_of=inp.week_of, shop_id=inp.shop_id,
                      shop_name=inp.shop_name, new_recalls=inp.new_recalls, items_checked=len(inp.results),
                      do_not_sell=dns, check_label=chk, applied_memories=list(mems.values()),
                      workflow_id=inp.workflow_id, model=model, generated_at=inp.generated_at)
    out = card.model_dump()
    # RecallCard ignores extra keys, so re-attach the provenance the UI can show
    out["do_not_sell"], out["check_label"], out["applied_memories"] = dns, chk, list(mems.values())
    out["notes"] = inp.notes
    out["memory_backend"] = inp.memory_backend
    out["store_scan"] = inp.store.model_dump(exclude={"flagged"}) if inp.store else None
    out["actions"] = {"match": CARD_ACTION["match"], "check": CARD_ACTION["check"]}
    out["usage"] = usage(inp.results)
    return out
