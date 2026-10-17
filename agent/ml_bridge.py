"""Thin adapter between the agent and ml/ (owned by the ML agent).

Prefers ml.infer / ml.heuristic / ml.spec_extract when they exist and import cleanly; otherwise uses
agent.fallback. Every result says which path produced it, so the UI/card can label heuristic output.

    provider()                  -> "tinker" | "openai" | "heuristic"
    describe()                  -> {"provider", "model", "classifier": "ml.infer"|"agent.fallback", ...}
    classify(spec, listing)     -> (MatchVerdict, meta)   raises InvalidModelOutput on bad JSON
    heuristic(spec, listing)    -> (MatchVerdict, meta)   always works, zero keys
    retrieve(text, specs, k)    -> [recall_number]
    spec_for(recall)            -> (RecallSpec, source)
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import time
from functools import lru_cache

from agent import fallback
from agent.config import DATA_DIR, has_key
from shared.schema import Listing, MatchVerdict, RecallSpec

log = logging.getLogger("recalldesk")


class InvalidModelOutput(ValueError):
    pass


@lru_cache(maxsize=None)
def _mod(name: str):
    try:
        return importlib.import_module(name)
    except Exception as e:  # missing, or broken mid-edit by the ML agent: never take the agent down
        if not isinstance(e, ModuleNotFoundError):
            log.warning("could not import %s (%s: %s) - using agent fallback", name, type(e).__name__, e)
        return None


def provider() -> str:
    p = os.environ.get("RECALLDESK_MODEL_PROVIDER", "").strip().lower()
    if p in ("tinker", "openai", "heuristic"):
        return p
    m = _mod("ml.infer")
    fn = next((getattr(m, n) for n in ("active_provider", "provider") if m is not None and hasattr(m, n)), None)
    if fn is not None:
        try:
            return str(fn())
        except Exception:
            pass
    return "tinker" if has_key("TINKER_API_KEY") and (
        os.environ.get("RECALLDESK_TINKER_MODEL_PATH") or (DATA_DIR.parent / "ml" / "results" / "model_path.txt").exists()
    ) else "heuristic"


def _lora_name() -> str:
    c = _mod("ml.common")
    return getattr(c, "LORA_MODEL_NAME", "qwen3.5-4b-recalldesk-lora") if c else "qwen3.5-4b-recalldesk-lora"


def describe() -> dict:
    p = provider()
    infer = _mod("ml.infer")
    d = {"provider": p, "classifier": "ml.infer" if (infer and hasattr(infer, "classify")) else "agent.fallback"}
    if infer is not None and hasattr(infer, "describe"):
        try:
            d.update(infer.describe())
            return d
        except Exception:
            pass
    if p == "tinker":
        d["model"] = _lora_name()
    elif p == "openai":
        d["model"] = os.environ.get("RECALLDESK_MODEL", "openai-compatible")
    else:
        d["model"] = HEURISTIC_LABEL
    return d


HEURISTIC_LABEL = f"{fallback.HEURISTIC_NAME} (heuristic, no model key)"


def _coerce(v) -> MatchVerdict:
    if isinstance(v, tuple):
        v = v[0]
    if isinstance(v, MatchVerdict):
        return v
    if isinstance(v, dict) and "verdict" in v:
        return MatchVerdict.model_validate(v)
    if hasattr(v, "model_dump"):
        return MatchVerdict.model_validate(v.model_dump())
    if isinstance(v, str):
        from shared.schema import parse_verdict

        mv, err = parse_verdict(v)
        if mv is None:
            raise InvalidModelOutput(f"model returned invalid JSON ({err}): {v[:80]!r}")
        return mv
    raise InvalidModelOutput(f"model returned {type(v).__name__}, not a MatchVerdict")


def heuristic(spec: RecallSpec, listing: Listing) -> tuple[MatchVerdict, dict]:
    t0 = time.perf_counter()
    h = _mod("ml.heuristic")
    src = "agent.fallback"
    v = None
    fn = next((getattr(h, n) for n in ("classify_heuristic", "classify") if h is not None and hasattr(h, n)), None)
    if fn is not None and os.environ.get("RECALLDESK_AGENT_HEURISTIC") != "1":
        try:
            v = _coerce(fn(spec, listing))
            src = "ml.heuristic"
        except Exception as e:
            log.debug("ml.heuristic.classify failed (%s) - agent fallback", e)
    if v is None:
        v = fallback.heuristic_classify(spec, listing)
    return v, {"model": HEURISTIC_LABEL, "provider": "heuristic", "source": src,
               "latency_ms": int((time.perf_counter() - t0) * 1000), "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}


def classify(spec: RecallSpec, listing: Listing) -> tuple[MatchVerdict, dict]:
    """The configured provider. Invalid output raises InvalidModelOutput (the activity retries it)."""
    p = provider()
    infer = _mod("ml.infer")
    if p == "heuristic" or infer is None or not hasattr(infer, "classify"):
        return heuristic(spec, listing)
    t0 = time.perf_counter()
    try:
        raw = infer.classify(spec, listing)
    except (ValueError, json.JSONDecodeError) as e:
        raise InvalidModelOutput(f"invalid model output: {e}"[:300]) from e
    v = _coerce(raw)
    meta = {"model": describe().get("model", p), "provider": p, "source": "ml.infer",
            "latency_ms": int((time.perf_counter() - t0) * 1000)}
    if isinstance(raw, tuple) and len(raw) > 1 and isinstance(raw[1], dict):
        meta.update({k: v_ for k, v_ in raw[1].items() if v_ is not None})
        meta["source"] = "ml.infer"
    if str(meta.get("provider", "")).startswith("heuristic (fallback"):
        # ml.infer already re-sampled and gave up: surface it as invalid output so Temporal retries the
        # activity; on the final attempt the activity itself answers with the (labelled) heuristic.
        raise InvalidModelOutput(f"model returned invalid JSON {meta.get('attempts', 2)}x ({p})")
    if meta.get("model") and "cost_usd" not in meta:
        c = _mod("ml.common")
        if c is not None and hasattr(c, "sample_cost_usd"):
            try:
                base = getattr(c, "STUDENT_MODEL", "")
                meta["cost_usd"] = c.sample_cost_usd(base, int(meta.get("tokens_in") or 0), int(meta.get("tokens_out") or 0))
            except Exception:
                pass
    last = getattr(infer, "last_usage", None)  # optional: ml.infer may expose token usage of the last call
    if callable(last):
        try:
            meta.update(last() or {})
        except Exception:
            pass
    elif isinstance(last, dict):
        meta.update(last)
    return v, meta


# ------------------------------------------------------------------------------------- retrieval
def retrieve(text: str, specs: list[RecallSpec], titles: dict[str, str], k: int = 3) -> list[str]:
    """Top-k recall_numbers for an item. Exact identifier hits are always included."""
    infer = _mod("ml.infer")
    out: list[str] = []
    if infer is not None and hasattr(infer, "retrieve"):
        try:
            r = infer.retrieve(text, specs, k=k)
            for x in r or []:
                rn = x if isinstance(x, str) else (getattr(x, "recall_number", None) or (
                    x.get("recall_number") if isinstance(x, dict) else None) or (
                    x[0] if isinstance(x, tuple) and isinstance(x[0], str) else None))
                if rn and rn not in out:
                    out.append(rn)
        except Exception as e:
            log.debug("ml.infer.retrieve failed (%s) - BM25 fallback", e)
            out = []
    if not out:
        bm = _bm25(tuple(s.recall_number for s in specs), specs, titles)
        out = [rn for rn, _ in bm.search(text, k=k)]
    ct = fallback.compact(text)
    for s in specs:  # identifier hit beats any ranking
        if s.recall_number not in out and any(len(fallback.compact(i)) >= 5 and fallback.compact(i) in ct
                                              for i in s.model_numbers + s.upcs):
            out.append(s.recall_number)
    return out


_BM_CACHE: dict = {}


def _bm25(key: tuple, specs: list[RecallSpec], titles: dict[str, str]) -> fallback.BM25:
    if key not in _BM_CACHE:
        _BM_CACHE.clear()
        _BM_CACHE[key] = fallback.BM25({s.recall_number: fallback.spec_doc(s, titles.get(s.recall_number, ""))
                                        for s in specs})
    return _BM_CACHE[key]


# ----------------------------------------------------------------------------------------- specs
def data_version() -> tuple:
    """mtimes of the files specs/recalls come from - caches key on this so new teacher specs show up live."""
    ps = [DATA_DIR / "specs" / "specs.jsonl", DATA_DIR / "specs" / "specs.heuristic.jsonl",
          DATA_DIR / "recalls" / "recalls.jsonl"]
    return tuple((p.name, p.stat().st_mtime) for p in ps if p.exists())


def _spec_cache_file() -> dict[str, dict]:
    return _spec_cache_versioned(data_version())


@lru_cache(maxsize=2)
def _spec_cache_versioned(_version: tuple) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name in ("specs.heuristic.jsonl", "specs.jsonl"):  # teacher specs override heuristic ones
        p = DATA_DIR / "specs" / name
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        r = json.loads(line)
                        out[r["recall_number"]] = {**r, "_source": "teacher" if name == "specs.jsonl" else "ml-heuristic"}
                    except (json.JSONDecodeError, KeyError):
                        pass
    return out


def spec_for(recall: dict, allow_model: bool = True) -> tuple[RecallSpec, str]:
    """Cached teacher spec -> live teacher (ml.spec_extract, needs TINKER key) -> heuristic spec."""
    rn = recall["recall_number"]
    cached = _spec_cache_file().get(rn)
    if cached:
        src = cached.get("_source", "teacher")
        return RecallSpec.model_validate({k: v for k, v in cached.items() if k != "_source"}), f"cached {src} spec"
    if allow_model and has_key("TINKER_API_KEY"):
        m = _mod("ml.spec_extract")
        fn = next((getattr(m, n) for n in ("extract_one", "extract_spec", "spec_for_recall") if m and hasattr(m, n)), None)
        if fn is not None:
            r = fn(recall)
            if isinstance(r, tuple):
                r = r[0]
            if r is not None:
                return (r if isinstance(r, RecallSpec) else RecallSpec.model_validate(r)), "teacher (live)"
    h = _mod("ml.heuristic")
    if h is not None and hasattr(h, "spec_from_record"):
        try:
            return h.spec_from_record(recall), "heuristic spec (ml.heuristic)"
        except Exception as e:
            log.debug("ml.heuristic.spec_from_record failed (%s)", e)
    return fallback.heuristic_spec(recall), "heuristic spec (agent.fallback)"
