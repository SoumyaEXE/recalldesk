"""SerpApi eBay engine for the per-shop store scan (cache-first, budget-aware, never re-spends a cached search).

    search(params) -> (json, source)     source: "cache" | "serpapi-live" | "snapshot (...)"

Cache: data/serp/<sha1 of params without api_key>.json - the same convention as ml/ (CONTRACT: cache EVERY
response, never re-spend a cached search). Raw responses contain seller usernames; data/serp/ is gitignored and
only seller hashes leave this module.

Quota / HTTP 429 is NOT retried (retrying burns quota and won't succeed this week): the caller gets the newest
cached snapshot for the same store, labelled `snapshot (SerpApi 429 ...)`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone

import httpx

from agent.config import SERP_CACHE_DIR

ENDPOINT = "https://serpapi.com/search.json"


class SerpQuotaError(Exception):
    pass


def cache_key(params: dict) -> str:
    clean = {k: v for k, v in sorted(params.items()) if k != "api_key"}
    return hashlib.sha1(json.dumps(clean, sort_keys=True).encode("utf-8")).hexdigest()


def seller_hash(username: str | None) -> str | None:
    return None if not username else "s_" + hashlib.sha1(username.strip().lower().encode("utf-8")).hexdigest()[:6]


def _redact(s: str) -> str:
    return re.sub(r"api_key=[^&\s]+", "api_key=***", s)


def cached(params: dict) -> dict | None:
    p = SERP_CACHE_DIR / f"{cache_key(params)}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def search(params: dict, allow_live: bool = True) -> tuple[dict | None, str]:
    hit = cached(params)
    if hit is not None:
        return hit, "cache"
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key or not allow_live:
        return None, "snapshot (no SERPAPI_API_KEY; nothing cached for this store)"
    try:
        r = httpx.get(ENDPOINT, params={**params, "api_key": key}, timeout=40)
    except httpx.HTTPError as e:
        raise RuntimeError(_redact(f"SerpApi network error: {type(e).__name__}")) from None
    body = {}
    try:
        body = r.json()
    except ValueError:
        pass
    err = str(body.get("error", "")) if isinstance(body, dict) else ""
    if r.status_code == 429 or "run out of searches" in err.lower() or "limit" in err.lower() and r.status_code >= 400:
        raise SerpQuotaError(f"SerpApi HTTP {r.status_code}: {err[:120] or 'quota exceeded'}")
    if r.status_code >= 400:
        raise RuntimeError(f"SerpApi HTTP {r.status_code}: {err[:120]}")
    SERP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    body.setdefault("search_parameters", {}).pop("api_key", None)
    body["_recalldesk"] = {"params": params, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (SERP_CACHE_DIR / f"{cache_key(params)}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return body, "serpapi-live"


def store_params(seller: str, query: str = "") -> dict:
    """Same params (and therefore the same cache key) as ml.serp_scan.ebay_params(query, seller, ipg=200):
    SerpApi's eBay engine filters by seller with _sasl + _saslop=1. One search per store per week."""
    m = None
    try:
        import ml.serp_scan as m  # noqa: F811
    except Exception:
        pass
    if m is not None and hasattr(m, "ebay_params"):
        return m.ebay_params(query, seller=seller, ipg=200)
    return {"engine": "ebay", "ebay_domain": "ebay.com", "_nkw": query, "_ipg": "200", "_sasl": seller, "_saslop": "1"}


def newest_snapshot_for(seller: str) -> tuple[dict | None, str]:
    """Any cached response for this seller (e.g. last week's), for the 429 fallback."""
    if not SERP_CACHE_DIR.exists():
        return None, ""
    best = None
    for p in SERP_CACHE_DIR.glob("*.json"):
        try:
            body = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sp = {**(body.get("search_parameters") or {}), **((body.get("_recalldesk") or {}).get("params") or {})}
        if str(sp.get("_sasl", "")).lower() == seller.lower():
            ts = body.get("_recalldesk_fetched_at") or (body.get("_recalldesk") or {}).get("fetched_at") or ""
            if best is None or ts > best[1]:
                best = (body, ts)
    return (best[0], best[1][:10]) if best else (None, "")


def listings_from(body: dict | None) -> list[dict]:
    out = []
    for r in (body or {}).get("organic_results") or []:
        price = r.get("price")
        if isinstance(price, dict):
            price = price.get("raw") or price.get("extracted")
        seller = (r.get("seller") or {}).get("username") if isinstance(r.get("seller"), dict) else None
        out.append({"title": r.get("title") or "", "subtitle": r.get("subtitle"), "condition": r.get("condition"),
                    "price": str(price) if price is not None else None, "link": r.get("link"),
                    "thumbnail": r.get("thumbnail"), "seller_hash": seller_hash(seller),
                    "item_id": str(r.get("product_id") or r.get("item_id") or (r.get("link") or "").rsplit("/", 1)[-1])})
    return out
