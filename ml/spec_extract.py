"""RecallRecord -> RecallSpec, once per recall.

    python -m ml.spec_extract --provider heuristic            # zero keys -> data/specs/specs.heuristic.jsonl
    python -m ml.spec_extract --provider tinker [--corpus AB] [--limit N] [--concurrency 24]
                                                              # teacher (Qwen3.5-397B-A17B) -> data/specs/specs.jsonl

Teacher path: resume-safe (valid rows are kept), 2 retries on invalid JSON, schema-validated, identifiers that do
not occur in the notice are dropped (never invent ids), token/$ accounting into ml/results/spend.json.
Any teacher failure falls back to the heuristic spec for that recall (flagged `_source: heuristic_fallback`).

Single recall (agent/ml_bridge.spec_for, inside the Temporal `extract_spec` activity):
    from ml.spec_extract import extract_one
    spec = extract_one(record)                # teacher if TINKER_API_KEY is set, else ml.heuristic.spec_from_record
    spec = extract_one(record, "heuristic")   # force the zero-key path
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import threading
import time

from ml.common import (SPECS, TEACHER_MODEL, add_spend, has_key, spend_stage, load_recalls, make_renderer, read_jsonl,
                       require_key, sample_cost_usd, utf8_stdout, write_jsonl)
from ml.heuristic import spec_from_record
from ml.prompts import SPEC_SYSTEM, spec_user_prompt
from ml.regex_ids import norm_id
from shared.schema import RecallRecord, RecallSpec, parse_spec


def ground_ids(spec: RecallSpec, rec: dict) -> RecallSpec:
    """Drop identifiers the model produced that do not occur in the notice text."""
    hay = norm_id(" ".join([rec.get("description") or "", rec.get("title") or "", " ".join(rec.get("upcs") or []),
                            " ".join(rec.get("product_names") or [])]))

    def ok(i: str) -> bool:
        k = norm_id(re.sub(r"^(?:lot|batch|date code|serial(?: numbers?)?|sku|upc)\s*[:#]?\s*", "", i, flags=re.I))
        return bool(k) and k in hay

    return spec.model_copy(update={
        "model_numbers": [i for i in spec.model_numbers if ok(i)],
        "upcs": [i for i in spec.upcs if ok(i)],
        "other_identifiers": [i for i in spec.other_identifiers
                              if any(norm_id(t) in hay for t in re.findall(r"[A-Za-z0-9][\w\-./]*\d[\w\-./]*", i))],
        "is_childrens": spec.is_childrens or bool(rec.get("is_childrens")),
    })


def run_heuristic(recs: list[dict]) -> None:
    rows = [spec_from_record(r).model_dump() for r in recs]
    write_jsonl(SPECS / "specs.heuristic.jsonl", rows)
    with_ids = sum(bool(r["model_numbers"] or r["upcs"] or r["other_identifiers"]) for r in rows)
    print(f"heuristic specs: {len(rows)} -> data/specs/specs.heuristic.jsonl ({with_ids} with identifiers)")


async def _teacher_sample(sc, renderer, rec: dict) -> dict:
    """One recall through the teacher: up to 3 attempts (temp 0, then 0.6), schema-validated, not yet grounded.

    Returns {"spec", "error", "text", "attempts", "prompt_tokens", "completion_tokens"}.
    Shared by the batch run (run_tinker) and extract_one.
    """
    import tinker

    msgs = [{"role": "system", "content": SPEC_SYSTEM}, {"role": "user", "content": spec_user_prompt(rec)}]
    prompt = renderer.build_generation_prompt(msgs)
    stop = renderer.get_stop_sequences()
    res = {"spec": None, "error": None, "text": "", "attempts": 0, "prompt_tokens": 0, "completion_tokens": 0}
    for attempt in range(3):
        res["attempts"] = attempt + 1
        try:
            params = tinker.SamplingParams(max_tokens=900, temperature=0.0 if attempt == 0 else 0.6,
                                           seed=attempt, stop=stop)
            out = await sc.sample_async(prompt=prompt, num_samples=1, sampling_params=params)
        except Exception as e:  # noqa: BLE001 - transient API errors -> back off
            res["error"] = f"api_error: {e!r}"[:200]
            await asyncio.sleep(3 * 2 ** attempt)
            continue
        toks = list(out.sequences[0].tokens)
        res["prompt_tokens"] += prompt.length
        res["completion_tokens"] += len(toks)
        msg, _ = renderer.parse_response(toks)
        c = msg.get("content")
        text = c if isinstance(c, str) else "".join(p.get("text", "") for p in (c or []) if isinstance(p, dict))
        spec, err = parse_spec(text, rec["recall_number"])
        res.update(spec=spec, error=err, text=text)
        if spec is not None:
            break
    return res


# ------------------------------------------------------------------------------------- single recall
_RENDERER = None
_LIVE_LOCK = threading.Lock()


def _teacher_renderer():
    global _RENDERER
    if _RENDERER is None:
        _RENDERER = make_renderer(TEACHER_MODEL)[1]
    return _RENDERER


async def _extract_one_tinker(rec: dict) -> dict:
    import tinker

    renderer = _teacher_renderer()
    service = tinker.ServiceClient()
    sc = await service.create_sampling_client_async(base_model=TEACHER_MODEL)
    return await _teacher_sample(sc, renderer, rec)


def _run_coro(coro):
    """asyncio.run, also when the calling thread already has a running loop (then it runs on a helper thread)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict = {}

    def target():
        try:
            box["v"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001 - re-raised in the caller's thread
            box["e"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join()
    if "e" in box:
        raise box["e"]
    return box["v"]


def extract_one(record: RecallRecord | dict, provider: str | None = None) -> RecallSpec:
    """RecallRecord (or its dict) -> RecallSpec for ONE recall, e.g. a brand-new one in the weekly sweep.

    provider: "tinker" (teacher Qwen3.5-397B-A17B) | "heuristic" | None = tinker if TINKER_API_KEY is set, else
    heuristic (ml.heuristic.spec_from_record). The teacher path is the batch path's code: same prompt, 3 attempts,
    schema validation, identifiers grounded in the notice text, token/$ accounting (stage `spec_extract_live` in
    ml/results/spend.json). If the teacher returns no valid spec after 3 attempts this RAISES RuntimeError, so the
    caller (a Temporal activity) retries and then labels its own heuristic fallback, rather than a heuristic spec
    being passed off as a teacher one. Writes nothing under data/specs/.
    """
    rec = record.model_dump() if isinstance(record, RecallRecord) else dict(record)
    prov = (provider or "").strip().lower() or ("tinker" if has_key("TINKER_API_KEY") else "heuristic")
    if prov == "heuristic":
        return spec_from_record(rec)
    if prov != "tinker":
        raise ValueError(f"unknown provider {provider!r} (tinker|heuristic)")
    require_key("TINKER_API_KEY", "teacher spec extraction")
    r = _run_coro(_extract_one_tinker(rec))
    usd = sample_cost_usd(TEACHER_MODEL, r["prompt_tokens"], r["completion_tokens"])
    with _LIVE_LOCK:
        old = spend_stage("spec_extract_live")
        add_spend("spec_extract_live", {"model": TEACHER_MODEL, "recalls": old.get("recalls", 0) + 1,
                                        "prompt_tokens": old.get("prompt_tokens", 0) + r["prompt_tokens"],
                                        "completion_tokens": old.get("completion_tokens", 0) + r["completion_tokens"],
                                        "est_usd": round(old.get("est_usd", 0.0) + usd, 4)})
    if r["spec"] is None:
        raise RuntimeError(f"teacher spec failed for {rec.get('recall_number')} after {r['attempts']} attempts: "
                           f"{r['error']}")
    return ground_ids(r["spec"], rec)


async def run_tinker(recs: list[dict], args) -> None:
    import tinker

    out_p = SPECS / "specs.jsonl"
    log_p = SPECS / "specs.teacher_log.jsonl"
    existing = {r["recall_number"]: r for r in read_jsonl(out_p) if r.get("_source") == "teacher"}
    todo = [r for r in recs if r["recall_number"] not in existing]
    if args.limit:
        todo = todo[: args.limit]
    print(f"teacher={TEACHER_MODEL}: {len(recs)} recalls, {len(existing)} done, {len(todo)} to do")
    _tok, renderer = make_renderer(TEACHER_MODEL)
    service = tinker.ServiceClient()
    sc = await service.create_sampling_client_async(base_model=TEACHER_MODEL)
    sem = asyncio.Semaphore(args.concurrency)
    results: dict[str, dict] = {}
    pt_total = ct_total = 0
    t0 = time.time()
    logf = log_p.open("a", encoding="utf-8")

    async def one(rec: dict) -> None:
        nonlocal pt_total, ct_total
        async with sem:
            r = await _teacher_sample(sc, renderer, rec)
        spec, err, text, attempts = r["spec"], r["error"], r["text"], r["attempts"]
        pt_total += r["prompt_tokens"]
        ct_total += r["completion_tokens"]
        if spec is not None:
            spec = ground_ids(spec, rec)
            row = {**spec.model_dump(), "_source": "teacher"}
        else:
            row = {**spec_from_record(rec).model_dump(), "_source": "heuristic_fallback", "_error": err}
        results[rec["recall_number"]] = row
        logf.write(json.dumps({"recall_number": rec["recall_number"], "attempts": attempts, "error": err,
                               "raw": text[:3000]}, ensure_ascii=False) + "\n")
        logf.flush()
        if len(results) % 20 == 0 or len(results) == len(todo):
            print(f"  {len(results)}/{len(todo)} ({time.time() - t0:.0f}s)")

    try:
        await asyncio.gather(*(one(r) for r in todo))
    finally:
        logf.close()
    merged = {**existing, **results}
    order = [r["recall_number"] for r in recs]
    rows = [merged[n] for n in order if n in merged]
    # keep rows for recalls outside this --corpus selection, too
    prev_other = [r for r in read_jsonl(out_p) if r["recall_number"] not in set(order)]
    write_jsonl(out_p, rows + prev_other)
    usd = sample_cost_usd(TEACHER_MODEL, pt_total, ct_total)
    old = spend_stage("spec_extract")
    add_spend("spec_extract", {"model": TEACHER_MODEL, "recalls": len(rows),
                               "prompt_tokens": old.get("prompt_tokens", 0) + pt_total,
                               "completion_tokens": old.get("completion_tokens", 0) + ct_total,
                               "est_usd": round(old.get("est_usd", 0.0) + usd, 4)})
    n_t = sum(r.get("_source") == "teacher" for r in rows)
    print(f"specs: {len(rows)} ({n_t} teacher, {len(rows) - n_t} heuristic fallback) -> {out_p}; this run ~${usd:.3f}")


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["heuristic", "tinker"], default="heuristic")
    ap.add_argument("--corpus", default="AB")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=24)
    args = ap.parse_args()
    recs = load_recalls(args.corpus)
    if args.provider == "heuristic":
        run_heuristic(recs)
    else:
        require_key("TINKER_API_KEY", "teacher spec extraction")
        asyncio.run(run_tinker(recs, args))


if __name__ == "__main__":
    main()
