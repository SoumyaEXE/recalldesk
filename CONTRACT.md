# RecallDesk — shared build contract

> Before you list it, check it. A weekly recall check for resellers and kids' consignment shops.

Hackathon: DEV "Hacktoberfest Open-Source AI Challenge — Week 2: Side Hustle"
(https://dev.to/challenges/hacktoberfest-week2-2026-10-12). Theme: *build something with open-weight / open-source AI that someone would actually pay for.*
Deadline **2026-10-18 23:59 PDT** (= 2026-10-19 12:29 IST). Repo must be created and finished inside the window (it was created 2026-10-17).

Target categories (in priority order): **Tinker** ($200), **SerpApi**, **Temporal**, **Backboard**, **Entire**, then **Render** ($200), **.tech**, **Sentry**.
We do NOT target Gemma (174 entries), TabPFN, Copilot.

## Story in one paragraph
Reselling a recalled product is a federal violation in the US, and recalled baby gear keeps showing up on eBay, Marketplace and Craigslist
(Consumer Reports, 2026-10-06). CPSC publishes ~12 recalls every Thursday as walls of text; the model numbers that matter are buried
in the description (73 of the 151 recalls since 2026-07-18). Kids' consignment shops and eBay flippers check by hand, or don't.
RecallDesk: (1) a **big open-weight teacher** (Qwen3.5-397B-A17B on Tinker) turns each recall into an identification spec and labels
(recall, listing) pairs; (2) we **LoRA-fine-tune Qwen3.5-4B on Tinker** to decide `match | check | no_match` for a listing/inventory item
against a recall; (3) **SerpApi's eBay engine** finds live listings for every recall — the headline number; (4) a **Temporal** schedule
runs every Thursday after CPSC posts: fetch new recalls → specs → re-check each shop's inventory + eBay store → ONE printable card;
(5) **Backboard** stores each shop's corrections as memories ("ours is the 2019 model, not recalled"), retrieved semantically and applied
by code, and is the one-key harness for comparing other open-weight models as baselines. Then it goes quiet until next Thursday.

**Rule of the build: the big model teaches, the small model reads, code decides, a human grades.**

## Repo layout (each owner touches only their dir)
```
data/              raw recalls, specs, listings, pairs, splits, gold labels     (ML agent)
ml/                python: fetch, spec, serp scan, pairs, label UI, teacher, train, eval   (ML agent)
ml/results/        eval.json, predictions, scan_summary.json, spend.json        (ML agent)
shared/            schema.py (pydantic) + fixtures/*.json — canonical shapes      (ML agent owns schema.py; Backend writes fixtures)
agent/             python: Temporal workflows/activities/worker, FastAPI, Backboard memory, Sentry   (Backend agent)
web/               Next.js dashboard                                             (UI agent)
docs/              DEV post draft, visuals, screenshots                          (Writer, later)
```
Python 3.12 venvs (`py -3.12` is NOT on PATH; use `python -m uv venv --python 3.12 <dir>/.venv`). Windows host: no `:` in filenames.
Secrets only in root `.env` (gitignored). Never print keys in logs or commit them.

## Env (root `.env`, see `.env.example`)
```
TINKER_API_KEY=            # teacher + training + LoRA sampling
SERPAPI_API_KEY=           # eBay engine
BACKBOARD_API_KEY=         # memory + baseline harness
SENTRY_DSN=                # optional
RECALLDESK_MODEL_PROVIDER=tinker|openai|heuristic   (default heuristic if no key)
RECALLDESK_TINKER_MODEL_PATH=tinker://...           (written to ml/results/model_path.txt by training)
RECALLDESK_BASE_URL= / RECALLDESK_MODEL=            (openai-compatible local server: Ollama/llama.cpp/vLLM, or Tinker OAI endpoint)
```

## Data sources
- CPSC Recalls REST API (no key): `https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallDateStart=YYYY-MM-DD`
  (also `RecallDateEnd`, `RecallNumber`). Returns 22 fields/record. **Decode as UTF-8 explicitly** (the ™/’ chars come back mangled otherwise).
  Corpus A = all recalls since 2026-07-18 (151). Corpus B = children's-product recalls since 2023-01-01 (resale shops face old recalls too).
- SerpApi eBay: `engine=ebay`, `_nkw=<query>`, `ebay_domain=ebay.com`, `_ipg=50`. Cache EVERY response to `data/serp/` (keyed by sha1 of params);
  never re-spend a search that is cached. Budget-aware: script takes `--max-searches`.

## Canonical shapes (shared/schema.py is the source of truth; web/lib/types.ts mirrors it)

### `RecallRecord` (normalized CPSC record) — `data/recalls/recalls.jsonl`
```json
{"recall_number":"27024","recall_id":11022,"recall_date":"2026-10-15","title":"...","description":"...","url":"https://www.cpsc.gov/Recalls/...",
 "product_names":["Scotch Thermal Laminators"],"units":"About 53,634","hazards":["..."],"remedies":["..."],"remedy_options":["Refund"],
 "retailers":["Sold Online At: Amazon.com from June 2024 through September 2026..."],"manufacturers":["..."],"importers":["..."],
 "images":["https://..."],"upcs":[],"regex_ids":["TL1302Z"],"is_childrens":false,"corpus":["A"]}
```
`regex_ids` = deterministic extraction (model/item/style/SKU/UPC/lot patterns) — a baseline AND a code-side check.

### `RecallSpec` (teacher-extracted, once per recall) — `data/specs/specs.jsonl`
```json
{"recall_number":"27024","brand":"Scotch (3M)","product_type":"thermal laminator","product_name":"Scotch Thermal Laminator",
 "model_numbers":["TL1302Z"],"upcs":[],"other_identifiers":[],"sold_from":"2024-06","sold_to":"2026-09",
 "colors":["light gray/white"],"key_features":["13-inch slot","carrying handle on right side"],
 "not_included":[],"search_queries":["Scotch thermal laminator TL1302Z","Scotch TL1302Z"],
 "is_childrens":false,"hazard_short":"Overheats; fire hazard","remedy_short":"Stop using; refund from 3M"}
```

### `Listing` (eBay via SerpApi, or an inventory row) — `data/listings/listings.jsonl`
```json
{"listing_id":"ebay:1234567890","source":"ebay|inventory","title":"...","subtitle":null,"condition":"Pre-Owned","price":"$24.99",
 "link":"https://www.ebay.com/itm/...","thumbnail":"https://...","seller_hash":"s_3f9a1c","item_specifics":{},"query":"...","recall_number":"27024","fetched_at":"ISO"}
```
Seller usernames are hashed before anything is published (post, fixtures, UI). Raw SerpApi JSON stays in gitignored `data/serp/`.

### `MatchVerdict` — the model's ONLY output (strict JSON)
Model input = compact RecallSpec + Listing text (title, subtitle, condition, item_specifics). Never the gold label.
```json
{"verdict":"match|check|no_match","identifiers_found":["TL1302Z"],"conflicts":[],"reason":"Same Scotch laminator, model TL1302Z named in title."}
```
Labeling guide (humans and teacher use the SAME definitions — `ml/LABELING.md`):
- **match** — the listing *is* the recalled product: brand + product line agree AND (a recalled identifier appears, OR the recall covers all units of a product name the listing names unambiguously). Seller should not list it.
- **check** — same brand and product line, but the listing does not show what decides it (model no., date code, sold window, size/colour variant). Needs a look at the label before listing.
- **no_match** — different product/brand, a model the recall explicitly excludes, or only an accessory / part / manual / "compatible with" item / empty box.
Card mapping: match → **DO NOT SELL**, check → **CHECK LABEL**, no_match → clear (not shown).

### Pairs, splits, gold
- `data/pairs/pairs.jsonl`: `{"pair_id","recall_number","listing_id","split":"train|test"}`.
- **Split by recall** (held-out recalls never appear in train), stratified by is_childrens, seed 0. ~25–30 test recalls, ~200–250 test pairs.
- Teacher labels for ALL pairs: `data/labeled/teacher.jsonl` (`{"pair_id","verdict":MatchVerdict,"latency_ms","tokens_in","tokens_out"}`).
- **Gold** = human labels on test pairs only, via the blind labeling UI (`python -m ml.label_ui`, http://localhost:8765, keys 1/2/3, s=skip, u=undo):
  `data/gold/labels.jsonl` `{"pair_id","label":"match|check|no_match","note","labeled_at"}`. The UI never shows any model output.
- Training target = teacher JSON on train pairs (no human labels in train).

## `ml/results/eval.json`
```json
{"test_size":220,"generated_at":"ISO","gold":"human (blind)",
 "models":[{"name":"Qwen3.5-397B-A17B (teacher)","role":"teacher","acc":0,"acc_ci":[0,0],"macro_f1":0,"risky_caught":"x/y","false_alarms":"x/y",
            "json_valid":1.0,"p50_latency_ms":0,"cost_per_1k_usd":0}, {"role":"base"}, {"role":"base_guided"}, {"role":"lora"}, {"role":"heuristic"},
           {"role":"backboard:<model>"} ],
 "paired":[{"a":"lora","b":"base","gain":0,"ci":[0,0],"only_a":0,"only_b":0,"p":0}],
 "confusion":{"lora":{"labels":["match","check","no_match"],"matrix":[[0,0,0],[0,0,0],[0,0,0]]},"base":{}},
 "training":{"base_model":"Qwen/Qwen3.5-4B","rank":32,"steps":0,"epochs":0,"lr":0,"loss_curve":[[0,0]],"test_nll":[[0,0]]},
 "examples":[{"pair_id","listing_title","recall_title","gold","base","lora"}]}
```
"risky" = gold ∈ {match, check}; risky_caught = model says match|check on those. false_alarms = model says match|check when gold = no_match.
Stats: 10,000-sample bootstrap CIs, exact McNemar on discordant pairs (copy the TrailTruth protocol).

## `ml/results/scan_summary.json` — the headline
```json
{"recalls_scanned":151,"searches_spent":0,"listings_seen":0,"flagged_match":0,"flagged_check":0,
 "human_verified_match":0,"childrens_flagged":0,"by_recall":[{"recall_number","title","listings","match","check","examples":["listing_id"]}],
 "generated_at":"ISO"}
```
The post only quotes numbers that a human verified, and says so.

## Backend API (FastAPI, http://localhost:8000)
- `GET /api/health`
- `GET /api/recalls?since=&childrens=` → `RecallRecord & {spec: RecallSpec}`[]
- `GET /api/scan` → scan_summary.json; `GET /api/scan/{recall_number}` → listings + verdicts
- `POST /api/check` body `{"shop_id","items":[{"name","brand?","model?","notes?"}]}` → starts `InventoryCheckWorkflow`, returns `{workflow_id}`
- `GET /api/cards/{workflow_id}` → `{status, card?: RecallCard, steps:[{name,status,attempt,started_at,ended_at,error?,note?}]}`
- `GET /api/runs` → recent workflow runs
- `POST /api/shops/{shop_id}/corrections` body `{"listing_or_item","recall_number","correct_verdict","note"}` → Backboard memory; returns memory id
- `GET /api/shops/{shop_id}/memories`
- `GET /api/eval` → eval.json

### `RecallCard` — the one thing the shop prints
```json
{"id":"card_2026-10-15_demo-shop","week_of":"2026-10-15","shop_id":"demo-shop","shop_name":"Little Loop Kids Consignment",
 "new_recalls":6,"items_checked":120,"do_not_sell":[{"item":"...","recall_number":"...","recall_title":"...","why":"...","remedy":"..."}],
 "check_label":[{"item":"...","recall_number":"...","look_for":"model no. on bottom sticker: TL1302Z"}],
 "applied_memories":[{"memory_id","text"}],"workflow_id":"...","model":"qwen3.5-4b-recalldesk-lora","generated_at":"ISO"}
```

## Temporal
- `WeeklyRecallSweep` — Temporal Schedule, Thursdays 14:00 America/New_York. Activities: `fetch_new_recalls` → `extract_spec` (per recall) →
  per watched shop: `load_shop_memories` (Backboard) → `check_items` (retrieve top-k recalls per item with BM25 over specs, classify each pair) →
  `scan_ebay_store` (SerpApi, cached) → `compose_card` → `publish_card`.
- `InventoryCheckWorkflow` — same minus fetch/extract, on demand from `/api/check`.
- Per-activity retry policies; model calls heartbeat; invalid JSON retried, then heuristic fallback (labelled). CPSC 5xx → backoff.
  SerpApi quota/429 → NOT retried; use cached snapshot and label the step `source=snapshot (...)`.
- Dev runner `python -m agent.dev` starts a local Temporal dev server via the SDK (`WorkflowEnvironment.start_local`) + worker + API.
- `python -m agent.demo_crash` hard-kills the worker mid-run, starts a fresh one, proves no activity ran twice (event history).

## Model providers (env `RECALLDESK_MODEL_PROVIDER`), one function: `ml.infer.classify(spec, listing) -> MatchVerdict`
- `tinker` — Tinker SamplingClient on the saved LoRA (`RECALLDESK_TINKER_MODEL_PATH`)
- `openai` — any OpenAI-compatible server (`RECALLDESK_BASE_URL`, `RECALLDESK_MODEL`), incl. Tinker's OAI-compatible endpoint
- `heuristic` — deterministic identifier/keyword rules, zero keys (clearly labelled in UI)

## Additions agreed with the UI (2026-10-17)
1. `RecallSpec` gains optional `look_for` (where the identifier is physically printed) and `spec_source` (`teacher|heuristic|hand-checked`).
2. `GET /api/scan/{n}` → `{recall_number, listings: [Listing & {verdict: MatchVerdict, human_verified?: bool}]}`.
3. `RecallCard.check_label[]` rows also carry `recall_title`.
4. `GET /api/cards/latest?shop_id=` → latest completed card for a shop.
5. `/api/runs` items: `{workflow_id, workflow_type, shop_id?, status, started_at, ended_at, steps[], retries?, resumed_after_crash?, workers?, history_events?, card_id?}`.
6. Memories: `[{memory_id, text, recall_number?, correct_verdict?, created_at}]`; corrections POST returns `{memory_id}`.
7. Any payload that is not real yet carries top-level `"placeholder": true` (drives the UI's "Demo data" badge). `scan_summary.by_recall[]` may carry `is_childrens`.
8. Step `note` carries `source=snapshot (...)` for cached fallbacks; `error` containing "crash"/"resumed" marks resumed steps.
9. API CORS: `http://localhost:3000` + deployed web origin.

## Fixtures
Until real results exist, code against `shared/fixtures/*.json` (built from REAL CPSC data + heuristic verdicts).
The UI must render from `web/public/fixtures/` when the API is down (static demo deploy).
