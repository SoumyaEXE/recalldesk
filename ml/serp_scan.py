"""SerpApi eBay scan: one search per recall -> data/listings/listings.jsonl (+ search_index.jsonl).

    python -m ml.serp_scan --dry-run --corpus AB            # plan only: queries + how many searches would be spent
    python -m ml.serp_scan --corpus A --max-searches 151     # spend at most 151 NEW searches (cached ones are free)
    python -m ml.serp_scan --rebuild                         # re-normalize listings from the cache only (no network)

Params (https://serpapi.com/ebay-search-api): engine=ebay, ebay_domain=ebay.com, _nkw=<query>, _ipg=50.
Store filter (agent's "scan my eBay store"): _sasl=<seller username> (+ _saslop=1 = only that seller); there is
no `_ssn` param in the SerpApi eBay engine. Every raw response is cached at data/serp/<sha1(params)>.json
(gitignored, contains seller usernames) and a cached search is NEVER re-spent. Quota / 429 errors are not retried:
the scan stops and keeps what it has.

Library use (agent/):
    from ml.serp_scan import search_ebay, QuotaExceeded
    listings, meta = search_ebay("Scotch TL1302Z", seller=None, allow_spend=True)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Any

from ml.common import (LISTINGS, SERP, add_spend, spend_stage, load_env, load_recalls, load_specs, now_iso, read_jsonl, seller_hash,
                       sha1, specs_path, utf8_stdout, write_jsonl)
from shared.schema import Listing

ENDPOINT = "https://serpapi.com/search.json"


class QuotaExceeded(RuntimeError):
    """SerpApi says the plan is out of searches / rate limited. Not retryable."""


class NotCached(RuntimeError):
    """The search is not cached and spending was not allowed."""


def ebay_params(query: str, seller: str | None = None, ipg: int = 50, page: int = 1) -> dict[str, str]:
    p = {"engine": "ebay", "ebay_domain": "ebay.com", "_nkw": query, "_ipg": str(ipg)}
    if page > 1:
        p["_pgn"] = str(page)
    if seller:
        p["_sasl"] = seller
        p["_saslop"] = "1"
    return p


def cache_key(params: dict[str, str]) -> str:
    return sha1(json.dumps({k: v for k, v in sorted(params.items()) if k != "api_key"}, sort_keys=True))


def cache_path(params: dict[str, str]):
    return SERP / f"{cache_key(params)}.json"


def is_cached(params: dict[str, str]) -> bool:
    return cache_path(params).exists()


def fetch_raw(params: dict[str, str], allow_spend: bool = True) -> tuple[dict, bool]:
    """Return (raw_json, spent_a_search). Uses the cache whenever possible."""
    p = cache_path(params)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")), False
    if not allow_spend:
        raise NotCached(params.get("_nkw", ""))
    load_env()
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        raise SystemExit("SERPAPI_API_KEY is not set. Put SERPAPI_API_KEY=... in the repo-root .env and rerun "
                         "(get one at https://serpapi.com/manage-api-key). Use --dry-run to plan without a key.")
    import httpx

    last = None
    for attempt in range(3):
        try:
            r = httpx.get(ENDPOINT, params={**params, "api_key": key}, timeout=90)
        except httpx.HTTPError as e:  # network blip -> retry (no search is charged for a failed connection)
            last = e
            time.sleep(2 * 2 ** attempt)
            continue
        if r.status_code == 429:
            raise QuotaExceeded("SerpApi 429 (rate limit / out of searches)")
        try:
            data = json.loads(r.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            last = RuntimeError(f"bad SerpApi response {r.status_code}")
            time.sleep(2 * 2 ** attempt)
            continue
        err = (data.get("error") or "")
        if err and re.search(r"run out|plan|limit|quota|exceeded|invalid api key", err, re.I):
            raise QuotaExceeded(err)
        if r.status_code >= 500:
            last = RuntimeError(f"SerpApi {r.status_code}: {err}")
            time.sleep(2 * 2 ** attempt)
            continue
        # success OR a "no results" style error: both are spent searches -> cache them
        data.setdefault("search_parameters", {}).pop("api_key", None)
        data["_recalldesk"] = {"params": params, "fetched_at": now_iso()}
        SERP.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data, True
    raise RuntimeError(f"SerpApi request failed: {last!r}")


# ------------------------------------------------------------------------------- normalization
def _price(x: Any) -> str | None:
    if not x:
        return None
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        if x.get("raw"):
            return x["raw"]
        lo, hi = (x.get("from") or {}).get("raw"), (x.get("to") or {}).get("raw")
        if lo and hi:
            return f"{lo} - {hi}"
        return lo or hi
    return str(x)


def item_id(res: dict) -> str | None:
    m = re.search(r"/itm/(?:[^/?]+/)?(\d{9,15})", res.get("link") or "")
    return m.group(1) if m else (str(res["product_id"]) if res.get("product_id") else None)


def normalize(raw: dict, recall_number: str | None = None) -> list[Listing]:
    meta = raw.get("_recalldesk") or {}
    q = (meta.get("params") or {}).get("_nkw") or (raw.get("search_parameters") or {}).get("_nkw")
    fetched = meta.get("fetched_at") or (raw.get("search_metadata") or {}).get("created_at")
    out = []
    for res in raw.get("organic_results") or []:
        iid = item_id(res)
        if not iid or not res.get("title"):
            continue
        link = f"https://www.ebay.com/itm/{iid}"
        specifics: dict[str, Any] = {}
        if res.get("extensions"):
            specifics["extensions"] = res["extensions"]
        if res.get("buying_format_text") or res.get("buying_format"):
            specifics["format"] = res.get("buying_format_text") or res.get("buying_format")
        if res.get("location"):
            specifics["location"] = res["location"]
        if res.get("sponsored"):
            specifics["sponsored"] = True
        out.append(Listing(
            listing_id=f"ebay:{iid}", source="ebay", title=res["title"].strip(), subtitle=res.get("subtitle"),
            condition=res.get("condition"), price=_price(res.get("price")), link=link, thumbnail=res.get("thumbnail"),
            seller_hash=seller_hash((res.get("seller") or {}).get("username")), item_specifics=specifics, query=q,
            recall_number=recall_number, fetched_at=fetched,
        ))
    return out


def search_ebay(query: str, seller: str | None = None, allow_spend: bool = True, recall_number: str | None = None,
                ipg: int = 50) -> tuple[list[dict], dict]:
    """One eBay search (cached). Returns (listings as dicts, meta{cached, spent, n, error}). Raises QuotaExceeded."""
    params = ebay_params(query, seller=seller, ipg=ipg)
    raw, spent = fetch_raw(params, allow_spend=allow_spend)
    ls = [x.model_dump() for x in normalize(raw, recall_number)]
    return ls, {"cached": not spent, "spent": spent, "n": len(ls), "error": raw.get("error"),
                "cache_key": cache_key(params), "query": query, "seller_filter": bool(seller)}


# ------------------------------------------------------------------------------------- planning
def recall_query(rec: dict, spec: dict | None) -> str:
    if spec and spec.get("search_queries"):
        return spec["search_queries"][0]
    # deterministic fallback: brand-ish title head + product name (+ first regex id)
    head = re.split(r"\s+(?:Expands\s+)?Recalls?\b|\s+Recalled\b", rec.get("title") or "")[0]
    name = (rec.get("product_names") or [""])[0]
    q = f"{head} {name}".replace("™", "").replace("®", "")
    if rec.get("regex_ids"):
        q += " " + rec["regex_ids"][0]
    return " ".join(dict.fromkeys(q.split()))[:80]


def plan(corpus: str) -> list[dict]:
    recs = load_recalls(corpus)
    specs = load_specs()
    rows = []
    for r in recs:
        q = recall_query(r, specs.get(r["recall_number"]))
        params = ebay_params(q)
        rows.append({"recall_number": r["recall_number"], "query": q, "cached": is_cached(params),
                     "cache_key": cache_key(params), "is_childrens": r.get("is_childrens", False),
                     "corpus": r.get("corpus", []), "recall_date": r.get("recall_date", "")})
    # A first, then B; newest recall first within each, so a capped budget spends on the most recent recalls
    rows.sort(key=lambda x: x["recall_date"], reverse=True)
    rows.sort(key=lambda x: (0 if "A" in x["corpus"] else 1))
    return rows


def rebuild_listings() -> tuple[int, int]:
    """Re-normalize every indexed search from the cache into listings.jsonl (first recall wins per listing)."""
    index = read_jsonl(LISTINGS / "search_index.jsonl")
    by_id: dict[str, dict] = {}
    for row in index:
        p = SERP / f"{row['cache_key']}.json"
        if not p.exists():
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        ids = []
        for lst in normalize(raw, row["recall_number"]):
            ids.append(lst.listing_id)
            by_id.setdefault(lst.listing_id, lst.model_dump())
        row["listing_ids"] = list(dict.fromkeys(ids))
        row["n_results"] = len(row["listing_ids"])
    write_jsonl(LISTINGS / "search_index.jsonl", index)
    write_jsonl(LISTINGS / "listings.jsonl", by_id.values())
    return len(index), len(by_id)


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="A", choices=["A", "B", "AB"])
    ap.add_argument("--max-searches", type=int, default=0, help="max NEW (uncached) searches to spend; 0 = none")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild", action="store_true", help="only rebuild listings.jsonl from cached searches")
    ap.add_argument("--show", type=int, default=15, help="dry-run: how many planned queries to print")
    args = ap.parse_args()
    print(f"specs source: {specs_path().name}")
    if args.rebuild:
        n_s, n_l = rebuild_listings()
        print(f"rebuilt: {n_s} searches -> {n_l} unique listings")
        return
    rows = plan(args.corpus)
    uniq_q = {r["cache_key"] for r in rows}
    to_spend = [r for r in rows if not r["cached"]]
    to_spend_u = list({r["cache_key"]: r for r in to_spend}.values())
    print(f"corpus {args.corpus}: {len(rows)} recalls, {len(uniq_q)} unique queries, "
          f"{len(rows) - len(to_spend)} cached, {len(to_spend_u)} searches needed "
          f"({sum(r['is_childrens'] for r in to_spend_u)} children's)")
    if args.dry_run:
        for r in rows[: args.show]:
            print(f"  {'cached ' if r['cached'] else 'SPEND  '} {r['recall_number']}  {r['query']}")
        return
    index = {(r["recall_number"], r["cache_key"]): r for r in read_jsonl(LISTINGS / "search_index.jsonl")}
    spent = 0
    stopped = None
    for r in rows:
        params = ebay_params(r["query"])
        need_spend = not is_cached(params)
        if need_spend and spent >= args.max_searches:
            continue
        try:
            raw, did = fetch_raw(params, allow_spend=need_spend)
        except QuotaExceeded as e:
            stopped = str(e)
            print(f"STOP: SerpApi quota/limit: {e}")
            break
        spent += did
        n = len(raw.get("organic_results") or [])
        index[(r["recall_number"], r["cache_key"])] = {
            "recall_number": r["recall_number"], "query": r["query"], "cache_key": r["cache_key"],
            "searched_at": (raw.get("_recalldesk") or {}).get("fetched_at"), "n_results": n,
            "error": raw.get("error"), "listing_ids": []}
        if did and spent % 10 == 0:
            print(f"  spent {spent} searches ...")
            write_jsonl(LISTINGS / "search_index.jsonl", index.values())
    write_jsonl(LISTINGS / "search_index.jsonl", index.values())
    n_s, n_l = rebuild_listings()
    old = spend_stage("serp_scan")
    add_spend("serp_scan", {"searches_spent": old.get("searches_spent", 0) + spent, "searches_indexed": n_s,
                            "unique_listings": n_l, "est_usd": 0.0, "stopped": stopped})
    print(f"spent {spent} new searches this run; index={n_s} searches; listings={n_l} unique")


if __name__ == "__main__":
    main()
