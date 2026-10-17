# RecallDesk labeling guide

One rulebook for the teacher model (`ml/prompts.py` embeds the same definitions and rules) and for any human audit
labels (`python -m ml.label_ui`; none were collected: the eval answer key is the teacher's labels with rule 7 enforced
by code, `data/labeled/targets.jsonl`). Every pair is one **CPSC recall** and one
**eBay listing** (or inventory row). The question is: *should a reseller stop and not list this item?*

## The three labels

- **match**: the listing *is* the recalled product. Brand and product line agree AND (a recalled identifier
  such as a model, item, style, SKU, UPC or lot number appears in the listing, OR the recall covers all units
  of a product name that the listing names unambiguously). The seller should not list it. On the card: **DO NOT SELL**.
- **check**: same brand and same product line, but the listing does not show what decides it (model number,
  date code, lot, sold window, size or colour variant). Someone needs to look at the label before listing it.
  On the card: **CHECK LABEL**.
- **no_match**: a different product or brand, a model or variant the recall explicitly excludes, or only an
  accessory, part, manual, "compatible with" or "fits" item, or an empty box. Not shown on the card.

## Rules, applied in order

1. **Accessory test.** If the listing is only an accessory, part, replacement piece, cover, case, charger, manual,
   "compatible with", "fits" or "for <brand>" item, sticker or empty box, label it **no_match**. The exception is
   when that accessory is itself the recalled product.
2. **Exclusion test.** If the listing names a model, size, variant or date that the recall excludes, label it
   **no_match**. The same applies to a model number from the same family that is not on the recalled list.
3. **Identifier test.** If a recalled identifier appears in the title, subtitle or details and the brand or
   product line agree, label it **match**. Ignore case, spaces and dashes. If the recall also needs a date code,
   lot or serial range that the listing does not show, label it **check** instead.
4. **Whole-line recalls.** Some recalls cover all units of a named product, with no identifier list. If the
   listing names that exact product by brand and name, label it **match**.
5. If it is the same brand and product type but the deciding detail is missing, label it **check**.
6. If it is a different brand, a different product type, or only a loosely similar generic item, label it
   **no_match**. The same brand on a different kind of product is also **no_match**.
7. **Unbranded listings.** If the listing names no brand at all and shows no recalled identifier, it is a
   generic look-alike, so label it **no_match** ("Bed rail for elderly adults", "13 inch thermal laminator").
   The one exception is when the listing names something *distinctive to the recalled product* that a generic
   item would not have: a licensed character or design ("101 Dalmatians coin purse" for the Primark recall), a
   unique product name, or a distinctive feature combination from the recall. Then label it **check**.
   Product type plus generic features (size, colour, "foldable", "with storage pouch") is not distinctive.

Notes:
- eBay conditions like "for parts or not working", "used" or "lot of 2" do not change what the product is.
  Judge the item itself.
- If you cannot tell from the title, open the listing on eBay (the title is a link) and look at the photos or
  item specifics. If it is still unclear, label it **check**. **check** is the honest label for "a person must look".
- Use **s** (skip) only when the page will not load or the pair is broken. Use **n** to add a note for odd cases.
- Label what the listing *is*, not whether the recall is a good one. Do not guess at identifiers that are not shown.

## Worked examples (real CPSC recalls; listing titles are illustrative)

| # | Recall (CPSC no.) | Listing title | Label | Why |
|---|---|---|---|---|
| 1 | Scotch thermal laminator, **model TL1302Z** (27024) | "Scotch Thermal Laminator TL1302Z 13 in. 2 roller - works" | **match** | Brand, product type and the recalled model number all appear. |
| 2 | same (27024) | "Scotch Thermal Laminator, 13 inch, gray/white, used once" | **check** | Same brand and product, but no model number is shown. Check the sticker on the bottom. |
| 3 | same (27024) | "Scotch Thermal Laminating Pouches 9 x 11.5 in, 100 pack" | **no_match** | This is only a consumable or accessory, not the laminator. |
| 4 | Hatsan **Blitz and Blitz 777** air rifles, *all units* sold 2020-2026 (27025) | "Hatsan Blitz .22 PCP air rifle full auto + case" | **match** | The recall covers all Blitz units, and the listing names the product unambiguously. |
| 5 | Love To Dream portable sleep machine, **model LTD-SM23 AND date code 7W15TN** only (26798) | "Love to Dream Portable Sleep Machine LTD-SM23 nightlight" | **check** | The model matches, but the recall needs a specific date code that the listing does not show. |
| 6 | Woodure children's tower stools, **models WD1764, WD1357, WD1720** (26658) | "Woodure kitchen tower step stool for toddlers WD1720 bamboo" | **match** | A recalled model number is in the title. |
| 7 | same (26658) | "Learning tower toddler kitchen stool adjustable, natural wood" | **no_match** | It does not name the brand or a model. It is a similar generic product, not this one (rule 6). |
| 8 | CCM Hybrid hockey visor **FMHVR** and **ACCHVR replacement visor** (26716) | "CCM ACCHVR replacement visor kit hybrid HVR SR" | **match** | The accessory is itself the recalled product, so rule 1's exception applies. |
| 9 | Thule RideAlong child bike seat, **only model 100107 with date codes 21/3-23/10** (24182) | "Thule RideAlong Lite child bike seat 100110" | **no_match** | It is the same line, but model 100110 is not on the recalled list (rule 2). Put the model in `conflicts`. |
| 10 | Bell Soquel youth bicycle helmet **B0726Y, made before Sept 2021** (24118) | "Bell Soquel Youth Bike Helmet 50-57cm blue" | **check** | It is the same helmet, but the manufacture date decides it. Check the label inside the helmet. |
| 11 | Joyin Sloosh dive sticks, **model 40041** (26536) | "Sloosh pool dive toys set 30 pcs dive rings + sticks" | **check** | It is the same brand and product line, but the listing does not say whether the set has the 40041 sticks. |
| 12 | Scotch laminator (27024) | "3M Scotch Magic Tape 6 rolls" | **no_match** | It is the same brand but a different kind of product (rule 6). |

## What gets recorded
`data/gold/labels.jsonl` gets one row per label: `{"pair_id","label","note","labeled_at"}`. If a pair is
labeled again (after undo), the newest row wins. Gold is collected only for the **test** split. The UI never
shows any model, teacher or heuristic output. The only highlighting comes from the deterministic regex
identifiers in the CPSC text.
