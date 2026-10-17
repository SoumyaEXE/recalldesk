# docs/charts: matplotlib charts for the post

```bash
python -m uv venv --python 3.12 docs/charts/.venv
python -m uv pip install --python docs/charts/.venv/Scripts/python.exe matplotlib numpy
docs/charts/.venv/Scripts/python.exe docs/charts/make_charts.py            # all charts
docs/charts/.venv/Scripts/python.exe docs/charts/make_charts.py ids-buried # one chart
```

The script only reads `data/` and `ml/results/`, plus the raw SerpApi cache `data/serp/*.json`, which it reads without spending a search. It then overwrites `docs/charts/*.png` and `docs/charts/chart_data.json`, where every number drawn is stored. Each image is 1600 px wide (8 in at 200 dpi, so 2x for an 800 px column). The fonts in `fonts/` are Barlow Condensed (titles and figures), Public Sans (text) and IBM Plex Mono (kicker and source line). They come from Google Fonts and Fontsource, and glyphs they lack fall back to DejaVu. The colours are the dashboard tokens: paper `#faf7f0`, ledger blue `#2b5fab` for the series we emphasise, neutral `#b9b2a2` for the others, DO NOT SELL red `#c8102e` and CHECK LABEL amber `#e8a200`. Red and amber appear only where a chart shows match or check verdicts.

**Placeholder rule:** charts in group (g) read `ml/results/*`. If the file is missing or has `"placeholder": true`, the chart uses the illustrative values from `docs/visuals/build_data.py` and gets a red **PLACEHOLDER · NOT REAL DATA** watermark. The answer key is `eval.json` `gold` = "teacher + rule 7 by code (not human)" (`data/labeled/targets.jsonl`, built by `ml/enforce_rules.py`); that is final for this project, so those charts are real and their source line reads "answer key: teacher + rule 7 (code), not human". Only an `eval.json` graded against raw teacher labels (no rule 7) gets an amber **PROVISIONAL** watermark. The script prints `[PLACEHOLDER]` or `[PROVISIONAL]` next to each such file. Don't publish a watermarked chart.

## Methods

| chart | method |
|---|---|
| `recalls-per-thursday` | Corpus A (`"A" in corpus`, recall_date ≥ 2026-07-18), grouped by `recall_date`. Children's = `is_childrens` from `ml/fetch_recalls`. |
| `ids-buried` | See below. |
| `where-sold` | Case-insensitive keyword match on the CPSC "Sold at" text (`retailers[]`). The patterns are `RETAILERS` in the script. A recall counts once per retailer. "Sold online" comes from `data/recalls/stats.json` (`A.sold_online` = 119, `B.sold_online` = 346), so the post quotes the same number `ml/` uses. The Amazon, Walmart and Target counts match `stats.json` exactly. |
| `listings-per-recall` | One row per cached search in `data/listings/search_index.jsonl` (rows with `error` are skipped). Listings come from that search's raw `organic_results`, deduped by eBay `product_id` (or link) within each recall. **Exact identifier in title (deterministic, not model):** `ml.regex_ids.find_ids_in_text(spec.model_numbers + spec.upcs, listing.title)`. The match ignores case and separators (`- . / _` and spaces) and is token-bounded, and ids of 6 or more characters may also prefix-match a longer token. This finds leads, not verdicts: it also counts accessories that name the model, such as "screen film for INMO AIR3". |
| `condition-mix` | eBay `condition` on every unique listing (deduped across all searches), normalized to New / Open box / Refurbished / Pre-Owned / For parts / Not stated. Rows: all listings, listings returned for children's recalls, and exact-identifier hits. |
| `hazard-types` | Keyword buckets (`HAZARDS` in the script) on `hazards[]` plus the title's "Due to …" clause. One recall can fall in several buckets. Generic "risk of serious injury" wording is deliberately not a bucket, because almost every recall uses it. |
| group (g) | `results-bars`, `cost-per-1k` and `latency` use `eval.json` `models[]`. `risky-caught-units` and `confusion-pair` use `eval.json` `confusion` (rows = answer key match/check/no_match, cols = predicted). `loss-curve` uses `training.json`, falling back to `eval.json` `training`. `flagged-by-recall` uses `scan_summary.json` `by_recall`. `label-distribution` uses `eval.json` `gold_dist` (the teacher + rule 7 answer key on the test pairs; `data/gold/labels.jsonl` only if eval.json was graded against human labels). |

### "Buried" model numbers: 73 of 151, and why not 69

**Definition (the one the post uses):** the recall's description contains at least one model, item, style, SKU, part, product-id or reference number, and **none** of those numbers appears in the recall's title or product names. Exclusions are dropped first ("model X is not included"). Lot and date codes and UPCs don't count as model numbers here.

**Method:** `ml.regex_ids.extract_ids_typed(description, upcs)`, keeping `kind ∈ {model, item, style, sku, part, product_id, ref}` and `excluded == False`. Then `norm_id(id)` is checked as a substring of `norm_id(title + " " + product_names)`. This is the same code as `docs/visuals/build_data.py` (`corpus.buried`), so `corpus.png` and `ids-buried.png` agree.

| corpus A, 151 recalls | count |
|---|---|
| model-type number only in the description (**buried**) | **73** (48.3%) |
| model-type number also in the title or product name | 11 |
| no model-type number in the notice | 67 (6 of these have only a lot/date code or UPC; 90 recalls have any regex id) |
| children's subset (48 recalls): buried / in title / none | 24 / 3 / 21 |

- **The writer's "73 of 151" matches this count exactly.**
- **The contract's "69 of 151" is stale.** It came from an earlier version of the regex that had no typed kinds or exclusion handling. Don't use it.
- **Cross-check with the teacher's specs:** using `specs.jsonl` `model_numbers` instead of the regex gives 88 buried, 14 in title and 49 with no model number. The teacher finds model numbers in some recalls the regex misses, for example ones written in tables or after unusual triggers. Every one of them is grounded in the notice by `ml.spec_extract.ground_ids`. This count is higher, but it depends on a model, so the post quotes the deterministic **73** and can say "at least 73".
