"""RecallDesk inference - what agent/ imports. No keys or heavy deps needed at import time.

    from ml.infer import classify, classify_batch, retrieve, active_provider
    verdict, meta = classify(spec, listing)            # MatchVerdict, {latency_ms,tokens_in,tokens_out,model,provider}
    hits = retrieve("Woodure kitchen tower WD1720", specs, k=5)   # [{"recall_number","score","id_hit","spec"}]

`spec` = RecallSpec | dict (a RecallRecord dict also works: a heuristic spec is derived). `listing` = Listing |
dict with at least "title" (an inventory row: {"listing_id":"inv:shop:1","source":"inventory","title":"...",
"item_specifics":{"brand":..,"model":..,"notes":..}}).

Provider (argument, else env RECALLDESK_MODEL_PROVIDER):
  tinker     Tinker SamplingClient on the LoRA (RECALLDESK_TINKER_MODEL_PATH or ml/results/model_path.txt);
             RECALLDESK_TINKER_BASE_MODEL=<hf id> samples a base model instead. Needs TINKER_API_KEY.
  openai     OpenAI-compatible server: RECALLDESK_BASE_URL + RECALLDESK_MODEL (+ RECALLDESK_API_KEY).
             For Tinker's OAI endpoint (base_url https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1,
             model = tinker://.../sampler_weights/...) we call /completions with the exact Qwen3.5 non-thinking
             template used in training (the /chat/completions route applies the HF default template) and
             authenticate with TINKER_API_KEY. Other servers (Ollama / llama.cpp / vLLM) use /chat/completions.
  heuristic  deterministic identifier/keyword rules (ml/heuristic.py), zero keys - clearly labelled.
  (unset)    tinker if TINKER_API_KEY + a model path exist, else heuristic.
Provider errors raise (so Temporal activities retry). Invalid JSON twice -> heuristic verdict with
meta.provider = "heuristic (fallback from <provider>)".
"""
from __future__ import annotations

import math
import os
import re
import threading
import time
from collections import Counter
from typing import Any

from ml.common import LORA_MODEL_NAME, ROOT, STUDENT_MODEL, TINKER_OAI_BASE_URL, load_env, tinker_model_path
from ml.prompts import STUDENT_SYSTEM, user_prompt
from shared.schema import Listing, MatchVerdict, RecallRecord, RecallSpec, parse_verdict

_lock = threading.Lock()
_tinker_state: dict = {}
MAX_TOKENS = 200


def _as_dict(x: Any) -> dict:
    return x.model_dump() if hasattr(x, "model_dump") else dict(x)


def _spec_dict(spec: Any) -> dict:
    if isinstance(spec, RecallRecord) or (isinstance(spec, dict) and "description" in spec and "brand" not in spec):
        from ml.heuristic import spec_from_record

        return spec_from_record(spec).model_dump()
    return _as_dict(spec)


def active_provider(provider: str | None = None) -> str:
    load_env()
    p = (provider or os.environ.get("RECALLDESK_MODEL_PROVIDER") or "").strip().lower()
    if p:
        return p
    return "tinker" if os.environ.get("TINKER_API_KEY") and tinker_model_path() else "heuristic"


# ------------------------------------------------------------------------------------- tinker
def _tinker():
    with _lock:
        if _tinker_state:
            return _tinker_state
        if not os.environ.get("TINKER_API_KEY"):
            raise RuntimeError("provider=tinker but TINKER_API_KEY is not set (repo-root .env)")
        import tinker

        from ml.common import make_renderer

        base = os.environ.get("RECALLDESK_TINKER_BASE_MODEL", "").strip()
        service = tinker.ServiceClient()
        if base:
            sc = service.create_sampling_client(base_model=base)
            name, renderer_model = base.split("/")[-1], base
        else:
            path = tinker_model_path()
            if not path:
                raise RuntimeError("provider=tinker needs RECALLDESK_TINKER_MODEL_PATH or ml/results/model_path.txt")
            sc = service.create_sampling_client(model_path=path)
            name, renderer_model = LORA_MODEL_NAME, STUDENT_MODEL
        _tok, renderer = make_renderer(renderer_model)
        _tinker_state.update(sc=sc, renderer=renderer, name=name, tinker=tinker)
        return _tinker_state


def _tinker_call(messages: list[dict], temperature: float) -> tuple[str, int, int, str]:
    st = _tinker()
    tinker, renderer = st["tinker"], st["renderer"]
    prompt = renderer.build_generation_prompt(messages)
    params = tinker.SamplingParams(max_tokens=MAX_TOKENS, temperature=temperature, seed=0,
                                   stop=renderer.get_stop_sequences())
    seq = st["sc"].sample(prompt=prompt, num_samples=1, sampling_params=params).result().sequences[0]
    toks = list(seq.tokens)
    msg, _ = renderer.parse_response(toks)
    c = msg.get("content")
    text = c if isinstance(c, str) else "".join(p.get("text", "") for p in (c or []) if isinstance(p, dict))
    return text, prompt.length, len(toks), st["name"]


# ------------------------------------------------------------------------------------- openai
def qwen35_prompt(messages: list[dict]) -> str:
    """Exact text of the cookbook `qwen3_5_disable_thinking` generation prompt (verified 2026-10-17)."""
    s = "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages)
    return s + "<|im_start|>assistant\n<think>\n\n</think>\n\n"


def _openai_call(messages: list[dict], temperature: float) -> tuple[str, int, int, str]:
    import httpx

    base = (os.environ.get("RECALLDESK_BASE_URL") or "http://localhost:11434/v1").rstrip("/")
    model = os.environ.get("RECALLDESK_MODEL") or ""
    is_tinker = "thinkingmachines" in base
    if is_tinker and not model:
        model = tinker_model_path() or ""
    if not model:
        raise RuntimeError("provider=openai needs RECALLDESK_MODEL (e.g. a tinker:// sampler path or an Ollama tag)")
    key = os.environ.get("RECALLDESK_API_KEY") or (os.environ.get("TINKER_API_KEY") if is_tinker else "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    mode = (os.environ.get("RECALLDESK_OAI_MODE") or ("completions" if is_tinker else "chat")).lower()
    if mode == "completions":
        r = httpx.post(f"{base}/completions", headers=headers, timeout=90, json={
            "model": model, "prompt": qwen35_prompt(messages), "max_tokens": MAX_TOKENS, "temperature": temperature,
            "stop": ["<|im_end|>"]})
        r.raise_for_status()
        j = r.json()
        text = j["choices"][0].get("text") or ""
    else:
        r = httpx.post(f"{base}/chat/completions", headers=headers, timeout=90, json={
            "model": model, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": temperature})
        r.raise_for_status()
        j = r.json()
        text = j["choices"][0]["message"].get("content") or ""
    u = j.get("usage") or {}
    name = LORA_MODEL_NAME if model.startswith("tinker://") else model
    return text, int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0), name


# ------------------------------------------------------------------------------------- public
def classify(spec: Any, listing: Any, provider: str | None = None,
             messages: list[dict] | None = None) -> tuple[MatchVerdict, dict]:
    """Classify one (recall spec, listing/inventory item) pair -> (MatchVerdict, meta)."""
    prov = active_provider(provider)
    sd, ld = _spec_dict(spec), _as_dict(listing)
    if prov == "heuristic":
        from ml.heuristic import classify_heuristic

        t0 = time.perf_counter()
        v = classify_heuristic(sd, ld)
        return v, {"latency_ms": round((time.perf_counter() - t0) * 1000, 3), "tokens_in": 0, "tokens_out": 0,
                   "model": "heuristic-rules", "provider": "heuristic"}
    if prov not in ("tinker", "openai"):
        raise ValueError(f"unknown provider {prov!r} (tinker|openai|heuristic)")
    if prov == "tinker":
        _tinker()  # one-time client/tokenizer setup is not counted as model latency
    msgs = messages or [{"role": "system", "content": STUDENT_SYSTEM}, {"role": "user", "content": user_prompt(sd, ld)}]
    call = _tinker_call if prov == "tinker" else _openai_call
    t0 = time.perf_counter()
    tin = tout = 0
    name = prov
    for attempt in range(2):
        text, a, b, name = call(msgs, 0.0 if attempt == 0 else 0.7)
        tin, tout = tin + a, tout + b
        v, _err = parse_verdict(text)
        if v is not None:
            return v, {"latency_ms": round((time.perf_counter() - t0) * 1000, 1), "tokens_in": tin, "tokens_out": tout,
                       "model": name, "provider": prov, "attempts": attempt + 1}
    from ml.heuristic import classify_heuristic

    return classify_heuristic(sd, ld), {"latency_ms": round((time.perf_counter() - t0) * 1000, 1), "tokens_in": tin,
                                        "tokens_out": tout, "model": "heuristic-rules",
                                        "provider": f"heuristic (fallback from {prov})", "attempts": 2}


def classify_batch(pairs: list[tuple[Any, Any]], provider: str | None = None,
                   max_workers: int = 16) -> list[tuple[MatchVerdict, dict]]:
    from concurrent.futures import ThreadPoolExecutor

    prov = active_provider(provider)
    if prov == "heuristic":
        return [classify(s, l, prov) for s, l in pairs]
    if prov == "tinker":
        _tinker()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(lambda sl: classify(sl[0], sl[1], prov), pairs))


# ------------------------------------------------------------------------------------- retrieval
_TOK = re.compile(r"[a-z0-9]+")
_RSTOP = {"the", "and", "with", "for", "of", "a", "in", "set", "new", "used", "kids", "baby", "pack", "lot"}


def _rtoks(s: str) -> list[str]:
    from ml.heuristic import stem

    return [stem(t) for t in _TOK.findall((s or "").lower().replace("™", " ").replace("®", " ")) if t not in _RSTOP]


class _BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = sum(map(len, docs)) / max(1, len(docs))
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, q: list[str]) -> list[float]:
        out = []
        for d, tf in zip(self.docs, self.tf):
            s = 0.0
            for t in set(q):
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            out.append(s)
        return out


_index_cache: dict[int, tuple[_BM25, list[dict]]] = {}


def _spec_doc(s: dict) -> list[str]:
    brand = s.get("brand") or ""
    return (_rtoks(brand) * 2 + _rtoks(s.get("product_name")) + _rtoks(s.get("product_type")) * 2
            + _rtoks(" ".join(s.get("model_numbers") or [])) * 3 + _rtoks(" ".join(s.get("upcs") or [])))


def retrieve(item_text: str, specs: Any, k: int = 5, min_score: float = 0.5) -> list[dict]:
    """BM25 over spec brand / product / type / model tokens. Exact identifier hits are ranked first.
    `specs`: list of RecallSpec/dicts or {recall_number: spec}."""
    from ml.regex_ids import find_ids_in_text

    lst = [_as_dict(s) for s in (specs.values() if isinstance(specs, dict) else specs)]
    key = id(specs)
    if key not in _index_cache or len(_index_cache[key][1]) != len(lst):
        _index_cache.clear()
        _index_cache[key] = (_BM25([_spec_doc(s) for s in lst]), lst)
    bm, lst = _index_cache[key]
    sc = bm.scores(_rtoks(item_text))
    hits = []
    for s, score in zip(lst, sc):
        ids = [*s.get("model_numbers", []), *s.get("upcs", [])]
        id_hit = find_ids_in_text(ids, item_text)
        if score >= min_score or id_hit:
            hits.append({"recall_number": s.get("recall_number"), "score": round(score + (10.0 if id_hit else 0), 3),
                         "id_hit": id_hit, "spec": s})
    hits.sort(key=lambda h: -h["score"])
    return hits[:k]


if __name__ == "__main__":  # quick manual check: python -m ml.infer
    from ml.common import load_specs, utf8_stdout

    utf8_stdout()
    specs = load_specs()
    hits = retrieve("Scotch thermal laminator TL1302Z", specs, k=3)
    for h in hits:
        print(h["recall_number"], h["score"], h["id_hit"], h["spec"]["product_name"])
    if hits:
        v, meta = classify(hits[0]["spec"], {"listing_id": "inv:demo:1", "source": "inventory",
                                             "title": "Scotch Thermal Laminator TL1302Z, used"})
        print(meta, v.model_dump_json())
    print("provider:", active_provider(), "| repo:", ROOT)
