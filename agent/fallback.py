"""Zero-key fallbacks used when ml/ hasn't provided them (or provider=heuristic):

    heuristic_spec(recall)            RecallRecord -> RecallSpec (regex ids, sold window, hazard/remedy one-liners)
    heuristic_classify(spec, listing) RecallSpec x Listing -> MatchVerdict (identifier + brand/product rules)
    BM25                              tiny BM25 over specs for top-k retrieval per inventory item
    label_hint(recall)                "where to look" sentence from the CPSC description (for CHECK LABEL rows)

Everything here is deterministic and labelled `heuristic` wherever it surfaces.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from shared.schema import Listing, MatchVerdict, RecallSpec

HEURISTIC_NAME = "heuristic-rules-v1"

_MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
_SOLD = re.compile(r"from\s+(?:(\w+)\s+)?(\d{4})\s+(?:through|to|until)\s+(?:(\w+)\s+)?(\d{4})", re.I)
_SOLD1 = re.compile(r"\bin\s+(\w+)\s+(\d{4})\b", re.I)
_STOP = set("""a an and the of for with to in on at by from or recalls recall recalled due risk serious injury death
hazard hazards violate mandatory standard sold amazon com inc llc ltd co usa us brand branded new used pre owned
preowned item items set sets size kids kid children childrens baby babies toddler infant youth adult portable product
products model models no number only all this these that is are be it its x pcs piece pieces""".split())
_ACCESSORY = re.compile(
    r"\b(for|fits|compatible with|replacement|replacement part|parts? only|manual|instructions|box only|empty box|"
    r"cover only|sticker|decal|charger only|cable only|strap only|accessor(?:y|ies))\b", re.I)


def norm(s: str) -> str:
    s = (s or "").replace("™", " ").replace("®", " ").replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def tokens(s: str) -> list[str]:
    out = []
    for t in norm(s).split():
        if t in _STOP or len(t) < 2:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]  # crude plural fold: sleepers -> sleeper
        out.append(t)
    return out


def _ym(month: str | None, year: str) -> str:
    m = _MONTHS.get((month or "").lower())
    return f"{year}-{m:02d}" if m else year


# ------------------------------------------------------------------------------------------ spec
def _brand_from(recall: dict) -> str:
    title = recall.get("title", "")
    m = re.match(r"^(.*?)\s+(?:Recalls|Expands|Reannounces|Recall of)\b", title)
    if m:
        b = re.sub(r"\b(Inc|LLC|Ltd|Co|Corporation|Company|USA|America|North America|Direct|International|"
                   r"Distribution|Group|Trading|Industries|Technology|of USA|U\.S\.)\b\.?,?", "", m.group(1))
        b = re.sub(r"\s+", " ", b).strip(" ,.")
        if b:
            return b
    pn = re.sub(r"[™®]", "", (recall.get("product_names") or [""])[0])
    words = pn.split()
    if not words:
        return ""
    # "Hampton Bay Halwin ...", "Little Rawr Pull String ...": keep a second capitalized word
    if len(words) > 1 and words[1][:1].isupper() and words[1].isalpha() and words[1].lower() not in _GENERIC_FIRST:
        return f"{words[0]} {words[1]}"
    return words[0]


_GENERIC_FIRST = set("""over adult adults portable baby babies children children's childrens kids kid six-drawer metal light-up
rechargeable electric magnetic mini youth infant toddler heated squishy pull rainbow wooden personalized pool
toddler's men's women's the a an and of in on with set sets twin full queen king outdoor indoor universal
replacement accessory additional certain select""".split())


def _product_brand(recall: dict, firm: str) -> str:
    desc_lc = " ".join([recall.get("description", ""), recall.get("title", "")])
    desc_lc = " ".join(w for w in re.split(r"\s+", desc_lc) if w[:1].islower())
    for src in (_product_type(recall), *(recall.get("product_names") or [])):
        w = re.sub(r"[™®]", "", (src or "").split(" ")[0] if src else "").strip(",.")
        if (w and len(w) >= 3 and w[0].isupper() and w.replace("-", "").isalpha() and w.lower() not in _GENERIC_FIRST
                and w.lower() not in norm(firm).split()
                # a brand never shows up as a lowercase common word in the notice ("fire engine", "convertible")
                and not re.search(rf"(?<![A-Za-z]){w.lower()}(?![A-Za-z])", desc_lc)):
            return w
    return ""


def _product_type(recall: dict) -> str:
    title = recall.get("title", "")
    m = re.search(r"Recall(?:s|ed)?(?:\s+of)?\s+(.*?)\s+(?:Due to|Recalled Due|Because)", title)
    pt = m.group(1) if m else (recall.get("product_names") or [""])[0]
    return re.sub(r"[™®]", "", pt).strip()


def label_hint(recall: dict) -> str:
    """The sentence that says where the deciding identifier lives (label / tag / sticker / packaging)."""
    sents = re.split(r"(?<=[.!?])\s+", recall.get("description") or "")
    # narrow pass first (label / tag / sticker sentences), then a wider pass (engraved, underside, back of ...)
    for where, what in ((_WHERE_NARROW, _WHAT_NARROW), (_WHERE_WIDE, _WHAT_WIDE)):
        for sent in sents:
            if where.search(sent) and what.search(sent):
                return sent.strip()[:240]
    return ""


_WHERE_NARROW = re.compile(r"\b(printed|located|found|stamped|embossed|sewn|label|tag|sticker)\b", re.I)
_WHAT_NARROW = re.compile(r"\b(model|item|batch|lot|date|code|number|serial|upc|style)\b", re.I)
_WHERE_WIDE = re.compile(r"\b(printed|located|found|stamped|embossed|engraved|etched|molded|moulded|imprinted|sewn|"
                         r"label|tag|sticker|underside|bottom of|back of|inside of)\b", re.I)
_WHAT_WIDE = re.compile(r"\b(model|item|batch|lot|date|code|number|serial|upc|style|sku)\b", re.I)


def heuristic_spec(recall: dict) -> RecallSpec:
    retail = " ".join(recall.get("retailers") or [])
    sold_from = sold_to = None
    m = _SOLD.search(retail)
    if m:
        sold_from, sold_to = _ym(m.group(1), m.group(2)), _ym(m.group(3), m.group(4))
    else:
        m1 = _SOLD1.search(retail)
        if m1:
            sold_from = sold_to = _ym(m1.group(1), m1.group(2))
    ids = list(recall.get("regex_ids") or [])
    upcs = [i for i in ids if re.fullmatch(r"\d{12,13}", i)]
    desc = recall.get("description", "")
    model_ids, other = [], []
    for i in ids:
        if i in upcs:
            continue
        # identifiers introduced by batch/lot/date words are "other" (date codes etc.)
        ctx = re.search(r"(batch|lot|date code|ref|serial)[^.]{0,30}" + re.escape(i), desc, re.I)
        (other if ctx else model_ids).append(i)
    not_inc = [s.strip()[:200] for s in re.split(r"(?<=[.])\s+", desc)
               if re.search(r"\b(not included|are not part|is not part|not affected|not being recalled|excluded)\b",
                            s, re.I)]
    brand = _brand_from(recall)
    pb = _product_brand(recall, brand)
    if pb and pb.lower() not in norm(brand).split():
        brand = f"{pb} ({brand})" if brand else pb
    pname = re.sub(r"[™®]", "", (recall.get("product_names") or [recall.get("title", "")])[0]).strip()
    hz = re.search(r"Due to (.*?)(?:;|$)", recall.get("title", ""))
    remedy = (recall.get("remedy_options") or [""])[0]
    rem_txt = (recall.get("remedies") or [""])[0]
    remedy_short = ("Stop using; " + (remedy.lower() if remedy else "contact firm")) if rem_txt else remedy
    q = " ".join(dict.fromkeys(f"{brand} {pname}".split()))
    queries = [q] + [f"{brand} {i}" for i in model_ids[:2]]
    return RecallSpec(
        recall_number=recall["recall_number"], brand=brand, product_type=_product_type(recall), product_name=pname,
        model_numbers=model_ids, upcs=upcs + list(recall.get("upcs") or []), other_identifiers=other,
        sold_from=sold_from, sold_to=sold_to, colors=[], key_features=[], not_included=not_inc,
        search_queries=list(dict.fromkeys(queries)), is_childrens=bool(recall.get("is_childrens")),
        hazard_short=(hz.group(1).strip() if hz else (recall.get("hazards") or [""])[0][:120]),
        remedy_short=remedy_short or "See CPSC notice")


# -------------------------------------------------------------------------------------- classify
def listing_text(listing: Listing) -> str:
    spec_txt = " ".join(f"{k} {v}" for k, v in (listing.item_specifics or {}).items())
    return " ".join(x for x in (listing.title, listing.subtitle or "", spec_txt) if x)


def heuristic_classify(spec: RecallSpec, listing: Listing) -> MatchVerdict:
    text = listing_text(listing)
    ctext = compact(text)
    ltoks = set(tokens(text))
    ids = [i for i in spec.model_numbers + spec.upcs + spec.other_identifiers if len(compact(i)) >= 3]
    found = [i for i in ids if compact(i) in ctext]
    model_found = [i for i in found if i in spec.model_numbers or i in spec.upcs]
    btoks = [t for t in tokens(spec.brand) if len(t) >= 3]
    brand_hit = _brand_hit(spec.brand, ltoks, ctext)
    ptoks = set(tokens(f"{spec.product_type} {spec.product_name}")) - set(btoks)
    prod_overlap = sorted((ptoks & ltoks) | {t for t in ptoks if len(t) >= 6 and t in ctext})
    prod_hit = len(prod_overlap) >= 1
    conflicts: list[str] = []
    if brand_hit and prod_hit:
        nc = _numeric_conflict(f"{spec.product_name} {spec.product_type}", text)
        if nc:
            return MatchVerdict(verdict="no_match", conflicts=[nc],
                                reason=f"Same {spec.brand} line but a different size/variant ({nc}).")

    for ex in spec.not_included:
        exids = [i for i in re.findall(r"[A-Z0-9][A-Z0-9-]{3,}", ex) if re.search(r"\d", i)]
        if any(compact(i) in ctext for i in exids):
            return MatchVerdict(verdict="no_match", identifiers_found=[], conflicts=[f"excluded: {ex[:80]}"],
                                reason="Listing names a model the recall explicitly excludes.")
    if _ACCESSORY.search(text) and not model_found:
        if brand_hit or prod_hit:
            return MatchVerdict(verdict="no_match", conflicts=["accessory / compatible-with item"],
                                reason="Accessory, part or 'compatible with' item, not the recalled product itself.")

    limited = [i for i in spec.other_identifiers if i not in found]
    if model_found and limited and (brand_hit or prod_hit):
        return MatchVerdict(verdict="check", identifiers_found=found,
                            reason=f"Model {model_found[0]} matches, but only units with code(s) "
                                   f"{', '.join(limited[:3])} are recalled; check the label.")
    if model_found and (brand_hit or prod_hit or len(compact(model_found[0])) >= 6):
        return MatchVerdict(verdict="match", identifiers_found=found,
                            reason=f"Recalled identifier {model_found[0]} appears"
                                   + (f" with brand {spec.brand}" if brand_hit else "") + ".")
    if not (brand_hit and prod_hit):
        if found and (brand_hit or prod_hit):
            return MatchVerdict(verdict="check", identifiers_found=found,
                                reason=f"Code {found[0]} appears; confirm it is the recalled {spec.product_type}.")
        return MatchVerdict(verdict="no_match", reason="Different brand or product line.")

    # same brand + product line from here
    explicit = str((listing.item_specifics or {}).get("Model") or "").strip()
    listing_ids = [explicit] if explicit else [
        t for t in re.findall(r"\b[A-Za-z0-9][A-Za-z0-9-]{3,}\b", listing.title)
        if re.search(r"\d", t) and re.search(r"[A-Za-z]", t) and not _MEASURE.fullmatch(t)]
    if spec.model_numbers and listing_ids and not found:
        mod = listing_ids[0]
        return MatchVerdict(verdict="no_match", conflicts=[f"listing model {mod} not in recall"],
                            reason=f"Same {spec.brand} line but model {mod} is not one of the recalled models.")
    deciding = spec.model_numbers + spec.other_identifiers
    if found and spec.other_identifiers and not model_found:
        return MatchVerdict(verdict="check", identifiers_found=found,
                            reason="Batch/date code matches; confirm model on the label.")
    if not deciding and not spec.not_included:
        return MatchVerdict(verdict="match", identifiers_found=[],
                            reason=f"Recall covers all {spec.brand} {spec.product_type}; listing names it unambiguously.")
    return MatchVerdict(verdict="check", identifiers_found=found,
                        reason=f"Same {spec.brand} {spec.product_type}; listing doesn't show "
                               + ("the model/lot number." if deciding else "which variant it is."))


_MEASURE = re.compile(r"\d+(?:\.\d+)?-?(?:inch|in|ft|qt|cu|l|liter|litre|oz|v|w|mah|psi|btu|gal|gallon|drawer|"
                      r"piece|pc|pcs|pack|ct|y|m|t|c|st|nd|rd|th|mm|cm|lb|lbs|pk)s?", re.I)
_NUMWORD = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
_NUMUNIT = re.compile(r"\b(\d+(?:\.\d+)?)\s*-?\s*(drawer|inch|liter|litre|quart|qt|gallon|piece|cu ft|ft|seat)s?\b")


def _numeric_conflict(spec_txt: str, listing_txt: str) -> str:
    def units(t: str) -> dict[str, set[str]]:
        t = t.lower()
        for w, n in _NUMWORD.items():
            t = re.sub(rf"\b{w}(?=[- ](?:drawer|inch|liter|piece|seat))", n, t)
        out: dict[str, set[str]] = {}
        for num, unit in _NUMUNIT.findall(t):
            out.setdefault(unit.replace("litre", "liter").replace("quart", "qt"), set()).add(num)
        return out
    su, lu = units(spec_txt), units(listing_txt)
    for u, nums in lu.items():
        if u in su and not (nums & su[u]):
            return f"{'/'.join(sorted(nums))}-{u} vs recalled {'/'.join(sorted(su[u]))}-{u}"
    return ""


def _brand_hit(brand: str, ltoks: set[str], ctext: str) -> bool:
    for alt in re.split(r"[()]", brand or ""):
        alt = alt.strip()
        if not alt:
            continue
        if len(compact(alt)) >= 4 and compact(alt) in ctext:
            return True
        bt = [t for t in tokens(alt) if len(t) >= 3]
        if not bt or bt[0] in _GENERIC_FIRST or bt[0] not in ltoks:
            continue
        need = len(bt) if len(bt) <= 2 else math.ceil(len(bt) * 2 / 3)
        if sum(t in ltoks for t in bt) >= need:
            return True
    return False


# ------------------------------------------------------------------------------------------ BM25
class BM25:
    def __init__(self, docs: dict[str, str], k1: float = 1.4, b: float = 0.75):
        self.ids = list(docs)
        self.tf = [Counter(tokens(docs[i])) for i in self.ids]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1.0
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(self.ids)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, k: int = 3) -> list[tuple[str, float]]:
        q = tokens(query)
        scores = []
        for idx, c in enumerate(self.tf):
            s = 0.0
            for t in q:
                f = c.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[idx] / self.avg))
            if s > 0:
                scores.append((self.ids[idx], s))
        scores.sort(key=lambda x: -x[1])
        return scores[:k]


def spec_doc(spec: RecallSpec, title: str = "") -> str:
    # brand + product words twice: they carry the signal for inventory names
    core = f"{spec.brand} {spec.product_name} {spec.product_type}"
    return f"{core} {core} {' '.join(spec.model_numbers)} {' '.join(spec.key_features)} {title}"
