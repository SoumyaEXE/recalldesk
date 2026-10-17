"""Optional Sentry tracing. Everything here is a no-op unless SENTRY_DSN is set.

Span conventions follow Sentry AI Agent Monitoring (sentry_sdk.consts.OP / SPANDATA):
  gen_ai.invoke_agent  "invoke_agent RecallDesk"      one transaction per check_item activity attempt
  gen_ai.chat          "chat <model>"                 one span per classify call (model, tokens, latency, cost)
  gen_ai.execute_tool  "execute_tool <activity>"      CPSC fetch, Backboard memory, SerpApi scan, publish
send_default_pii=False; listing/inventory text is truncated in span data and seller names are never sent.
"""
from __future__ import annotations

import contextlib
import logging
import os
import time

log = logging.getLogger("recalldesk")
_enabled = False


def init_sentry(component: str) -> bool:
    global _enabled
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
            send_default_pii=False,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "dev"),
            release=os.environ.get("SENTRY_RELEASE", "recalldesk@0.1.0"),
            server_name=f"recalldesk-{component}",
        )
        sentry_sdk.set_tag("component", component)
        _enabled = True
    except Exception as e:  # telemetry must never take the agent down
        log.warning("sentry init failed: %s", type(e).__name__)
    return _enabled


def enabled() -> bool:
    return _enabled


class _NullSpan:
    def finish_with(self, *a, **k):
        pass


class _ModelSpan:
    def __init__(self, span):
        self.span = span

    def finish_with(self, model_name: str, latency_ms: int, output: str, tokens_in: int | None = None,
                    tokens_out: int | None = None, cost_usd: float | None = None, source: str = ""):
        try:
            from sentry_sdk.consts import SPANDATA

            it = int(tokens_in or 0)
            ot = int(tokens_out or 0)
            s = self.span
            s.set_data(SPANDATA.GEN_AI_RESPONSE_MODEL, model_name)
            s.set_data(SPANDATA.GEN_AI_USAGE_INPUT_TOKENS, it)
            s.set_data(SPANDATA.GEN_AI_USAGE_OUTPUT_TOKENS, ot)
            s.set_data(SPANDATA.GEN_AI_USAGE_TOTAL_TOKENS, it + ot)
            s.set_data(SPANDATA.GEN_AI_RESPONSE_TEXT, output[:1000])
            s.set_data("recalldesk.model_latency_ms", int(latency_ms))
            s.set_data("recalldesk.cost_usd", round(float(cost_usd or 0.0), 8))
            s.set_data("recalldesk.verdict_source", source)
        except Exception:
            pass


@contextlib.contextmanager
def model_span(model: str, provider: str, recall_number: str, item_text: str):
    if not _enabled:
        yield _NullSpan()
        return
    import sentry_sdk
    from sentry_sdk.consts import OP, SPANDATA

    with sentry_sdk.start_span(op=OP.GEN_AI_CHAT, name=f"chat {model}") as span:
        span.set_data(SPANDATA.GEN_AI_OPERATION_NAME, "chat")
        span.set_data(SPANDATA.GEN_AI_REQUEST_MODEL, model)
        span.set_data(getattr(SPANDATA, "GEN_AI_PROVIDER_NAME", "gen_ai.provider.name"), provider)
        span.set_data("recalldesk.recall_number", recall_number)
        span.set_data("recalldesk.item", item_text[:120])
        t0 = time.perf_counter()
        yield _ModelSpan(span)
        span.set_data("recalldesk.wall_ms", int((time.perf_counter() - t0) * 1000))


@contextlib.contextmanager
def activity_span(op_name: str, name: str, **data):
    """One transaction per activity attempt."""
    if not _enabled:
        yield None
        return
    import sentry_sdk
    from sentry_sdk.consts import SPANDATA

    with sentry_sdk.start_transaction(op=op_name, name=name) as tx:
        tx.set_data(SPANDATA.GEN_AI_AGENT_NAME, "RecallDesk")
        for k, v in data.items():
            tx.set_data(k, v)
        yield tx


def capture(e: BaseException) -> None:
    if _enabled:
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(e)
        except Exception:
            pass
