---
title: "We Searched eBay for 237 Recalled Products. Only 45 of 12,562 Listings Named the Model."
published: true
description: Recalled baby gear keeps getting resold because the model number lives in the fine print. RecallDesk is a $15/month weekly recall check for kids' consignment shops and eBay flippers, built on CPSC data, SerpApi, a fine-tuned open 4B model, Temporal and Backboard.
tags: devchallenge, hf26challenge, ai, opensource
cover_image: https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/images/cover.png
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12)*

Built by [@dronzer2code](https://dev.to/dronzer2code) and [@soumyadeepdey](https://dev.to/soumyadeepdey).

Picture a Thursday afternoon at a kids' consignment shop (a composite, not a real store). A parent drops a bag at the intake desk: a toy fire truck, a wooden learning tower, a sleep machine, some toddler pyjamas. The staffer has about two minutes per item. That morning the U.S. Consumer Product Safety Commission posted its weekly batch of a dozen or so recalls. Nobody at the desk has read them.

Here's the part of one notice that matters, from September 17, for the Melissa & Doug Lights and Sound Fire Truck (about 84,000 sold at Target):

> Affected units will have one arrow pointing to the number 25 and the second arrow pointing to the number 4 or 5 or they will have one arrow pointing to the number 26 and the second arrow pointing to the number 3.

The arrows are two date dials under the battery box. The brand and the price tag can't answer it. You have to turn the toy over.

For the shop this is a legal question. CPSC's [Resale Round-up](https://www.cpsc.gov/Newsroom/News-Releases/2009/CPSC-Launches-Resale-Round-up-Campaign-to-Keep-Dangerous-Recalled-Products-Out-of-Resale-Stores-and-Off-the-Internet) campaign told thrift stores and online resellers directly that re-selling recalled products violates federal law. On October 6, [Consumer Reports, via News4Jax](https://www.news4jax.com/money/2026/10/06/consumer-reports-warns-parents-about-unsafe-baby-gear-being-sold-on-craigslist-ebay-facebook-marketplace-other-sites/), warned that banned and recalled baby gear is still listed on Craigslist, eBay and Facebook Marketplace. eBay said its product-safety systems (AI models, keyword rules and manual review) stopped 21 million potentially unsafe listings worldwide in 2025. And a [2026 Buchalter analysis](https://www.buchalter.com/blogs/cpsc-escalates-enforcement-in-2026-expanded-market-oversight-civil-penalties-and-criminal-exposure/) notes that CPSC has now sent its 100,000th takedown notice for recalled or banned products sold online.

We built **RecallDesk** for that desk. Every Thursday it reads the new recalls, checks a shop's stock and eBay store against them, and prints one page: what to pull, and what to flip over.

![RecallDesk printable card for Little Loop Kids Consignment, week of Thursday October 15, 2026, made by the fine-tuned 4B: 6 new CPSC recalls, 60 items checked. A red DO NOT SELL band lists 8 items with CPSC number, reason and remedy: Papablic bedside sleeper (PAPA03001AI, 27027), Primark 101 Dalmatians coin purse (2595301), ONTHEWEI bath seat (MY002), Skip Hop Elmo teether (9R263210), Taleco Gear swing (swing-1), Mangohood kitchen tower (LT003), Love To Dream sleep machine (LTD-SM23) and Romorgniz 6-drawer dresser. An amber CHECK LABEL band lists 6 items with where to look, e.g. Woodure learning tower: the model number is engraved on the underside of the bottom step. At the bottom, two shop corrections applied from Backboard memory: the HARPPA tower and the Melissa & Doug fire truck](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/blog-shots/home-card-1440.png)

## Where the model number hides

Before any model code, we pulled every recall CPSC posted from July 18 to October 15: 151, all on Thursdays, 48 for children's products. Adding children's recalls back to 2023 (shops sell old baby gear too) made 591.

![Stacked bar chart of CPSC recalls per Thursday from Jul 23 to Oct 15, 2026: 7, 15, 17, 18, 7, 11, 13, 12, 14, 11, 12, 8 and 6 recalls, 151 in total, about 12 a week. Children's products are in blue (48 of 151, 32%), from 0 on Aug 20 to 7 on Jul 30 and Aug 6. Every recall in the period was posted on a Thursday](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/charts/recalls-per-thursday.png)

Then, with plain code and no model, we asked where the identifying number appears. In **73 of the 151** notices, the model, item, style or SKU number is only in the description, never in the headline or product name (24 of 48 for children's). "Woodure Toddler Kitchen Step Stools Recalled" gives you the brand. Whether *your* stool is affected is further down: "The model number is engraved on the underside of the bottom step."

![100% stacked bar chart of the 151 CPSC recalls since Jul 18, 2026: 73 (48%) have a model, item, style, SKU or part number only in the description, 11 also show it in the title or product name, and 67 have no model-type number. Children's recalls (48): 24 description only, 3 in the title, 21 none. Using the teacher model's extracted model numbers instead of regexes gives 88 description-only](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/charts/ids-buried.png)

On the resale side, SerpApi's eBay engine searched for 237 recalls (the 151 recent ones plus 86 older children's ones; 235 paid searches, since two recalls shared a cached query): 14,068 results, **12,562 unique listings**. We counted titles containing a recalled identifier, ignoring case and dashes. There were **45**, across 13 recalls. For children's recalls, **2 of 6,901**, both for one brand of pool dive sticks.

![Two panels. Left: a histogram of unique eBay listings per recall search across 237 searches (151 recalls since Jul 18 plus 86 older children's recalls): 210 returned a full page of 50 or more, 7 returned 25-49, 7 returned 10-24 and 13 returned 1-9. Right: a funnel from 237 recalls searched, to 150 with a model number or UPC in their spec, to 13 with at least one listing whose title contains a recalled identifier exactly (45 listings, deterministic string match)](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/charts/listings-per-recall.png)

Second-hand sellers are the least likely to type one: **17.1%** of all listings were pre-owned (**20.2%** for children's recalls), but only 9% of the 45 exact hits were.

![100% stacked bars of eBay listing condition. All 12,562 unique listings: 78% new, about 3% open box, 17% pre-owned. Listings returned for children's recalls (6,901): 79% new, 20% pre-owned. The 45 listings whose title names a recalled identifier: 78% new, 13% open box, 9% pre-owned](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/charts/condition-mix.png)

That count shaped the product. A keyword filter can flag the 45 but can't clear the other 12,517, because a title without a model number proves nothing. For most same-brand items the useful answer is "go look at the label", plus where the label is.

## What I Built

RecallDesk is a weekly recall desk for resale businesses. A shop loads its stock once (CSV or paste) and, optionally, its eBay seller name. Every Thursday at 2:00 PM Eastern, after CPSC posts, it turns each new recall into a structured spec (brand, model numbers, date codes, sold window), compares every item and live listing against the specs that could apply, applies the shop's past corrections, and prints one card: **DO NOT SELL** for `match`, **CHECK LABEL** for `check` with the place to look, and nothing for `no_match`.

A trimmed excerpt of a real card for the demo shop, from a run with the fine-tuned model on Tinker:

```text
=== RECALL CARD card_2026-10-15_little-loop  Little Loop Kids Consignment  (week of 2026-10-15) ===
  6 new recalls this week | 60 items checked | model: qwen3.5-4b-recalldesk-lora
  DO NOT SELL (8)
    x Papablic Convertible Bedside Sleeper with Play Yard (model PAPA03001AI)  -> CPSC 27027
        why: Listing matches recalled brand, product type, and explicitly states the recalled model number.
        remedy: Stop use, destroy product, email photos for refund
    x Love To Dream Portable Sleep Machine with Night Light (model LTD-SM23)  -> CPSC 26798
  CHECK LABEL (7)
    ? Woodure Wooden Toddler Learning Tower  -> CPSC 26658
        look for: model no. WD1764, WD1357, WD1720; sold 2024-07 to 2026-06. The model number is
                  engraved on the underside of the bottom step.
    ? Sweet Cubby Kids Loungewear Set (shirt + shorts)  -> CPSC 26752
        look for: lot/date code Batch No.: 272779; sold 2025-06 to 2026-05. "Batch No.: 272779" and
                  the size are printed on the sewn-in neck label and on the seam label.
  SHOP MEMORIES APPLIED (1)
    * beeeda90-bb74-4681-b1fa-bfdacd9ef8e6: Shop correction: 'HARPPA Nordi Foldable Toddler Tower' is
      NOT the recalled product for CPSC recall 26651. Ours is the 2022 one - consignor's receipt s...
  model usage: 179 classify calls for 60 items | ... | est. $0.0348 at Tinker list price
  workflow: check-little-loop-2026-10-17-e610   memory: backboard
```

One line on that card is wrong, and it's wrong in the cautious direction. The Love To Dream recall covers model LTD-SM23 *with* date code 7W15TN, so our own rule 3 says the item should be CHECK LABEL, not DO NOT SELL. The shop would pull a sleep machine that might be fine.

The dashboard is Next.js with [BoardUI](https://boardui.com) components. Most owners only need the printable card. The rest is for setup and for answering "why was this flagged?"

![RecallDesk overview: a KPI row (new recalls this Thursday, items checked, do-not-sell and check-label counts), this week's card as a sortable table, a countdown to the next scheduled sweep, the recalls posted this Thursday, an eBay summary and an activity feed](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/blog-shots/overview-1440.png)

Any inventory row opens beside the recall it was compared with. **"Not a match? Correct this"** is how a shop teaches the system about its own stock.

![Inventory page with an item drawer open: the shop's item on one side, the matched CPSC recall and its extracted spec on the other, a verdict pill, and the "Not a match? Correct this" button](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/blog-shots/inventory-drawer-1440.png)

The recalls page puts CPSC's text, identifiers highlighted, next to the extracted spec:

![Recall page with CPSC 26658, Woodure Toddler Kitchen Step Stools (about 91,000 units, sold on Amazon), expanded: the original notice with models WD1764, WD1357 and WD1720 highlighted, including "The model number is engraved on the underside of the bottom step", beside the extracted spec with brand, model numbers, sold window Jul 2024 to Jun 2026, key features, hazard, remedy and eBay queries](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/blog-shots/recalls-expanded-1440.png)

The eBay monitor is for flippers who sell online:

![eBay monitor: searches spent, listings seen and flagged counts, and per-recall rows that expand into listing cards with title, condition, price and verdict; sellers appear only as a hashed id](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/blog-shots/ebay-1440.png)

**Who would pay?** Kids' consignment shops, which take in second-hand children's goods from strangers daily. Seasonal consignment events, with thousands of items and volunteer staff in one weekend. eBay and Poshmark flippers buying returns pallets blind. We priced it at **$15 a month per shop** and **$49 per consignment event**. A full re-check of the 60-item demo shop took 179 model calls and cost $0.035.

![Pricing page: Shop plan at $15 per month per shop (weekly card every Thursday, unlimited inventory checks, eBay store re-check, shop memory) and Consignment event at $49 per event (check every consignor's intake list, one card per drop-off batch, printable pull list, recalls back to 2023)](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/blog-shots/billing-1440.png)

It isn't legal advice or a substitute for [cpsc.gov/Recalls](https://www.cpsc.gov/Recalls). It reads text and can't see a label in a photo, which is why CHECK LABEL exists. U.S. CPSC recalls only.

## Demo

One-click deploy of the full stack (agent runtime plus dashboard) from the repo's Render Blueprint:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/SoumyaEXE/recalldesk)

Or run it locally. Every key is optional, and anything missing falls back to a labelled substitute.

```bash
git clone https://github.com/SoumyaEXE/recalldesk && cd recalldesk
cp .env.example .env            # TINKER_API_KEY / SERPAPI_API_KEY / BACKBOARD_API_KEY, all optional

python -m uv venv --python 3.12 agent/.venv
python -m uv pip install --python agent/.venv/Scripts/python.exe -r agent/requirements-tinker.txt
agent/.venv/Scripts/python -m agent.dev --schedule        # Temporal :7233 (UI :8233), worker, API :8000
agent/.venv/Scripts/python -m agent.run_check little-loop # run one shop's check and print its card
agent/.venv/Scripts/python -m agent.demo_crash            # kill the worker mid-check, watch it recover

cd web && npm install && npm run dev                      # dashboard on :3000
```

On macOS or Linux the interpreter is `agent/.venv/bin/python`.

## Code

{% github SoumyaEXE/recalldesk %}

There are four directories. `ml/` holds data collection, specs, eBay search, labelling, training and evaluation. `agent/` holds the Temporal workflows, the API and shop memory. `web/` is the dashboard. `shared/schema.py` is the single contract the other three code against. Every figure here traces to `ml/results/*.json`, `data/*/…stats.json`, `docs/charts/chart_data.json` or a transcript under `agent/demo_logs/`. License: MIT.

## How I Built It

![Architecture diagram. Offline, once: CPSC recalls go to the Qwen3.5-397B teacher on Tinker, which writes a spec per recall; SerpApi searches eBay for each; code builds (recall, listing) pairs split by recall; the teacher labels every pair; code enforces rule 7 on the training targets; a rank-32 LoRA on Qwen3.5-4B is trained on Tinker and scored on 20 held-out recalls. Weekly: a Temporal schedule on Thursdays at 14:00 Eastern runs fetch_new_recalls, extract_spec, load_shop_memories (Backboard), check_item per item with the LoRA, scan_ebay_store (SerpApi), compose_card and publish_card, and shop corrections flow back into Backboard](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/images/architecture.png)

### Rules first, model second

We wrote the decision rules before choosing a model. Our three verdicts are defined in [`ml/LABELING.md`](https://github.com/SoumyaEXE/recalldesk/blob/main/ml/LABELING.md):

- **match:** the item is the recalled product. Brand and line agree, and either a recalled identifier is visible or the recall covers every unit of that exact product.
- **check:** same brand and line, but whatever decides it (model number, date code, sold window, variant) isn't visible.
- **no_match:** a different product, an excluded model, or only an accessory, part or "compatible with" item.

Seven ordered rules apply them. Rule 7 did the most work: *an unbranded listing with no recalled identifier is a generic look-alike, so no_match*, unless it names something only the recalled product has, like a licensed character. The model outputs one small JSON object, and plain code maps it to the card.

A large open model, **Qwen3.5-397B-A17B**, wrote specs for all 591 recalls (100 seconds, $2.21), and code drops any identifier not actually in the notice. It also labelled 3,300 (recall, listing) pairs, and kept calling unbranded look-alikes "check": 1,134 checks on the first pass, 872 after we added rule 7 to the prompt. Still too many, so we stopped asking. A short function checks the rule and rewrites the *training target* when the teacher breaks it:

```python
def is_generic_lookalike(spec: dict, title: str) -> bool:
    words = set(norm(title).split())
    if brand_words(spec.get("brand", "")) & words:      # names the brand -> not generic
        return False
    if id_hit(spec, title):                              # shows a recalled identifier -> not generic
        return False
    return len(distinctive_words(spec) & words) < 2      # fewer than 2 distinctive product-name words
```

It fired on 391 pairs: 357 in training and 34 in the test split. Every change is logged in `data/labeled/targets.jsonl`.

### The 397B teaches once; a 4B works every Thursday

At **$2.20 per 1,000 checks**, the 397B is too expensive to run for every shop every week. So with Tinker we fine-tuned **Qwen3.5-4B** (LoRA rank 32) on its corrected labels: 3,007 pairs, 2 epochs fixed in advance, 376 steps at batch 16, learning rate 4.91e-4 decaying linearly, loss on the JSON only. Our code assembles batches and calls `forward_backward` and `optim_step`; Tinker's GPUs do the rest, and `save_weights_for_sampler` returns the `tinker://` path the weekly workflow samples. About 38 minutes; held-out loss 0.724 → 0.228. With a ~400-token prompt (the teacher's is ~1,060), the student costs **$0.19 per 1,000 checks**.

Tinker spend at list prices: specs $2.21, discarded first labelling run $6.80, second run $7.47, training $2.39, evaluation $0.23, **about $19.10** total. SerpApi: 235 of the free plan's 250 searches.

### Scoring it without fooling ourselves

We split by **recall**: 217 for training, 20 held out (12 children's), with no recall or listing shared. One try per pair at temperature 0; invalid JSON is wrong. The evaluation harness (bootstrap CIs, exact McNemar) and the Temporal crash-test pattern come from @soumyadeepdey's earlier open-source TrailTruth project ([repo](https://github.com/SoumyaEXE/trailtruth)).

**One caveat shapes everything below.** We built a blind labelling tool but didn't finish human labels in time, so the answer key for the 293 test pairs is **the teacher's verdict with rule 7 applied by code**, not a person's. The scores show how faithfully a 4B learned the teacher's rulebook on unseen recalls, not how often it's right about the world.

| On 293 held-out pairs | Accuracy (95% CI) | False alarms (of 255) | Risky pairs flagged (of 38) | $ / 1k checks |
| --- | --- | --- | --- | --- |
| Qwen3.5-4B, base | 0.512 (0.457–0.570) | 120 | 34 | $0.22 |
| Qwen3.5-4B, base + teacher's full rulebook | 0.625 (0.570–0.679) | 106 | 36 | $0.37 |
| Identifier/keyword rules, no model | 0.864 (0.823–0.901) | 22 | 22 | $0 |
| Teacher, Qwen3.5-397B-A17B | 0.884 (0.846–0.918) | 34 | 38 | $2.20 |
| **Qwen3.5-4B + RecallDesk LoRA** | **0.918 (0.884–0.949)** | **12** | **26** | **$0.19** |

<sub>The teacher's 38 of 38 is automatic, because every gold "check" is one of its own. Its 34 false alarms are exactly the pairs rule 7 overrode. The base 4B returned invalid JSON on 14 pairs, and every other model on none.</sub>

Fine-tuning moved the 4B from 0.512 to 0.918 (+40.6 points, 95% CI +33.8 to +47.1, exact McNemar p < 0.001). Against the teacher the gap (+3.4, p = 0.20) isn't significant: same reading, about a twelfth of the cost. For a shop the false-alarm column matters most. The base model sent 120 of 255 harmless listings to CHECK LABEL, which would bury the real ones. The LoRA sends 12.

![Bar chart of accuracy on 293 held-out pairs from 20 unseen recalls, scored against teacher labels with rule 7 enforced by code: LoRA 0.918 (95% CI 0.884-0.949), teacher 0.884, identifier rules 0.864, base + rulebook 0.625, base 0.512, with cost per 1,000 checks beside each bar](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/images/results.png)

The price: the LoRA flags **26 of the 38 risky pairs**; its base flagged 34 (on risky pairs alone the base is ahead, 11 to 3, p = 0.057, not significant). Nine of the twelve misses are one recall, a Sviyatp pool drain cover that, per CPSC, "has no labeling or product identification on the product itself". The listings are unbranded white drain covers, which rule 7 reads as no_match, and that's what the student said. Our coded rule kept them as "check" only because the titles share "dual suction outlet" with the product name printed on Sviyatp's packaging. Two more misses are unbranded baby toys; one is a 14-pack of finger lights against a recall of 28- and 30-packs. So it's a genuine trade: fewer false alarms in exchange for trusting rule 7 on products with no label at all. On the 180 children's pairs the LoRA scores 0.933, the base 0.428.

![Unit chart of the 38 held-out risky pairs: the base 4B flagged 34 and missed 4 (3 cleared, 1 invalid JSON); the LoRA flagged 26 and cleared 12, nine of them listings for the unlabeled Sviyatp pool drain cover](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/images/risky-caught.png)

A concrete false alarm: for TheKiddoSpace's recalled LED hover ball, eBay returned "Rechargeable Hover Soccer Ball LED Lights Air Power Indoor Outdoor Toy Kids 3+", no brand anywhere. The base said `check` because the listing "matches the brand". The LoRA said `no_match`: "Generic look-alike: no brand and no recalled identifier in the listing." Per-request latency on Tinker's hosted sampler is 2.3–2.8 s for every model, so the win is cost, not speed.

### Finding the listings (SerpApi)

Each call is `engine=ebay`, `ebay_domain=ebay.com`, `_ipg=50`, with the teacher's first query as `_nkw`. Responses are cached under a hash of their parameters, so nothing is paid for twice, and a 429 halts the run. A shop's own store uses `_sasl=<seller>&_saslop=1` (the engine has no `_ssn`). Seller names stay in the raw cache; published data uses a hash.

### Thursday, every Thursday (Temporal)

`recalldesk-weekly-sweep` is a Temporal Schedule for Thursdays, 14:00 America/New_York. It next fires October 22 and 29 at 18:00 UTC, then November 5 at 19:00 UTC once the clocks change. Every step is an activity with its own failure policy: CPSC fetches back off, then fall back to a committed snapshot; classification heartbeats with six calls in flight, so a stuck call gets retried; malformed JSON is retried, then answered by the rules with a note on the card; a SerpApi 429 is never retried, and the step records `source=snapshot (SerpApi quota/429, not retried)`.

Does a dead worker lose work? We started a check of the demo shop's 60 items (176 comparisons) and killed the worker process 12.4 seconds in, 19 items done. For three seconds nothing ran, while Temporal still showed the workflow running with six activities in flight. A fresh worker replayed the history and published the card at 33.2 seconds. The history: 60 item activities, each scheduled once; the 20 finished before the kill were kept, the 6 in flight got a second attempt, none completed twice. This rehearsal used the rules classifier plus 1.2 s of artificial latency per item, to make sure the kill hit mid-run.

Then we did it again with the real LoRA on Tinker (workflow `check-little-loop-2026-10-17-1a16-crashdemo`). We killed worker pid 12764 at 73.2 seconds with 18 of 60 items done and 6 calls in flight, and a fresh worker started at 76.5 seconds. The card was published at 170.9 seconds. Again there were 60 activities, each scheduled once: 18 kept, 6 retried, none completed twice, 344 history events. The chart below is this LoRA run; the Temporal UI screenshot after it is from the rehearsal.

![Timeline of the crash run on the real LoRA: worker 1 (pid 12764) hard-killed at t+73.2 s with 18 of 60 items done and 6 activities in flight; three seconds with no worker while Temporal still shows the workflow RUNNING; worker 2 (pid 17928) starts at t+76.5 s and replays the history; 18 finished activities kept, 6 orphaned ones retried, none completed twice; card published at t+170.9 s; 344 history events](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/images/crash-resume.png)

![Temporal Web UI timeline of workflow check-little-loop-2026-10-17-7a6f-crashdemo, completed, 392 events: one bar per check_item activity, the retried ones spanning the gap with no live worker, then scan_ebay_store, compose_card and publish_card](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/blog-shots/temporal-crash-timeline-chart.png)

The dashboard's runs page badges the same run as resumed:

![RecallDesk runs page with the crash-test run selected: completed, 7 activities, 392 history events, handled by worker 16408 and then worker 20396, with the check_items step marked as resumed after a worker crash on attempt 2](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/blog-shots/runs-crash-1440.png)

With injected faults on the LoRA worker (fake CPSC 503s, hung calls, broken JSON), ten items needed retries and three were answered by the labelled fallback, and the card noted it. A manual sweep for recalls since October 8 fetched 14 live from CPSC and fanned out to one child workflow per shop, producing two cards in 83 seconds.

### Remembering a shop's corrections (Backboard)

No model can know that this shop's fire truck reads 24/11 on its dials. The staffer holding it can. Their "Not a match? Correct this" note is stored as a memory in the shop's own Backboard assistant (explicit memory endpoints only). Next run, `load_shop_memories` retrieves it by meaning, not exact text. The memory is kept away from the model, which still answers `check`; code then changes the verdict to `no_match` and lists the correction on the card. In the recorded run (LoRA on Tinker, Backboard memory `063081d1-…`), CHECK LABEL went from 7 items to 6 and DO NOT SELL stayed at 8.

![Three panels. Run 1: Melissa & Doug Lights & Sounds Fire Truck Activity Board marked CHECK LABEL for CPSC 26780. Correction: "Date wheels read 24/11, not the recalled 25/4, 25/5 or 26/3", stored as Backboard memory 063081d1. Run 2: the model still answers check, code applies the memory and the card shows the item cleared; CHECK LABEL goes from 7 to 6](https://raw.githubusercontent.com/SoumyaEXE/recalldesk/main/docs/images/memory-loop.png)

An override needs a matching recall number and at least 60% word overlap with the remembered item, so a note about one tower can't clear another. The same run also applied an older HARPPA tower correction (memory `beeeda90-…`). One honest wrinkle: semantic search was flaky on long item names. The full "Melissa & Doug Lights & Sounds Fire Truck Activity Board" query didn't return its own correction, while a shorter brand + name query did. So each run now searches with brand, name and model only, and also lists the shop's memories once, putting both through the same overlap guard. In the recorded run the fire-truck correction came through the list.

## Where it broke

- **A 402 froze training.** When our Tinker credit ran out mid-run, the pending request never resolved, and the loop waited on it with no error. Every wait now has a 300-second timeout, and weights are saved at the end of each epoch.
- **The teacher wouldn't follow rule 7.** Two prompt revisions only reduced the violations, so in the end code enforced the rule on the training targets.
- **Backboard's free credit covered memory only.** We had planned to run extra open-weight baselines through Backboard's chat, and that wasn't included, so those rows aren't in the table.
- **Entire recorded nothing.** Its hooks are installed per repository, and our coordinating session was started outside the repo folder, so no checkpoints exist and we didn't enter that category.
- **The first labelling run crashed on its first write** because the output folder didn't exist yet. That took one line to fix.
- **Some recalls can't be read by anyone.** Six notices end with "the following model numbers are included:" and put the list only on cpsc.gov, which refuses automated requests.

## Why Does Open Innovation Matter?

A small shop's margins can't carry a frontier-model bill per item per week. Open weights let us train a 4B for this one job, and training is where the false alarms went; a closed API would have left a choice between the expensive model and the noisy prompt.

No lock-in either: the adapter exports as PEFT weights for a shop's own vLLM or llama.cpp server, selected with one environment variable, and with no keys RecallDesk still runs on its rules classifier and labels its cards accordingly. Specs, splits, predictions and the eval script are in the repo, so anyone can re-score our 293 pairs or add the human answer key we didn't get to.

Privacy: everything RecallDesk reads is public (CPSC's open API, public eBay search results via SerpApi). Seller usernames never leave the gitignored raw cache, and the demo shops are invented. By default, though, labelling, training and inference run on Tinker's hosted GPUs; local means the exported adapter.

## My Agent Session

A coordinating session ran five parallel coding agents (ML and data, Temporal backend, dashboard, charts and screenshots, writing). Its first output wasn't code but [`CONTRACT.md`](https://github.com/SoumyaEXE/recalldesk/blob/main/CONTRACT.md): every data shape, every API route, and the rule that code, not the model, decides what reaches the card. With that pinned, the dashboard was built on real-data fixtures while training was still running, and the parts fit on first connection.

## My First User

No paying shop has used RecallDesk yet, and we won't dress up a hypothetical as a customer. From the first kids' consignment owner we want to learn how long recall checks take today, whether CHECK LABEL is clear without a walkthrough, what price they'd name before seeing ours, and what would stop them. We suspect liability and data entry, which would put a POS import ahead of any model work.

So here's the offer, open until winners are announced: if you run a resale shop or flip on eBay in the U.S., send us your item list or seller name and we'll run it through RecallDesk this Thursday and send you the card, free. We'll add the first real reply to this section, with permission.

## Prize Categories

- **Best Use of Tinker:** Qwen3.5-397B-A17B writes specs and labels; Tinker's training API fine-tunes Qwen3.5-4B (LoRA rank 32), and its sampler serves it every Thursday. On 20 unseen recalls: 0.512 → 0.918 accuracy (p < 0.001), 120 → 12 false alarms of 255, $0.19 vs $2.20 per 1,000 checks, about $19.10 all in. Caveats (teacher-built answer key, 26 of 38 risky flagged) are spelled out above.
- **Best Use of SerpApi:** 235 cached eBay-engine searches across 237 recalls, 12,562 unique listings, and the 45-of-12,562 finding the product is built around; plus a weekly per-store scan via `_sasl` + `_saslop=1`, with 429s never retried.
- **Best Use of Temporal:** a DST-aware Thursday Schedule, per-activity retry and fallback policies, heartbeats on classification, and a worker-kill test: 60 activities, 20 kept, 6 retried, zero duplicates.
- **Best Use of Backboard:** per-shop correction memories, retrieved by meaning and applied by code behind a recall-number and word-overlap guard, so one line from a staffer changes next week's card.

---

If you run a kids' consignment shop or a seasonal sale, or you flip returns on eBay, comment or message us. We'll run your store through RecallDesk free this Thursday and send you the card. For everyone else: has a recall ever made you turn something over to read the label, and what was it?

Built by [@dronzer2code](https://dev.to/dronzer2code) and [@soumyadeepdey](https://dev.to/soumyadeepdey).