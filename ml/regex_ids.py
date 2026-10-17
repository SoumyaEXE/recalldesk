"""Deterministic identifier extraction from CPSC recall text (model / item / style / SKU / UPC / lot / batch ...).

    from ml.regex_ids import extract_ids, find_ids_in_text, norm_id
    extract_ids(description)            -> ["TL1302Z", ...]   (order of appearance, deduped)
    find_ids_in_text(ids, listing_text) -> ids that occur in the listing (separator/case-insensitive)

Used three ways: RecallRecord.regex_ids (baseline + code-side check), the heuristic classifier, and the
label UI highlighter. Pure stdlib. Self-checks on real CPSC descriptions: `python -m ml.regex_ids`.
"""
from __future__ import annotations

import re

# Phrases after which identifiers are listed. Serial-number ranges are deliberately NOT included
# (they never appear in a listing title and are not something a reseller can search for).
_TRIGGER = re.compile(
    r"\b(?:"
    r"model(?:\s+(?:numbers?|nos?\.?|#))?|models|"
    r"item(?:\s+(?:numbers?|nos?\.?|#))|items?\s+#|"
    r"style(?:\s+(?:numbers?|nos?\.?|#))?|styles|"
    r"skus?|sku\s+numbers?|article\s+(?:numbers?|nos?\.?)|"
    r"upcs?(?:\s+(?:codes?|numbers?))?|"
    r"lot(?:\s*/\s*ref)?(?:\s+(?:numbers?|codes?|nos?\.?))?|lots|"
    r"batch(?:\s+(?:numbers?|codes?|nos?\.?))?|batches|"
    r"part(?:\s+(?:numbers?|nos?\.?))|"
    r"product\s+(?:ids?|codes?|numbers?)|"
    r"catalog(?:ue)?\s+(?:numbers?|nos?\.?)|"
    r"date\s+codes?|ref(?:erence)?\s+(?:numbers?|nos?\.?)|"
    r"tcin|dpci|asin|ean"
    r")(?![A-Za-z0-9])\s*[:#]?",
    re.I,
)
# "model name", "model year" etc. are not identifier lists.
_NOT_TRIGGER_AFTER = re.compile(r"^\s*(?:name|year|names|years|line)\b", re.I)

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-./+_]*[A-Za-z0-9+]|[A-Za-z0-9]")
_UNIT = re.compile(
    r"^\d{1,3}(?:\.\d+)?(?:-?(?:inch|inches|in|mm|cm|m|ft|feet|foot|lb|lbs|pound|pounds|oz|ounce|ounces|g|kg|v|w|"
    r"mah|ah|l|ml|gal|gallon|gallons|pack|pk|pc|pcs|piece|pieces|ct|count|qt|quart|psi|hp|cc|btu|amp|amps|a|"
    r"watt|watts|volt|volts|x|s|th|st|nd|rd|day|days|month|months|year|years|yr|hour|hours|min)s?)$|"
    r"^\d{1,5}(?:\.\d+)?-?(?:w|watts?|mah|btu|psi|rpm|lumens?)$", re.I)
_DATEISH = re.compile(r"^(?:19|20)\d\d(?:[/-]\d\d?(?:[/-]\d\d?)?)?$|^\d\d?[/-]\d\d?(?:[/-]\d{2,4})?$|"
                      r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[-/.]?\d{2,4}$", re.I)
_PHONE = re.compile(r"^\d{3}-\d{3}-\d{4}$")
_STOP_CAPS = {
    "UPC", "UPCS", "SKU", "SKUS", "USB", "LED", "USA", "US", "AND", "OR", "THE", "NO", "NOS", "NUMBER", "NUMBERS",
    "MODEL", "MODELS", "ITEM", "STYLE", "LOT", "BATCH", "DATE", "CODE", "ID", "AC", "DC", "PVC", "ABS", "BPA",
    "CPSC", "ASTM", "FCC", "UL", "ETL", "CE", "TM", "LLC", "INC", "CO", "LTD", "ALL", "NEW", "SET", "KIT", "XL",
    "XXL", "SM", "ML", "SR", "JR", "FDA", "PCP", "OEM", "N/A", "DESCRIPTION", "PRODUCT", "NAME", "COLOR", "SIZE",
    "SERIAL", "RANGE", "QTY", "TOTAL", "UNITS", "SOLD", "BRUSH",
}
_STOP_WORDS = {"and", "or", "the", "a", "an", "of", "in", "on", "is", "are", "with", "to", "from", "for", "as",
               "number", "numbers", "no", "no.", "nos", "model", "models", "include", "includes", "including",
               "following", "between", "through"}
_WORD_PARTS = {"in", "head", "heads", "pack", "piece", "pc", "way", "speed", "drawer", "drawers", "light", "lights",
               "inch", "year", "month", "day", "port", "tier", "seat", "seater", "ply", "layer", "tone", "step", "door",
               "person", "burner", "gallon", "quart", "foot", "ft", "watt", "volt", "shelf", "cube", "bike",
               "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
               "november", "december"}
_UPC_SPAN = re.compile(r"(?<![\dA-Za-z])\d(?:[ \-]?\d){10,13}(?![\dA-Za-z])")
_SENT_END = re.compile(r"\.\s+(?=[A-Z\"“(])|\.\s*$|;\s|\n")


def norm_id(s: str) -> str:
    """Canonical comparison form: upper-case, separators removed."""
    return re.sub(r"[\s\-./_]", "", s.upper())


def _clean_token(t: str) -> str:
    return t.strip(".,;:()[]{}\"'“”’*")


def _is_id(tok: str, first: bool) -> bool:
    t = _clean_token(tok)
    if len(t) < 3 or len(t) > 32:
        return False
    if _UNIT.match(t) or _DATEISH.match(t) or _PHONE.match(t):
        return False
    if t.lower() in _STOP_WORDS or t.upper() in _STOP_CAPS:
        return False
    if re.search(r"https?|www\.|\.com$", t, re.I):
        return False
    if re.fullmatch(r"\d+/\d+|20\d\d(?:0[1-9]|1[0-2])|MY\d{4}(?:-MY\d{4})?", t, re.I):
        return False  # fractions / ranges, YYYYMM, model years
    if any(p.lower() in _WORD_PARTS for p in re.split(r"[-/]", t)):
        return False  # "3-head", "2-in-1", "2025-August"
    digits = sum(c.isdigit() for c in t)
    letters = sum(c.isalpha() for c in t)
    if digits == 0:
        # all-caps letter-only style codes (e.g. "style FMHVR") only right after the trigger
        return first and t.isupper() and 4 <= len(t) <= 12 and letters >= 4
    if letters == 0:
        n = len(re.sub(r"\D", "", t))  # bare numbers: style / item / model numbers
        return n >= 5 or (n == 4 and first)
    if re.fullmatch(r"\d+(?:st|nd|rd|th)", t, re.I):
        return False
    if re.fullmatch(r"[A-Za-z]\d", t):  # "M2", "A4" too short to be distinctive
        return False
    return True


def _window(text: str, start: int, max_len: int = 700) -> str:
    seg = text[start : start + max_len]
    m = _SENT_END.search(seg)
    # tables ("Model Number Product Description ... T4X1076DMN ...") have no sentence ends -> long window
    return seg[: m.start()] if m and m.start() > 0 else seg


_EXCLUDE_SENT = re.compile(r"\b(?:not (?:included|part of|affected|being recalled|subject to|involved)|"
                           r"are excluded|is excluded|excluded from|no other (?:models?|products?))\b", re.I)


def _kind(trig: str) -> str:
    t = trig.lower()
    for k, pre in (("upc", ("upc", "ean")), ("lot", ("lot", "batch", "date code")), ("sku", ("sku", "tcin", "dpci",
                   "asin", "article")), ("item", ("item",)), ("style", ("style",)), ("part", ("part", "catalog")),
                   ("product_id", ("product",)), ("ref", ("ref",))):
        if t.startswith(pre):
            return k
    return "model"


def _sentence_at(text: str, pos: int) -> str:
    a = max(text.rfind(". ", 0, pos), text.rfind("; ", 0, pos))
    b = text.find(". ", pos)
    return text[a + 1 : b if b != -1 else len(text)]


def extract_ids_typed(text: str, upcs: list[str] | None = None) -> list[dict]:
    """[{"id", "kind": model|item|style|sku|upc|lot|part|product_id|ref, "excluded": bool}] in order of appearance."""
    if not text:
        return []
    text = (text.replace(" ", " ").replace(" ", " ").replace("‑", "-").replace("–", "-"))
    out: list[dict] = []
    seen: dict[str, dict] = {}

    def add(t: str, kind: str, excluded: bool = False) -> None:
        t = _clean_token(t)
        k = norm_id(t)
        if not k:
            return
        if k in seen:
            seen[k]["excluded"] = seen[k]["excluded"] and excluded
            return
        seen[k] = {"id": t, "kind": kind, "excluded": excluded}
        out.append(seen[k])

    trigs = list(_TRIGGER.finditer(text))
    for ti, m in enumerate(trigs):
        if _NOT_TRIGGER_AFTER.match(text[m.end():]):
            continue
        trig = m.group(0).strip(" :#").lower()
        kind = _kind(trig)
        excluded = bool(_EXCLUDE_SENT.search(_sentence_at(text, m.start())))
        win = _window(text, m.end())
        nxt = next((t2 for t2 in trigs[ti + 1:] if _kind(t2.group(0).strip(" :#")) != kind), None)
        if nxt is not None and nxt.start() - m.end() < len(win):
            win = win[: max(0, nxt.start() - m.end())]  # stop at the next trigger of a different kind
        if kind == "upc":
            for u in _UPC_SPAN.findall(win):
                add(re.sub(r"\D", "", u), "upc", excluded)
            continue
        first = True
        for tm in _TOKEN.finditer(win):
            tok = tm.group(0)
            if _is_id(tok, first):
                add(tok, kind, excluded)
            elif tok.lower() in ("number", "numbers", "no", "nos", "#", "is", "are", "of"):
                continue  # filler right after the trigger keeps `first`
            first = False
    for u in upcs or []:
        add(re.sub(r"\D", "", u), "upc")
    # explicit 12/13-digit UPC-looking spans next to the word UPC anywhere (e.g. "UPC: 0 12345 67890 1")
    for m in re.finditer(r"\bUPC[^0-9]{0,15}(" + _UPC_SPAN.pattern + ")", text):
        add(re.sub(r"\D", "", m.group(1)), "upc")
    return out


def extract_ids(text: str, upcs: list[str] | None = None) -> list[str]:
    """Identifiers mentioned after model/item/style/SKU/UPC/lot/batch/part phrases (+ explicit UPCs).
    Ids that only appear in an exclusion sentence ("... are not included in this recall") are dropped."""
    return [x["id"] for x in extract_ids_typed(text, upcs) if not x["excluded"]]


def find_ids_in_text(ids: list[str], text: str) -> list[str]:
    """Return the ids that occur in `text` (case-insensitive, ignoring - . / space separators, token-bounded)."""
    if not ids or not text:
        return []
    hay = " " + re.sub(r"[\-./_]", "", text.upper()) + " "
    hay_tokens = set(re.findall(r"[A-Z0-9+]+", hay))
    found = []
    for i in ids:
        k = norm_id(i)
        if len(k) < 3:
            continue
        if k in hay_tokens:
            found.append(i)
        elif len(k) >= 6 and re.search(r"(?<![A-Z0-9])" + re.escape(k), hay.replace(" ", " ")):
            found.append(i)  # prefix-bounded (e.g. "TL1302ZB" listing variant of TL1302Z) - long ids only
    return found


# ------------------------------------------------------------------------------- self-checks
# (description excerpt, ids that MUST be found, ids that must NOT be found) - all real CPSC text.
_CASES = [
    ("This recall involves the Scotch™ thermal laminator, model number TL1302Z.  The laminator is light gray/white "
     "with gray accents. The laminating slot is approximately 13 inches wide.", ["TL1302Z"], ["13"]),
    ("This recall involves the Cupcakes and Cashmere Brand Three-Light Floor Lamps, model 7927-OZ and model 7927-OZ1. "
     "Lamps with model number 7927-OZ (associated with HomeGoods style numbers 190734 and 211918) are gold.",
     ["7927-OZ", "7927-OZ1", "190734", "211918"], []),
    ("Only machines with model number LTD-SM23 and date code 7W15TN are included in this recall.",
     ["LTD-SM23", "7W15TN"], []),
    ("This recall involves Courant Spliced Kalimba climbing ropes with part numbers MH730JZC045 (45m length) lollipop "
     "color, MH730JZC050 (50m length), lollipop color MH730JZC060 (60m length) lollipop color",
     ["MH730JZC045", "MH730JZC050", "MH730JZC060"], ["45m", "50m"]),
    ("This recall involves Apeks model XL4, XL4+ and XL4 Ocea second stage scuba regulators sold from April 2025 "
     "through June 2026. They were sold with serial numbers between 250402212 and 260402893.",
     ["XL4", "XL4+"], ["250402212", "2025"]),
    ("the batch number DS250238 on the back of packaging.", ["DS250238"], []),
    ('"Three Drawer Dresser," model number WE11E5080Wx3-W or WE11E5081Rx3-W and batch number SME2025112805 or '
     'SME2025102401 are printed on a label on the back of the dresser.',
     ["WE11E5080Wx3-W", "WE11E5081Rx3-W", "SME2025112805", "SME2025102401"], []),
    ("“Model No.: YD-001,” “Lot/Ref: YD-260320” and “Date 2026/03/20” are printed on a label.",
     ["YD-001", "YD-260320"], ["2026/03/20"]),
    ("This recall involves Woodure-branded children's tower kitchen step stools, models WD1764, WD1357, and WD1720. "
     "The tower stools measure 18 inches deep by 16.9 inches wide.", ["WD1764", "WD1357", "WD1720"], ["16.9"]),
    ("The product SKU (sa25092843915310553, sa2404237092800828, or sa251115653050553503) is printed on the front.",
     ["sa25092843915310553", "sa2404237092800828", "sa251115653050553503"], []),
    ("This recall involves the CCM Hybrid Hockey Visors, style FMHVR and replacement visor accessories, style ACCHVR.",
     ["FMHVR", "ACCHVR"], ["CCM"]),
    ("The model name \"BLITZ\" or \"BLITZ 777\" is also marked on the left side of the receiver.", [], ["BLITZ"]),
    ("The UPC code 0 12345 67890 5 is on the package. Model Number Product Description Serial Number Range "
     "T4X1076DMN DR TRIMMER PILOT 7.6 FPT DR MS All T4X1076DMNR DR TRIMMER", ["012345678905", "T4X1076DMN",
                                                                              "T4X1076DMNR"], ["7.6"]),
]


def _selfcheck() -> int:
    bad = 0
    for text, must, must_not in _CASES:
        got = extract_ids(text)
        gk = {norm_id(g) for g in got}
        miss = [m for m in must if norm_id(m) not in gk]
        extra = [m for m in must_not if norm_id(m) in gk]
        ok = not miss and not extra
        bad += not ok
        print(("ok  " if ok else "FAIL"), got, ("missing=" + str(miss)) if miss else "", ("unwanted=" + str(extra)) if extra else "")
    assert find_ids_in_text(["TL1302Z"], "Scotch Thermal Laminator TL-1302Z 13in") == ["TL1302Z"]
    assert find_ids_in_text(["XL4"], "Apeks XL4+ regulator") == []  # XL4+ is its own token
    assert find_ids_in_text(["WD1764"], "kitchen tower wd1764 bamboo") == ["WD1764"]
    print(f"{len(_CASES) - bad}/{len(_CASES)} extraction cases pass")
    return bad


if __name__ == "__main__":
    import sys

    for s in (sys.stdout,):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    raise SystemExit(1 if _selfcheck() else 0)
