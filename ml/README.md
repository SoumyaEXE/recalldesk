# RecallDesk ML + data pipeline

A large open-weight **teacher** (`Qwen/Qwen3.5-397B-A17B` on Tinker) does two jobs. It turns each CPSC recall
into a `RecallSpec`, and it labels (recall, eBay listing) pairs as `match | check | no_match`. Then a
**student** (`Qwen/Qwen3.5-4B`, LoRA rank 32 on Tinker) is trained on those labels. Every classifier is
scored against **blind human gold labels** on held-out recalls. The definitions are in `ml/LABELING.md`.

| role | Tinker id | notes |
|---|---|---|
| teacher | `Qwen/Qwen3.5-397B-A17B` | No deprecation note in `models.json` (checked 2026-10-17). It gets the long rulebook plus the CPSC text. |
| student | `Qwen/Qwen3.5-4B` | LoRA rank 32. Same tokenizer and template (`qwen3_5_disable_thinking`). We avoid models "Retiring October 23" (Nemotron-3-Nano, Qwen3.6-27B, DeepSeek-V3.1). |

Shapes live in `shared/schema.py`. Prompts and definitions are in `ml/prompts.py`, which matches `ml/LABELING.md`.

## Setup (once)
```bash
python -m uv venv --python 3.12 ml/.venv
python -m uv pip install --python ml/.venv/Scripts/python.exe -r ml/requirements.txt
# keys go in the repo-root .env (gitignored): TINKER_API_KEY / SERPAPI_API_KEY / BACKBOARD_API_KEY
PY=ml/.venv/Scripts/python.exe
```
Every script loads `.env` on its own. If a step needs a key that is missing, it exits with a clear message.
Nothing needs a key at import time.

## Pipeline, in order

| # | command | key | output | est. cost |
|---|---|---|---|---|
| 1 | `$PY -m ml.fetch_recalls` | none | `data/recalls/{raw_A,raw_B}.json`, `recalls.jsonl`, `stats.json` | free |
| 1b | `$PY -m ml.regex_ids` | none | self-checks of the identifier regexes on real CPSC text | free |
| 2 | `$PY -m ml.spec_extract --provider heuristic` | none | `data/specs/specs.heuristic.jsonl`, the zero-key fallback | free |
| 2t | `$PY -m ml.spec_extract --provider tinker --corpus AB` | Tinker | `data/specs/specs.jsonl` (preferred automatically once it exists) | ~$0.6 for A, ~$2.4 for AB |
| 3 | `$PY -m ml.serp_scan --dry-run --corpus A` | none | the planned queries and a count of searches to spend | free |
| 3s | `$PY -m ml.serp_scan --corpus A --max-searches 150` | SerpApi | `data/serp/*.json` (raw, gitignored), `data/listings/{listings,search_index}.jsonl` | 150 searches |
| 4 | `$PY -m ml.make_pairs` | none | `data/pairs/pairs.jsonl`, `data/splits/{train,test}.jsonl`, `split_stats.json` | free |
| 5 | `$PY -m ml.label_ui` | none | Opens http://localhost:8765 so a human can label the ~220 test pairs into `data/gold/labels.jsonl` | ~40-60 min of human time |
| 6 | `$PY -m ml.teacher_label` | Tinker | `data/labeled/teacher.jsonl` (every pair) | ~$0.002 per pair (about $4.5 for 2.2k pairs) |
| 7 | `$PY -m ml.eval --roles heuristic,teacher,base,base_guided` | Tinker | baselines in `ml/results/eval.json` | ~$0.1 |
| 8 | `$PY -m ml.train_tinker` (`--dry-run` first) | Tinker | `ml/results/model_path.txt`, `training.json` | ~$1-2 |
| 9 | `$PY -m ml.eval --roles lora` | Tinker | final `eval.json`, `predictions.jsonl`, `preds/*.jsonl` | ~$0.05 |
| 10 | `$PY -m ml.backboard_baselines --list-models --provider openrouter`, then `--models "openrouter:<m1>,openrouter:<m2>"`, then `$PY -m ml.eval --rebuild-only` | Backboard | `preds/backboard_*.jsonl`, plus their rows in `eval.json` | Backboard credits |
| 11 | `$PY -m ml.scan_summary --provider tinker` (or `heuristic`) | Tinker (optional) | `ml/results/scan_summary.json` (the headline) | ~$0.3 per 1k listings |
| opt | `$PY -m ml.download_adapter --peft` | Tinker | local PEFT adapter for vLLM, SGLang or llama.cpp | free |

Steps 5 and 6 are independent of each other. Labeling can start as soon as step 4 has run. If you want a score
before the humans finish, `ml.eval --gold teacher` gives a provisional one, clearly marked in `eval.json`. Spend
estimates are tracked in `ml/results/spend.json`, priced from the Tinker list prices in `models.json` on 2026-10-17.
Token sizes were measured with the Qwen3.5 tokenizer:

| prompt | tokens |
|---|---|
| student | ~340 |
| base_guided | ~760 |
| teacher (with CPSC text) | ~900 |
| spec | ~830 |

## Data facts (fetched 2026-10-17)
- **Corpus A**: all recalls since 2026-07-18. That is **151** recalls: 48 for children, and 90 with at least one
  regex identifier (84 with a model, item, style, SKU or part number, 12 with a lot or date code, 4 with a UPC).
- **Corpus B**: children's-product recalls since 2023-01-01. That is **488** of 1,534 recalls; 241 have an identifier.
  A and B overlap by 48 recalls, giving 591 unique recalls.
- The children's detector (`ml/fetch_recalls.is_childrens`) uses keywords on the title head (before "Due to"),
  the product names and the first two sentences. It also counts a "Violates ... standard for infant/toy/crib..."
  clause. Negations are stripped first: child-resistant packaging, "Children's Gasoline Burn Prevention Act",
  "risk to children", and Reese's-law button batteries.
- **Encoding:** the API returns valid UTF-8 bytes (`Scotch\xe2\x84\xa2` = ™). We decode `response.content` as UTF-8
  ourselves, with a cp1252 fallback that has never been needed. We found 0 mojibake. Mangled ™ only shows up when
  something else decodes the bytes with the wrong codec, such as the Windows console.
- **Identifier caveat:** 6 recalls in A end their description with "the following model numbers ... are included:".
  The table itself exists only on the cpsc.gov page, and cpsc.gov returns 403 to scripts. Those recalls have no
  identifiers for anyone, including the teacher.
- One CPSC data error: recall "F&F Fine Wines ... Prosecco" has a crib-mattress description.

## SerpApi eBay
- Params checked against https://serpapi.com/ebay-search-api: `engine=ebay`, `ebay_domain=ebay.com`, `_nkw`,
  and `_ipg` (25, 50, 100 or 200; we use 50). `_pgn` sets the page.
- The cache key is `sha1(sorted params without api_key)`, stored at `data/serp/<sha1>.json`. A cached search is
  never re-spent. `--max-searches` caps how many *new* searches are spent. A quota error or 429 stops the run
  without retrying, and the snapshot is kept.
- **Planned searches** (one per recall, using `spec.search_queries[0]` and deduped): **A = 150**,
  **B = 474**, **A+B = 577**. B adds 427 beyond A.
- **Filtering to one seller's store** ("scan my eBay store"): the eBay engine has **no `_ssn` param**. Use
  **`_sasl=<seller username>`** with **`_saslop=1`**, which shows only that seller (`2` excludes them). Several
  sellers can be comma-separated. In code: `ml.serp_scan.search_ebay(query, seller="username")`. It costs one
  search and is cached like any other. A query is still needed: use the shop's category words, or `category_id`.
- Search results do **not** include item specifics, only `extensions`, condition, price and seller.
  `Listing.item_specifics` holds `extensions`, `format` and `location`. Full specifics would cost one
  `ebay_product` search per item, so we don't fetch them.
- Privacy: seller usernames only ever exist in the raw `data/serp/` cache. Everything else carries
  `seller_hash = "s_" + sha1(lower(username))[:6]`.

## For agent/ (import surface)
```python
from shared.schema import RecallRecord, RecallSpec, Listing, MatchVerdict, RecallCard, parse_verdict
from ml.infer import classify, classify_batch, retrieve, active_provider
from ml.serp_scan import search_ebay, QuotaExceeded, NotCached
from ml.heuristic import spec_from_record          # spec for a brand-new recall when the teacher is unavailable
v, meta = classify(spec, {"listing_id": "inv:shop:1", "source": "inventory", "title": "Woodure tower WD1720"})
hits = retrieve("Woodure kitchen tower WD1720", specs_dict, k=5)  # BM25; exact identifier hits come first
```
- `RECALLDESK_MODEL_PROVIDER` can be `tinker`, `openai` or `heuristic`. If it is unset, the default is `tinker`
  when a key and a model path exist, and `heuristic` otherwise. `meta` contains `latency_ms`, `tokens_in`,
  `tokens_out`, `model` and `provider`. After two invalid JSON replies, `provider` is
  `"heuristic (fallback from X)"`.
- **Tinker OAI endpoint:** set `RECALLDESK_MODEL_PROVIDER=openai` and
  `RECALLDESK_BASE_URL=https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1`. `RECALLDESK_MODEL` is
  the `tinker://...` path and defaults to `model_path.txt`; the key is `TINKER_API_KEY`. We call `/completions` with
  the exact Qwen3.5 non-thinking template used in training, because `/chat/completions` applies the HF default
  template. Set `RECALLDESK_OAI_MODE=chat` to override.
- Overriding `RECALLDESK_DATA` or `RECALLDESK_RESULTS` points every script at another directory. This is used for
  smoke tests, so fake data never lands in `data/`.

## Eval protocol
- The split is **by recall**: test recalls never appear in train. It is stratified by `is_childrens` with seed 0,
  and at least half the test recalls are children's. Re-issued recalls that share a query or product name stay
  in the same split. Train pairs that reuse a test listing are dropped.
- Gold is human and blind. The UI shows no model output; the only highlighting is the deterministic regex ids.
- Each pair gets a single attempt at temperature 0, and invalid JSON counts as wrong. We report:
  - acc, with a 10,000-sample bootstrap 95% CI
  - macro-F1
  - risky_caught (gold in {match, check} → predicted match or check)
  - false_alarms
  - json_valid
  - p50 and p95 latency
  - cost per 1k pairs
  - confusion matrices
- Paired comparisons use an **exact two-sided McNemar** test on discordant pairs, plus a paired bootstrap CI of the
  accuracy gain. The pairs compared are lora vs base, base_guided, teacher and heuristic, and each Backboard model.
- The training target is the teacher's JSON on train pairs. No human labels are used in training. Held-out NLL
  is computed against the teacher's targets on test pairs at step 0 and after each epoch. Weights are taken from
  the final epoch, not picked using the test set.
