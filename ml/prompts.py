"""Prompts + compact text renderings shared by teacher labeling, training, eval and inference.

The label definitions here are the SAME as ml/LABELING.md (humans and the teacher use one rulebook).
Student = short prompt (STUDENT_SYSTEM); teacher = long guided prompt (TEACHER_SYSTEM) - prompt distillation.
"""
from __future__ import annotations

import json
from typing import Any

DEFINITIONS = """\
- match: the listing IS the recalled product. Brand and product line agree AND either (a) a recalled identifier \
(model / item / style / SKU / UPC / lot) appears in the listing, or (b) the recall covers ALL units of a product name \
that the listing names unambiguously. A seller should not list it.
- check: same brand and same product line, but the listing does not show what decides it (model number, date code, \
lot, sold window, size or colour variant). Someone must look at the label before listing it.
- no_match: a different product or brand, a model/variant the recall explicitly excludes, or only an accessory, \
part, manual, "compatible with"/"fits" item, or empty box."""

OUTPUT_SPEC = ('Reply with one JSON object only: {"verdict": "match" | "check" | "no_match", '
               '"identifiers_found": [recalled identifiers that literally appear in the listing], '
               '"conflicts": [listing details that contradict the recall], "reason": "one short sentence"}')

STUDENT_SYSTEM = ("You check marketplace listings against a product recall.\n" + DEFINITIONS + "\n" + OUTPUT_SPEC)

TEACHER_GUIDE = """\
Rules (apply in order):
1. Accessory test. If the listing is only an accessory, part, replacement piece, cover, case, charger, manual, \
"compatible with" / "fits" / "for <brand>" item, sticker, or empty box -> no_match, UNLESS that accessory is itself \
the recalled product (e.g. the recall is for replacement visors and the listing is that replacement visor).
2. Exclusion test. If the listing names a model, size, variant or date that the recall explicitly excludes (or a \
model number of the same family that is not in the recalled list) -> no_match, and put it in "conflicts".
3. Identifier test. If a recalled model / item / style / SKU / UPC / lot number appears in the listing title, subtitle \
or specifics (ignore case, spaces and dashes) and brand/product line agree -> match. If the recall ALSO requires a \
date code, lot or serial range that the listing does not show -> check (the model alone does not decide it).
4. Whole-line recalls. If the recall covers all units of a named product (no identifier list, e.g. "all Blitz and \
Blitz 777 air rifles") and the listing names that exact product by brand and name -> match.
5. Same brand + same product type but the deciding detail is missing (no model number visible, unknown colour/size, \
could be an older non-recalled version) -> check.
6. Different brand, different product type, or only a loosely similar generic product -> no_match. A brand-only \
overlap (same brand, different kind of product) is no_match.
7. Unbranded listings. If the listing names NO brand and shows no recalled identifier, it is a generic look-alike \
-> no_match (e.g. "Bed rail for elderly adults", "13 inch thermal laminator"). Exception -> check: the listing names \
something distinctive to the recalled product that a generic item would not have (a licensed character/design such \
as "101 Dalmatians coin purse", a unique product name, or a distinctive feature combination from the recall). \
Product type plus generic features (size, colour, "foldable", "with storage pouch") is NOT distinctive.
Notes: eBay condition text such as "for parts or not working", "used" or "lot of 2" does not change the product - \
judge the item itself. Never invent identifiers: identifiers_found must be copied from the recall list AND appear in \
the listing. Keep "reason" under 25 words, plain English, for a reseller.
Output the JSON object only, no markdown."""

TEACHER_SYSTEM = STUDENT_SYSTEM + "\n\n" + TEACHER_GUIDE


def _j(xs: list[str] | None, n: int = 12) -> str:
    xs = [x for x in (xs or []) if x]
    if not xs:
        return "none listed"
    more = f" (+{len(xs) - n} more)" if len(xs) > n else ""
    return ", ".join(xs[:n]) + more


def spec_text(spec: dict[str, Any]) -> str:
    """Compact RecallSpec rendering (the student's whole view of the recall)."""
    lines = [
        f"RECALL {spec.get('recall_number', '')}: {spec.get('product_name') or ''} | brand: {spec.get('brand') or '?'}"
        f" | type: {spec.get('product_type') or '?'}",
        f"Recalled model numbers: {_j(spec.get('model_numbers'), 25)}",
    ]
    if spec.get("upcs"):
        lines.append(f"Recalled UPCs: {_j(spec.get('upcs'))}")
    if spec.get("other_identifiers"):
        lines.append(f"Other identifiers (lot/date code/SKU): {_j(spec.get('other_identifiers'))}")
    if spec.get("sold_from") or spec.get("sold_to"):
        lines.append(f"Sold: {spec.get('sold_from') or '?'} to {spec.get('sold_to') or '?'}")
    feats = [*(spec.get("colors") or []), *(spec.get("key_features") or [])]
    if feats:
        lines.append(f"Looks like: {_j(feats, 8)}")
    if spec.get("not_included"):
        lines.append(f"NOT included in the recall: {_j(spec.get('not_included'))}")
    return "\n".join(lines)


def listing_text(listing: dict[str, Any]) -> str:
    lines = [f"LISTING: {listing.get('title') or ''}"]
    if listing.get("subtitle"):
        lines.append(f"Subtitle: {listing['subtitle']}")
    if listing.get("condition"):
        lines.append(f"Condition: {listing['condition']}")
    spec = listing.get("item_specifics") or {}
    if spec:
        kv = "; ".join(f"{k}: {v if not isinstance(v, list) else ', '.join(map(str, v))}" for k, v in spec.items()
                       if v not in (None, "", []))
        if kv:
            lines.append(f"Details: {kv[:400]}")
    return "\n".join(lines)


def user_prompt(spec: dict[str, Any], listing: dict[str, Any], recall_excerpt: str | None = None) -> str:
    parts = [spec_text(spec)]
    if recall_excerpt:
        parts.append("RECALL TEXT (CPSC): " + recall_excerpt)
    parts.append(listing_text(listing))
    return "\n\n".join(parts)


def recall_excerpt(record: dict[str, Any] | None, max_chars: int = 1400) -> str | None:
    if not record:
        return None
    d = (record.get("description") or "").strip()
    return d[:max_chars] + ("..." if len(d) > max_chars else "")


def student_messages(spec: dict, listing: dict) -> list[dict]:
    return [{"role": "system", "content": STUDENT_SYSTEM}, {"role": "user", "content": user_prompt(spec, listing)}]


def guided_messages(spec: dict, listing: dict) -> list[dict]:
    """Base model + the teacher's long rulebook, but the student's input (no recall text)."""
    return [{"role": "system", "content": TEACHER_SYSTEM}, {"role": "user", "content": user_prompt(spec, listing)}]


def teacher_messages(spec: dict, listing: dict, record: dict | None) -> list[dict]:
    """Teacher sees the long rulebook AND the original CPSC description (privileged information)."""
    return [{"role": "system", "content": TEACHER_SYSTEM},
            {"role": "user", "content": user_prompt(spec, listing, recall_excerpt(record))}]


# ------------------------------------------------------------------------------- spec extraction
SPEC_SYSTEM = """\
You turn a US CPSC recall notice into an identification spec that a reseller can use to recognise the recalled \
product in a marketplace listing. Reply with ONE JSON object only, keys exactly:
{"brand": str (brand printed on the product; add the firm in parentheses if different, e.g. "Scotch (3M)"),
 "product_type": str (generic noun phrase, singular, lowercase, e.g. "thermal laminator"),
 "product_name": str (brand + product line as a seller would title it),
 "model_numbers": [recalled model / item / style / SKU / part numbers, copied exactly],
 "upcs": [recalled UPC / EAN codes, digits only],
 "other_identifiers": [lot / batch / date codes / serial ranges, copied exactly, with a short label e.g. "date code 7W15TN"],
 "sold_from": "YYYY-MM" or null, "sold_to": "YYYY-MM" or null,
 "colors": [colours / finishes of recalled units],
 "key_features": [up to 4 short visual identifiers: printed words, shape, size],
 "not_included": [models / variants / dates the notice says are NOT recalled],
 "search_queries": [2-3 eBay search strings, 2-6 words each; FIRST = how a reseller would title it (brand + product line + type, no model number); SECOND = brand + first model number if any],
 "is_childrens": bool (product is intended for children under 12 or for infant care),
 "hazard_short": str (<= 8 words), "remedy_short": str (<= 10 words)}
Rules: never invent identifiers - every model number / UPC / lot must appear in the notice. Use [] when none. \
Output JSON only."""


def spec_user_prompt(rec: dict[str, Any]) -> str:
    return json.dumps({
        "title": rec.get("title"), "product_names": rec.get("product_names"), "description": rec.get("description"),
        "units": rec.get("units"), "hazards": rec.get("hazards"), "remedies": [r[:400] for r in rec.get("remedies", [])],
        "retailers": rec.get("retailers"), "manufacturers": rec.get("manufacturers"), "importers": rec.get("importers"),
        "upcs": rec.get("upcs"), "recall_date": rec.get("recall_date"),
    }, ensure_ascii=False)
