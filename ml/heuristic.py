"""Deterministic (zero-key) recall tools: a rough RecallSpec builder and a match/check/no_match classifier.

    from ml.heuristic import spec_from_record, classify_heuristic
    spec = spec_from_record(record_dict)                  # RecallSpec
    v = classify_heuristic(spec_or_record, listing_dict)   # MatchVerdict

Baseline in eval and the labelled fallback when no model is available. Pure stdlib + pydantic.
"""
from __future__ import annotations

import re
from typing import Any

from ml.regex_ids import extract_ids_typed, find_ids_in_text, norm_id
from shared.schema import Listing, MatchVerdict, RecallRecord, RecallSpec

# ------------------------------------------------------------------------------------ text utils
_CORP = re.compile(r"\b(?:inc|llc|l\.l\.c|ltd|limited|co|corp|corporation|company|companies|group|holdings|"
                   r"international|intl|usa|us|america|north america|of usa|direct|trading|technology|technologies|"
                   r"enterprises?|brands?|products?|industries|global|store|shop|e-?commerce|import|imports)\b\.?", re.I)
_STOP = {"the", "and", "with", "for", "of", "a", "an", "in", "on", "to", "by", "set", "sets", "new", "kit", "kits",
         "brand", "branded", "recalled", "recall", "recalls", "model", "models", "series", "pack", "piece", "pieces",
         "pcs", "inch", "in", "x", "size", "sizes", "color", "colors", "style", "styles", "item", "items", "lot",
         "&", "-", "all", "plus", "pro", "mini", "max", "large", "small", "medium", "used", "pre", "owned", "nwt",
         "nib", "free", "shipping", "fast", "ship", "oem", "genuine", "authentic", "rare", "vintage", "baby", "kids"}
_ACCESSORY = re.compile(
    r"\b(?:compatible|fits?|fitting|replacement|replace|spare|parts? only|for parts only|manual|instructions?|"
    r"user guide|empty box|box only|packaging only|cover only|case only|skin|decal|sticker|charger only|cord only|"
    r"adapter only|insert only|pouch(?:es)?|refills?|accessor(?:y|ies)|cable only|remote only|knob|screws?|"
    r"hardware only|lid only|base only|strap only|canopy only|cushion only|pad only)\b", re.I)
_FOR_BRAND = re.compile(r"\b(?:for|fits|compatible with|works with)\s+(?:the\s+)?([A-Za-z0-9][\w'&-]*)", re.I)
_COLORS = ["black", "white", "gray", "grey", "silver", "gold", "red", "blue", "navy", "green", "pink", "purple",
           "yellow", "orange", "brown", "beige", "cream", "tan", "ivory", "teal", "turquoise", "multicolor",
           "multi-colored", "clear", "natural", "walnut", "oak", "espresso", "charcoal", "mint", "lavender", "rose gold"]
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}


def toks(s: str | None) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:['’][a-z]+)?", (s or "").lower().replace("™", " ").replace("®", " "))]


def stem(t: str) -> str:
    if len(t) <= 3:
        return t
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith(("sses", "xes", "ches", "shes", "zes")):
        return t[:-2]
    if t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def content_tokens(s: str | None) -> set[str]:
    return {stem(t) for t in toks(s) if t not in _STOP and len(t) > 1 and not t.isdigit()}


def _strip_marks(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("™", "").replace("®", "").replace("©", "")).strip()


# ---------------------------------------------------------------------------------- spec builder
def _firm_from_title(title: str) -> str:
    m = re.match(r"^(.*?)\s+(?:Expands\s+)?Recalls?\b", title)
    if m and not re.search(r"\bRecalled\b", m.group(1)):
        return m.group(1)
    return ""


def _clean_firm(f: str) -> str:
    f = re.sub(r",.*$", "", f)
    f = re.sub(r"\bof\s+[A-Z][\w .]*$", "", f)
    f = _CORP.sub("", f)
    return re.sub(r"\s+", " ", f).strip(" ,.-&")


_GENERIC_CAPS = {"children's", "childrens", "children’s", "baby", "kids", "kid's", "infant", "toddler", "youth",
                 "safety", "multi-purpose", "certain", "about", "over", "the", "this", "these", "new", "portable",
                 "electric", "adult", "women's", "men's", "girls", "boys", "mini", "large", "small", "deluxe"}


def _is_generic(word: str, desc: str) -> bool:
    w = word.strip(" ,.;:'\"’")
    if not w or w.lower() in _GENERIC_CAPS or re.search(r"\d", w) and not re.search(r"[A-Za-z]{2}", w):
        return True
    if re.search(r"\d", w) and "-" in w:  # "15-Drawer", "3-in-1"
        return True
    # a word that also occurs in lower case in the notice is an ordinary word, not a brand
    return bool(re.search(r"(?<![A-Za-z])" + re.escape(w.lower()) + r"(?![A-Za-z])", desc)) and not w.isupper()


def _brand_words(phrase: str, desc: str, take_last: bool = False, max_words: int = 3) -> str:
    words = [w for w in re.split(r"\s+", _strip_marks(phrase)) if w]
    if take_last:
        words = words[-max_words:]
        while words and _is_generic(words[0], desc):
            words = words[1:]
        return " ".join(words)
    out = []
    for w in words[:max_words]:
        if not w[:1].isupper() and not w[:1].isdigit() or _is_generic(w, desc):
            break
        out.append(w)
    return " ".join(out)


def _brand(rec: dict) -> str:
    desc = rec.get("description") or ""
    title = rec.get("title") or ""
    names = rec.get("product_names") or []
    cand = ""
    m = re.search(r"((?:[A-Z0-9][\w&'’.]*\s+){0,1}[A-Z0-9][\w&'’.]*)[- ]branded", desc)
    if m:
        cand = _brand_words(m.group(1), desc, take_last=True, max_words=2)
    if not cand:
        m = re.search(r"((?:[A-Z0-9][\w&'’.\-]*\s+){0,1}[A-Z0-9][\w&'’.\-]*)\s*[™®]", " ".join(names) + " " + title + " "
                      + desc)
        if m:
            cand = _brand_words(m.group(1), desc, take_last=True, max_words=2)
    if not cand:
        m = re.search(r"\binvolves\s+(?:the\s+)?([A-Z][\w&.\-]+)['’]s\b", desc)
        if m and not _is_generic(m.group(1), desc):
            cand = m.group(1)
    if not cand and names:
        cand = _brand_words(names[0], desc, max_words=2)
    firm = _clean_firm(_firm_from_title(title))
    cand = _clean_firm(cand)
    if cand and firm and cand.lower() != firm.lower() and cand.lower() not in firm.lower() \
            and firm.lower() not in cand.lower():
        return f"{cand} ({firm})"
    return cand or firm


def _product_type(product_name: str, brand: str) -> str:
    bt = content_tokens(brand)
    name = _strip_marks(product_name)
    name = re.split(r",|\(|;|\s(?:model|models|with|in|sold|and date|item|style|sku|or|for|from|including)\s", name,
                    flags=re.I)[0]
    keep = []
    for w in name.split():
        wl = w.lower().strip(".,:'\"")
        if not wl or re.search(r"\d", w) or (w.isupper() and len(w) <= 5) or stem(wl) in bt or wl in _STOP                 or wl in ("children's", "children’s", "childrens", "kids'", "kid's", "baby", "toddler", "infant",
                          "youth", "and", "or", "&"):
            continue
        keep.append(wl)
    if not keep:
        return re.sub(r"\s+", " ", name.lower()).strip()
    keep = keep[-3:]  # head noun phrase is at the end ("Pull String Teething Toys" -> "string teething toy")
    keep[-1] = stem(keep[-1])
    return " ".join(keep)


def _ym(month: str, year: str) -> str | None:
    m = _MONTHS.get(month.lower())
    return f"{year}-{m:02d}" if m else None


def _sold_window(retailers: list[str]) -> tuple[str | None, str | None]:
    blob = " ".join(retailers)
    froms, tos = [], []
    for m in re.finditer(r"\bfrom\s+([A-Z][a-z]+)\s+(\d{4})\s+(?:through|to|until)\s+([A-Z][a-z]+)\s+(\d{4})", blob):
        a, b = _ym(m.group(1), m.group(2)), _ym(m.group(3), m.group(4))
        if a:
            froms.append(a)
        if b:
            tos.append(b)
    return (min(froms) if froms else None, max(tos) if tos else None)


def spec_from_record(rec: dict | RecallRecord) -> RecallSpec:
    r = rec.model_dump() if isinstance(rec, RecallRecord) else rec
    typed = extract_ids_typed(r.get("description") or "", r.get("upcs") or [])
    models = [x["id"] for x in typed if not x["excluded"] and x["kind"] in ("model", "item", "style", "sku", "part",
                                                                           "product_id", "ref")]
    upcs = [x["id"] for x in typed if not x["excluded"] and x["kind"] == "upc"]
    other = [x["id"] for x in typed if not x["excluded"] and x["kind"] == "lot"]
    excluded = [x["id"] for x in typed if x["excluded"]]
    if not typed and r.get("regex_ids"):
        models = list(r["regex_ids"])
    brand = _brand(r)
    pname = _strip_marks((r.get("product_names") or [""])[0]) or _strip_marks(
        re.sub(r"^.*?Recalls?\s+|\s+(?:Recalled\s+)?Due to.*$", "", r.get("title") or ""))
    pname = re.sub(r"^(?:Certain|About|Over)\s+[\d.,]+\s*(?:Million\s+)?", "", pname)
    ptype = _product_type(pname, brand)
    sold_from, sold_to = _sold_window(r.get("retailers") or [])
    desc_l = (r.get("description") or "").lower()
    colors = [c for c in _COLORS if re.search(r"\b" + re.escape(c) + r"\b", desc_l)][:6]
    brand_short = re.sub(r"\s*\(.*\)$", "", brand)
    name_wo_brand = " ".join(w for w in pname.split() if w.lower() not in brand_short.lower().split())
    qwords = []
    for w in f"{brand_short} {name_wo_brand}".replace('"', " ").replace("(", " ").replace(")", " ").split():
        wl = w.lower().strip(",.;:")
        if wl in ("and", "or", "the", "of", "with", "model", "models", "number", "numbers", "certain", "recalled")                 or re.fullmatch(r"\d+|(?:19|20)\d\d", wl) or wl in (x.lower() for x in qwords):
            continue
        qwords.append(w.strip(",.;:"))
    q1 = " ".join(qwords[:6]).strip()
    queries = [q1] if q1 else []
    if models:
        queries.append(f"{brand_short} {models[0]}".strip())
    hz = (r.get("hazards") or [""])[0]
    hz_short = re.sub(r"^The recalled [^,]*?(?:can|could|pose|poses|may)\s+", "", hz)
    hz_short = " ".join(hz_short.split()[:10]).rstrip(".,;")
    rem = ", ".join(r.get("remedy_options") or []) or "see notice"
    return RecallSpec(
        recall_number=r["recall_number"], brand=brand, product_type=ptype, product_name=pname,
        model_numbers=models, upcs=upcs, other_identifiers=other, sold_from=sold_from, sold_to=sold_to,
        colors=colors, key_features=[], not_included=excluded, search_queries=queries,
        is_childrens=bool(r.get("is_childrens")), hazard_short=hz_short, remedy_short=f"Stop using; {rem.lower()}",
    )


# ---------------------------------------------------------------------------------- classifier
def _as_spec(x: Any) -> dict:
    if isinstance(x, RecallSpec):
        return x.model_dump()
    if isinstance(x, RecallRecord):
        return spec_from_record(x).model_dump()
    if isinstance(x, dict) and "description" in x and "brand" not in x:
        return spec_from_record(x).model_dump()
    return dict(x)


def _listing_blob(listing: dict) -> str:
    spec = listing.get("item_specifics") or {}
    vals = " ".join(str(v) if not isinstance(v, list) else " ".join(map(str, v)) for v in spec.values())
    return " ".join(filter(None, [listing.get("title"), listing.get("subtitle"), vals]))


def _brand_tokens(brand: str) -> set[str]:
    out = set()
    for part in re.split(r"[()/,]", brand or ""):
        part = _clean_firm(part)
        out |= {t for t in toks(part) if len(t) > 1 and t not in _STOP}
    return out


def _id_like(text: str) -> list[str]:
    return [t for t in re.findall(r"\b[A-Za-z0-9][A-Za-z0-9\-]{2,}\b", text)
            if re.search(r"\d", t) and re.search(r"[A-Za-z]", t)]


def classify_heuristic(spec_or_record: Any, listing: dict | Listing) -> MatchVerdict:
    spec = _as_spec(spec_or_record)
    lst = listing.model_dump() if isinstance(listing, Listing) else listing
    text = _listing_blob(lst)
    title = lst.get("title") or ""
    ids = [*spec.get("model_numbers", []), *spec.get("upcs", []), *spec.get("other_identifiers", [])]
    found = find_ids_in_text(ids, text)
    excluded_hit = find_ids_in_text(spec.get("not_included", []), text)
    lt = content_tokens(text)
    l_raw = set(toks(text))
    bt = _brand_tokens(spec.get("brand", ""))
    brand_hit = bool(bt & l_raw) if bt else False
    tt = content_tokens(spec.get("product_type", ""))
    type_hit = bool(tt & lt)
    nt = content_tokens(spec.get("product_name", "")) - {stem(b) for b in bt}
    name_overlap = len(nt & lt) / len(nt) if nt else 0.0
    brand_s = re.sub(r"\s*\(.*\)$", "", spec.get("brand", "")) or "brand"
    ptype = spec.get("product_type") or "product"

    acc = _ACCESSORY.search(title)
    for_m = _FOR_BRAND.search(title)
    for_brand = bool(for_m and for_m.group(1).lower() in bt)
    recall_is_accessory = bool(_ACCESSORY.search(spec.get("product_name", "") + " " + ptype))
    if (acc or for_brand) and not recall_is_accessory:
        cue = acc.group(0) if acc else for_m.group(0)
        return MatchVerdict(verdict="no_match", identifiers_found=found, conflicts=[f"accessory cue: '{cue}'"],
                            reason=f"Looks like an accessory/part ('{cue}'), not the recalled {ptype}.")
    if excluded_hit:
        return MatchVerdict(verdict="no_match", identifiers_found=[], conflicts=[f"excluded: {x}" for x in excluded_hit],
                            reason=f"Names {excluded_hit[0]}, which the recall excludes.")
    if found:
        lots_needed = bool(spec.get("other_identifiers")) and not find_ids_in_text(spec.get("other_identifiers", []),
                                                                                   text)
        if lots_needed and not set(found) & set(spec.get("upcs", [])):
            return MatchVerdict(verdict="check", identifiers_found=found, conflicts=[],
                                reason=f"Model {found[0]} is recalled only with certain lot/date codes; check the label.")
        return MatchVerdict(verdict="match", identifiers_found=found, conflicts=[],
                            reason=f"Recalled identifier {found[0]} appears in the listing.")
    # sibling model number of the same family that is not in the list -> conflict
    fam = {norm_id(i)[:3] for i in spec.get("model_numbers", []) if len(norm_id(i)) >= 5}
    sib = [t for t in _id_like(text) if norm_id(t)[:3] in fam and len(norm_id(t)) >= 5]
    if brand_hit and (type_hit or name_overlap >= 0.5):
        if sib:
            return MatchVerdict(verdict="no_match", identifiers_found=[], conflicts=[f"model {sib[0]} not in recall"],
                                reason=f"Same {brand_s} line but model {sib[0]} is not on the recalled list.")
        if spec.get("model_numbers") or spec.get("upcs") or spec.get("other_identifiers"):
            return MatchVerdict(verdict="check", identifiers_found=[], conflicts=[],
                                reason=f"Same {brand_s} {ptype}, but no model number shown; check the label.")
        if name_overlap >= 0.6 or (type_hit and len(nt) <= 2):
            return MatchVerdict(verdict="match", identifiers_found=[], conflicts=[],
                                reason=f"Names the recalled {brand_s} product; recall covers all units.")
        return MatchVerdict(verdict="check", identifiers_found=[], conflicts=[],
                            reason=f"Same {brand_s} {ptype}; product line unclear from the listing.")
    if brand_hit:
        return MatchVerdict(verdict="no_match", identifiers_found=[], conflicts=[],
                            reason=f"Same brand {brand_s} but a different kind of product.")
    return MatchVerdict(verdict="no_match", identifiers_found=[], conflicts=[],
                        reason=f"Different brand/product than the recalled {brand_s} {ptype}.")
