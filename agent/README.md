# RecallDesk agent (backend)

Temporal workflows + FastAPI + Backboard memory + Sentry spans. Python 3.12. It runs with **zero keys**: the heuristic provider, a local memory store and the committed CPSC snapshot are used instead, and each one is labelled as such. Each key you add switches on the matching real service.

```bash
python -m uv venv --python 3.12 agent/.venv
python -m uv pip install --python agent/.venv/Scripts/python.exe -r agent/requirements.txt
#   (+ agent/requirements-tinker.txt for provider=tinker)

agent/.venv/Scripts/python.exe -m agent.dev --schedule
#   Temporal dev server :7233 (UI http://localhost:8233, DB agent/state/temporal-dev.db)
#   worker (task queue "recalldesk"), API http://localhost:8000, weekly Schedule
```

## Pipeline

```
WeeklyRecallSweep   (Temporal Schedule "recalldesk-weekly-sweep": Thursdays 14:00 America/New_York)
  fetch_new_recalls(since)        CPSC API; 5xx -> backoff (6 attempts); 4xx non-retryable; attempt>=3 -> snapshot
  extract_spec(recall) x N        cached teacher spec -> live teacher -> ml.heuristic.spec_from_record (labelled)
  InventoryCheckWorkflow (child) per watched shop, against this week's new specs

InventoryCheckWorkflow   (POST /api/check, or the sweep's child)
  load_inventory                  agent/fixtures_src/<shop>_inventory.csv when no items are posted
  load_specs                      corpus A (151 recalls since 2026-07-18) or AB (+ children's since 2023, 591)
  load_shop_memories              Backboard semantic search per item (local JSON store without a key)
  check_items                     retrieve_candidates (ml.infer.retrieve: BM25 + exact id hits, top-3)
                                  -> check_item per item, 6 concurrent, heartbeat 10s, 4 attempts;
                                     invalid model JSON -> retry; final attempt -> heuristic, labelled
                                     "heuristic-fallback" on the card; then CODE applies memory overrides
                                     and two downgrade-only guards (size/variant conflict, different brand)
  scan_ebay_store                 SerpApi eBay, seller filter _sasl+_saslop=1, cache data/serp/ (shared with ml/);
                                  quota/429 -> NOT retried, step note "source=snapshot (...)"
  compose_card -> publish_card    agent/cards/<safe_name(workflow_id)>.json, card_<week>_<shop>.json, latest_<shop>.json
```

The big model teaches, the small model reads, code decides. A shop memory such as "ours is the 2022 one, not recalled" overrides the model only when its `recall_number` matches and the remembered item covers at least 60% of this item's tokens (`backboard_memory.applies_to`). Each override is listed under `applied_memories` on the card.

## Demo shops (fictional), real recalls

| shop | inventory | corpus |
|---|---|---|
| `little-loop`: Little Loop Kids Consignment | 60 kids-resale items. 12 correspond to real CPSC recalls since 2026-07-18: 7 with model numbers (DO NOT SELL) and the rest needing a label check. Near-miss same-brand items, many clean items | AB |
| `flip-garage`: eBay household/tools flipper | 30 items: Scotch TL1302Z, BenQ GV31, YETI 3000X, HotHands H163650, ... | A |

`demo-shop` (the UI's default id) is an alias for `little-loop`. The demo correction lives in `fixtures_src/seed_memories.json`. The worker seeds it on boot if the shop has no memories: HARPPA Nordi tower, recall 26651, "ours is the 2022 one".

## API (CONTRACT.md + "Additions agreed with the UI")

| | |
|---|---|
| `GET /api/health` | temporal, model/provider, memory backend, which keys are set |
| `GET /api/recalls?since=&childrens=` | RecallRecord & {spec (+look_for, spec_source)}; default since 2026-07-18 |
| `GET /api/scan`, `GET /api/scan/{n}` | ml/results/scan_summary.json / data/listings + verdicts (teacher > model > live heuristic), `human_verified` from gold |
| `POST /api/check` `{shop_id, items[], corpus?}` | starts InventoryCheckWorkflow; empty items = shop inventory; inline (labelled) if Temporal is down |
| `GET /api/cards/{workflow_id}` | `{status, card?, steps[{name,status,attempt,started_at,ended_at,error?,note?}], workers?, resumed_after_crash?}` |
| `GET /api/cards/latest?shop_id=` | latest published card |
| `GET /api/runs` | recent runs (both workflow types) with `card_id`, `retries`, `summary` |
| `POST /api/shops/{id}/corrections` | `{listing_or_item, recall_number, correct_verdict, note}` -> `{memory_id, backend, text}` |
| `GET /api/shops/{id}/memories` | `[{memory_id, text, recall_number, correct_verdict, created_at, ...}]` |
| `GET /api/eval` | ml/results/eval.json, else placeholder fixture (`"placeholder": true`) |
| `GET /api/shops` | demo shops (extra) |

## Demo scripts (transcripts in `agent/demo_logs/`)

```bash
python -m agent.run_check little-loop          # 01: watch steps, print the card
python -m agent.run_check flip-garage          # 02
RECALLDESK_CHAOS=1 RECALLDESK_TASK_QUEUE=recalldesk-chaos python -m agent.worker   # 03: fake 503s, hangs, invalid JSON
RECALLDESK_TASK_QUEUE=recalldesk-chaos python -m agent.run_check little-loop
python -m agent.demo_crash                     # 04: hard-kill worker mid-check_items, restart, event-history proof
python -m agent.run_check sweep --since 2026-10-08   # 06: WeeklyRecallSweep now (same as the Thursday run)
python -m agent.schedule describe | trigger    # 07
python -m agent.backboard_memory list little-loop
python -m agent.make_fixtures                  # rebuild shared/fixtures/*.json from real runs
```

## Keys (root `.env`)

| key | without it | with it |
|---|---|---|
| `TINKER_API_KEY` (+ `ml/results/model_path.txt`) | `heuristic-rules-v1 (heuristic, no model key)` | Qwen3.5-4B + RecallDesk LoRA via `ml.infer.classify`, invalid JSON retried by Temporal; live teacher spec extraction |
| `SERPAPI_API_KEY` | store scan uses cached snapshots (labelled) | live eBay store scan for shops with `ebay_seller` (≤3 searches/week, cached forever) |
| `BACKBOARD_API_KEY` | `agent/state/memories/<shop>.json` (labelled `local`) | one Backboard assistant per shop; explicit memory endpoints only (never chat with memory=Auto) |
| `SENTRY_DSN` | no-op | transaction per activity attempt, `gen_ai.chat` span per classify (model, tokens, latency, cost) |
| `TEMPORAL_API_KEY` / `TEMPORAL_ADDRESS` | local dev server | Temporal Cloud (`python -m agent.dev --no-server`) |

Lessons carried over from the earlier Temporal + FastAPI project: filenames go through `safe_name` (Schedule workflow ids contain `:`), logging/event recording never fails an activity, and SerpApi 429/quota errors are never retried.
