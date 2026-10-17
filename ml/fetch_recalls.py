"""Fetch CPSC recalls and normalize them into RecallRecord rows (no key needed).

    python -m ml.fetch_recalls                     # A = since 2026-07-18, B = children's since 2023-01-01
    python -m ml.fetch_recalls --since-a 2026-07-18 --since-b 2023-01-01 [--offline]

Writes data/recalls/raw_A.json, raw_B.json (raw API rows), recalls.jsonl (deduped by recall_number,
corpus tags) and stats.json. `--offline` re-normalizes from the cached raw files (no network).
The API returns UTF-8 bytes; we decode them explicitly (falling back to cp1252 only if the bytes are not
valid UTF-8) so ™ / ’ survive.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from datetime import date

import httpx

from ml.common import RECALLS, utf8_stdout, write_json, write_jsonl
from ml.regex_ids import extract_ids
from shared.schema import RecallRecord

API = "https://www.saferproducts.gov/RestWebServices/Recall"

# ----------------------------------------------------------------------------- children's detector
CHILD_TERMS = [
    r"child(?:ren)?(?:['’]s)?", r"kids?(?:['’]s?)?", r"bab(?:y|ies)(?:['’]s)?", r"infants?(?:['’])?", r"toddlers?",
    r"newborns?", r"cribs?", r"bassinets?", r"(?<!sofa )(?<!couch )sleepers?(?! sofa)", r"strollers?",
    r"car seats?", r"booster seats?", r"high ?chairs?", r"play ?yards?", r"playards?", r"playpens?", r"toys?",
    r"youth", r"teethers?", r"teething", r"pacifiers?", r"rattles?", r"bibs?", r"nursery", r"diapers?",
    r"changing (?:tables?|pads?)", r"baby gates?", r"bouncers?", r"(?:baby|infant) (?:walkers?|swings?|monitors?)",
    r"onesies?", r"sleep ?sacks?", r"swaddles?", r"sleepwear", r"montessori", r"balance bikes?",
    r"activity (?:centers?|cubes?|tables?)", r"bath seats?", r"bunk beds?", r"toddler beds?", r"nursing pillows?",
    r"dolls?", r"plush", r"stuffed animals?", r"slime", r"crayons?", r"bath toys?", r"jumpers?",
    r"stacking (?:toys?|rings?|blocks?)", r"building blocks?", r"infant loungers?", r"baby loungers?",
    r"push ?toys?", r"step stools?", r"learning towers?", r"kitchen towers?", r"tower stools?",
    r"pajamas?", r"nightgowns?", r"robes?(?= for (?:girls|boys|kids|children))", r"girls['’]?", r"boys['’]?",
]
_CHILD_RE = re.compile(r"\b(?:" + "|".join(CHILD_TERMS) + r")\b", re.I)
# ambiguous terms (adult trikes, ride-on mowers, generator cradles) count only in the title head
_CHILD_TITLE_ONLY = re.compile(
    r"\b(?:tricycles?|ride-on (?:toys?|cars?|trucks?|vehicles?)|kids?['’]? (?:scooters?|bikes?))\b", re.I)
# phrases that mention children but are not children's products
_CHILD_NEG = re.compile(
    r"child[- ]resistant|children['’]s gasoline burn prevention act|poison prevention packaging act|"
    r"out of (?:the )?reach of (?:young )?children|keep (?:away|out) .{0,30}children|"
    r"(?:children|kids|child) (?:can|could|may) |reese['’]s law|harm to (?:young )?children|"
    r"(?:risk|deaths?|injur(?:y|ies)) (?:of|to) (?:young )?children|"
    r"button (?:cell|coin) batter(?:y|ies)|sleepers? sofas?|toy haulers?", re.I)
_VIOLATES_CHILD = re.compile(
    r"violat\w*[^.]{0,120}\b(?:infant|child|children|toddler|crib|bassinet|toy|baby|sleep|pacifier|rattle|"
    r"teeth|play yard|high chair|stroller|carrier|bunk bed|walker|bath seat)", re.I)


def _strip_neg(s: str) -> str:
    return _CHILD_NEG.sub(" ", s or "")


def first_sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(parts[:n])


def is_childrens(title: str, product_names: list[str], description: str) -> tuple[bool, str]:
    head, _, tail = (title or "").partition(" Due to ")
    for where, s in (("title", head), ("product", " ; ".join(product_names)), ("desc", first_sentences(description))):
        m = _CHILD_RE.search(_strip_neg(s))
        if m:
            return True, f"{where}:{m.group(0)}"
    if _CHILD_TITLE_ONLY.search(head):
        return True, "title_only"
    m = _VIOLATES_CHILD.search(_strip_neg(tail))
    if m:
        return True, "title_violates"
    return False, ""


# ----------------------------------------------------------------------------- fetch + normalize
def fetch(start: str, end: str | None = None) -> list[dict]:
    params = {"format": "json", "RecallDateStart": start}
    if end:
        params["RecallDateEnd"] = end
    last = None
    for attempt in range(4):
        try:
            r = httpx.get(API, params=params, timeout=60, headers={"Accept": "application/json"})
            if r.status_code >= 500:
                raise httpx.HTTPStatusError(f"CPSC {r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            raw = r.content
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp1252", errors="replace")
            return json.loads(text)
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            last = e
            time.sleep(2 ** attempt * 2)
    raise SystemExit(f"CPSC API failed after retries: {last!r}")


_WS = re.compile(r"[\s  ​]+")


def clean(s: str | None) -> str:
    if not s:
        return ""
    s = s.replace("‑", "-").replace("�", "")
    return _WS.sub(" ", s).strip()


def names(items: list[dict] | None, key: str = "Name") -> list[str]:
    return [clean(x.get(key)) for x in (items or []) if clean(x.get(key))]


def normalize(r: dict, corpus: list[str]) -> RecallRecord:
    title = clean(r.get("Title"))
    desc = clean(r.get("Description"))
    products = r.get("Products") or []
    pnames = [clean(p.get("Name")) for p in products if clean(p.get("Name"))]
    units = next((clean(p.get("NumberOfUnits")) for p in products if clean(p.get("NumberOfUnits"))), None)
    upcs = [re.sub(r"\D", "", u.get("UPC") or "") for u in (r.get("ProductUPCs") or [])]
    upcs = [u for u in upcs if u]
    # identifiers: description first, then product-level model fields and image captions
    id_text = " ".join([desc] + [clean(p.get("Model")) for p in products if p.get("Model")]
                       + [f"model {clean(p.get('Model'))}" for p in products if p.get("Model")])
    child, _why = is_childrens(title, pnames, desc)
    url = clean(r.get("URL")).replace("https://cpsc.gov/", "https://www.cpsc.gov/")
    return RecallRecord(
        recall_number=str(r.get("RecallNumber")), recall_id=r.get("RecallID"),
        recall_date=(r.get("RecallDate") or "")[:10], title=title, description=desc, url=url,
        product_names=pnames, units=units, hazards=names(r.get("Hazards")), remedies=names(r.get("Remedies")),
        remedy_options=names(r.get("RemedyOptions"), "Option"), retailers=names(r.get("Retailers")),
        manufacturers=names(r.get("Manufacturers")), importers=names(r.get("Importers")) + names(r.get("Distributors")),
        images=[clean(i.get("URL")) for i in (r.get("Images") or []) if i.get("URL")], upcs=upcs,
        regex_ids=extract_ids(id_text, upcs), is_childrens=child, corpus=corpus,
    )


RETAILER_PATTERNS = {
    "Amazon": r"amazon", "Temu": r"temu", "Walmart": r"walmart", "Target": r"\btarget\b", "eBay": r"ebay",
    "SHEIN": r"shein", "TikTok Shop": r"tiktok", "AliExpress": r"aliexpress", "Wayfair": r"wayfair",
    "Etsy": r"etsy", "Home Depot": r"home depot", "Lowe's": r"lowe['’]?s", "Costco": r"costco",
}


def iso_week(d: str) -> str:
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def build_stats(recs: list[RecallRecord], since_a: str, since_b: str) -> dict:
    def block(rs: list[RecallRecord]) -> dict:
        ret = Counter()
        for r in rs:
            blob = " ".join(r.retailers).lower()
            for k, pat in RETAILER_PATTERNS.items():
                if re.search(pat, blob):
                    ret[k] += 1
        return {
            "recalls": len(rs), "childrens": sum(r.is_childrens for r in rs),
            "with_regex_ids": sum(bool(r.regex_ids) for r in rs),
            "childrens_with_regex_ids": sum(bool(r.regex_ids) and r.is_childrens for r in rs),
            "with_upcs": sum(bool(r.upcs) for r in rs), "with_images": sum(bool(r.images) for r in rs),
            "mean_regex_ids": round(sum(len(r.regex_ids) for r in rs) / max(1, len(rs)), 2),
            "retailers_mentioning": dict(ret.most_common()),
            "sold_online": sum(any("online" in x.lower() for x in r.retailers) for r in rs),
        }

    a = [r for r in recs if "A" in r.corpus]
    b = [r for r in recs if "B" in r.corpus]
    by_week = Counter(iso_week(r.recall_date) for r in a)
    by_year_b = Counter(r.recall_date[:4] for r in b)
    return {
        "generated_at": date.today().isoformat(), "since_a": since_a, "since_b": since_b,
        "total_unique": len(recs), "A": block(a), "B": block(b), "A_and_B": sum(len(r.corpus) == 2 for r in recs),
        "A_by_week": dict(sorted(by_week.items())), "B_by_year": dict(sorted(by_year_b.items())),
    }


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-a", default="2026-07-18")
    ap.add_argument("--since-b", default="2023-01-01")
    ap.add_argument("--offline", action="store_true", help="re-normalize from cached raw_A/raw_B.json")
    args = ap.parse_args()
    RECALLS.mkdir(parents=True, exist_ok=True)
    pa, pb = RECALLS / "raw_A.json", RECALLS / "raw_B.json"
    if args.offline:
        raw_a = json.loads(pa.read_text(encoding="utf-8"))
        raw_all_b = json.loads(pb.read_text(encoding="utf-8"))
    else:
        raw_a = fetch(args.since_a)
        raw_all_b = fetch(args.since_b)
    # Corpus B = children's subset of everything since since_b (raw_B.json keeps only that subset)
    raw_b = []
    for r in raw_all_b:
        rec = normalize(r, ["B"])
        if rec.is_childrens:
            raw_b.append(r)
    write_json(pa, raw_a)
    write_json(pb, raw_b)

    by_num: dict[str, RecallRecord] = {}
    for r in raw_a:
        rec = normalize(r, ["A"])
        by_num[rec.recall_number] = rec
    for r in raw_b:
        rec = normalize(r, ["B"])
        if rec.recall_number in by_num:
            if "B" not in by_num[rec.recall_number].corpus:
                by_num[rec.recall_number].corpus.append("B")
        else:
            by_num[rec.recall_number] = rec
    recs = sorted(by_num.values(), key=lambda x: (x.recall_date, x.recall_number), reverse=True)
    write_jsonl(RECALLS / "recalls.jsonl", [r.model_dump() for r in recs])
    stats = build_stats(recs, args.since_a, args.since_b)
    write_json(RECALLS / "stats.json", stats)
    tm = sum("™" in r.title or "™" in r.description for r in recs)
    print(f"A={stats['A']['recalls']} (childrens {stats['A']['childrens']}, with ids {stats['A']['with_regex_ids']})  "
          f"B={stats['B']['recalls']} (with ids {stats['B']['with_regex_ids']})  unique={len(recs)}  "
          f"records with ™ intact={tm}  mojibake={sum('â„¢' in r.description for r in recs)}")


if __name__ == "__main__":
    main()
