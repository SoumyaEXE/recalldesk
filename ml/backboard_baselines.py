"""Optional baselines: send the SAME test prompts to other open-weight models through Backboard (one key).

    python -m ml.backboard_baselines --list-models [--provider openrouter] [--grep llama]
    python -m ml.backboard_baselines --models "openrouter:meta-llama/llama-3.3-70b-instruct,openrouter:qwen/qwen3-32b"
    python -m ml.eval --rebuild-only            # picks up ml/results/preds/backboard_*.jsonl

API (https://docs.backboard.io, verified 2026-10-17): POST https://app.backboard.io/api/threads/messages with header
X-API-Key, JSON {content, system_prompt, llm_provider, model_name, memory: "off", json_output, stream: false};
the response has content, input_tokens, output_tokens, model_provider. GET /api/models?model_type=llm&provider=...
lists the library (OpenRouter / Featherless / Cerebras host the open-weight models).
Prompt: the teacher's long rulebook + the student's input (= role base_guided), so un-tuned models get the
full rules. One attempt, temperature default, invalid JSON = wrong. Resume-safe per (model, pair).
"""
from __future__ import annotations

import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor

from ml.common import RESULTS, read_jsonl, require_key, utf8_stdout, write_jsonl
from shared.schema import parse_verdict

API = "https://app.backboard.io/api"
PREDS = RESULTS / "preds"
DEFAULT_MODELS = "openrouter:meta-llama/llama-3.3-70b-instruct,openrouter:qwen/qwen3-32b,openrouter:openai/gpt-oss-20b"


def slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def list_models(key: str, provider: str | None, grep: str | None) -> None:
    import httpx

    params = {"model_type": "llm", "limit": 500}
    if provider:
        params["provider"] = provider
    r = httpx.get(f"{API}/models", params=params, headers={"X-API-Key": key}, timeout=60)
    r.raise_for_status()
    data = r.json()
    models = data.get("models", data) if isinstance(data, dict) else data
    for m in models:
        name = f"{m.get('provider')}:{m.get('name')}"
        if grep and grep.lower() not in name.lower():
            continue
        print(f"{name:70s} in ${m.get('input_cost_per_1m_tokens')}/M out ${m.get('output_cost_per_1m_tokens')}/M "
              f"ctx {m.get('context_limit')}")


def call(key: str, provider: str, model: str, system: str, user: str) -> dict:
    import httpx

    body = {"content": user, "system_prompt": system, "llm_provider": provider, "model_name": model,
            "memory": "off", "web_search": "off", "json_output": True, "stream": False}
    t0 = time.perf_counter()
    for attempt in range(3):
        r = httpx.post(f"{API}/threads/messages", json=body, headers={"X-API-Key": key}, timeout=120)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(3 * 2 ** attempt)
            continue
        if r.status_code == 400 and body.get("json_output") and attempt < 2:
            body.pop("json_output")  # some models reject JSON mode; fall back to plain text
            continue
        r.raise_for_status()
        j = r.json()
        return {"text": j.get("content") or "", "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "tokens_in": j.get("input_tokens") or 0, "tokens_out": j.get("output_tokens") or 0,
                "status": j.get("status"), "provider_used": j.get("model_provider")}
    raise RuntimeError("unreachable")


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=DEFAULT_MODELS, help="comma list of provider:model")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--grep", default=None)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    key = require_key("BACKBOARD_API_KEY", "Backboard baselines")
    if args.list_models:
        list_models(key, args.provider, args.grep)
        return
    from ml.eval import load_test, messages_for

    rows, _gold, ctx = load_test("human")
    if args.limit:
        rows = rows[: args.limit]
    PREDS.mkdir(parents=True, exist_ok=True)
    for spec in [m.strip() for m in args.models.split(",") if m.strip()]:
        provider, model = spec.split(":", 1)
        out_p = PREDS / f"backboard_{slug(model)}.jsonl"
        done = {r["pair_id"]: r for r in read_jsonl(out_p) if not (r.get("error") or "").startswith("api_error")}
        todo = [r for r in rows if r["pair_id"] not in done]
        print(f"{provider}:{model}: {len(done)} done, {len(todo)} to do")

        def one(r):
            msgs = messages_for("guided", r, ctx)
            try:
                res = call(key, provider, model, msgs[0]["content"], msgs[1]["content"])
                v, err = parse_verdict(res["text"])
                return {"pair_id": r["pair_id"], "verdict": v.model_dump() if v else None, "valid": v is not None,
                        "latency_ms": res["latency_ms"], "tokens_in": res["tokens_in"], "tokens_out": res["tokens_out"],
                        "error": None if v else err, "output_text": res["text"][:1500], "model": model,
                        "provider": provider, "prompt": "guided", "role": f"backboard:{model}"}
            except Exception as e:  # noqa: BLE001
                return {"pair_id": r["pair_id"], "verdict": None, "valid": False, "error": f"api_error: {e!r}"[:300],
                        "model": model, "provider": provider, "prompt": "guided", "role": f"backboard:{model}",
                        "latency_ms": None, "tokens_in": 0, "tokens_out": 0}

        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            new = list(ex.map(one, todo))
        api_errs = sum(1 for x in new if (x.get("error") or "").startswith("api_error"))
        merged = {**done, **{x["pair_id"]: x for x in new}}
        write_jsonl(out_p, [merged[r["pair_id"]] for r in rows if r["pair_id"] in merged])
        ok = sum(x["valid"] for x in merged.values())
        print(f"  -> {out_p.name}: {ok}/{len(merged)} valid JSON, {api_errs} API errors (rerun to retry those)")
        if api_errs == len(new) and new:
            print("  all calls failed - check the model name with --list-models; first error:", new[0]["error"])


if __name__ == "__main__":
    main()
