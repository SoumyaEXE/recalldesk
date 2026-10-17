"""Async helpers for classifying (recall, listing) pairs with a Tinker SamplingClient (teacher labels, eval)."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from shared.schema import parse_verdict


@dataclass
class SampleResult:
    text: str = ""
    verdict: Any = None  # MatchVerdict | None
    error: str | None = None
    latency_ms: float = 0.0  # latency of the FIRST attempt (what a single call costs)
    total_ms: float = 0.0
    attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0  # summed over attempts (for cost)
    first_valid: bool = False  # was attempt #1 valid? (json_valid metric uses this)
    first_text: str = ""
    extra: dict = field(default_factory=dict)


def _text_of(renderer, tokens: list[int]) -> str:
    msg, _term = renderer.parse_response(tokens)
    content = msg.get("content")
    return content if isinstance(content, str) else "".join(
        p.get("text", "") for p in (content or []) if isinstance(p, dict) and p.get("type") == "text")


async def classify_one(sampling_client, renderer, messages: list[dict], *, max_tokens: int = 200,
                       retries: int = 0, temperature: float = 0.0, seed: int | None = 0) -> SampleResult:
    import tinker

    prompt = renderer.build_generation_prompt(messages)
    stop = renderer.get_stop_sequences()
    res = SampleResult(prompt_tokens=prompt.length)
    t_all = time.perf_counter()
    for attempt in range(retries + 1):
        params = tinker.SamplingParams(max_tokens=max_tokens, temperature=temperature if attempt == 0 else 0.7,
                                       seed=None if seed is None else seed + attempt, stop=stop)
        t0 = time.perf_counter()
        out = await sampling_client.sample_async(prompt=prompt, num_samples=1, sampling_params=params)
        dt = (time.perf_counter() - t0) * 1000
        tokens = list(out.sequences[0].tokens)
        res.completion_tokens += len(tokens)
        text = _text_of(renderer, tokens)
        verdict, err = parse_verdict(text)
        res.attempts = attempt + 1
        if attempt == 0:
            res.latency_ms, res.first_valid, res.first_text = dt, verdict is not None, text
        res.text, res.verdict, res.error = text, verdict, err
        if verdict is not None:
            break
    res.total_ms = (time.perf_counter() - t_all) * 1000
    return res


async def classify_many(sampling_client, renderer, items: list[tuple[str, list[dict]]], *, concurrency: int = 16,
                        on_result=None, **kw) -> dict[str, SampleResult]:
    sem = asyncio.Semaphore(concurrency)
    results: dict[str, SampleResult] = {}

    async def run(key: str, msgs: list[dict]):
        async with sem:
            r = SampleResult(error="not_run")
            for net_try in range(4):  # transient API errors (rate limits, 5xx) -> back off and retry
                try:
                    r = await classify_one(sampling_client, renderer, msgs, **kw)
                    break
                except Exception as e:  # noqa: BLE001
                    if net_try == 3:
                        r = SampleResult(error=f"api_error: {e!r}"[:300])
                    else:
                        await asyncio.sleep(2 ** net_try * 3)
            results[key] = r
            if on_result:
                on_result(key, r)

    await asyncio.gather(*(run(k, m) for k, m in items))
    return results
