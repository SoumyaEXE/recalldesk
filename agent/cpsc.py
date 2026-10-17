"""CPSC Recalls REST API (no key) -> normalized RecallRecord dicts.

    fetch_raw(since)            live call, UTF-8 decoded explicitly (the API's ™/’ come back mangled otherwise)
    fetch_recalls(since, ...)   live -> snapshot ladder; every good response is cached to agent/cache/
    normalize(raw)              22-field CPSC record -> RecallRecord (same shape as data/recalls/recalls.jsonl)

If ml/ has written data/recalls/recalls.jsonl, `load_corpus()` prefers it (teacher pipeline is the source of
truth); otherwise it normalizes the committed CPSC snapshot in agent/cache/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from agent.config import CACHE_DIR, CORPUS_A_START, CPSC_BASE, DATA_DIR


class CpscHttpError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def snapshot_path(since: str) -> Path:
    return CACHE_DIR / f"cpsc_since_{since}.json"


def fetch_raw(since: str, timeout: float = 30.0) -> list[dict]:
    r = httpx.get(CPSC_BASE, params={"format": "json", "RecallDateStart": since}, timeout=timeout,
                  headers={"User-Agent": "RecallDesk/0.1 (hackathon; weekly recall check)"})
    if r.status_code >= 400:
        raise CpscHttpError(r.status_code, f"CPSC API HTTP {r.status_code}")
    data = json.loads(r.content.decode("utf-8"))
    if not isinstance(data, list):
        raise CpscHttpError(502, "CPSC API returned non-list JSON")
    snapshot_path(since).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def best_snapshot(since: str) -> tuple[list[dict], str] | None:
    """Exact snapshot for `since`, else the widest older snapshot filtered to >= since."""
    p = snapshot_path(since)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")), f"snapshot ({p.name})"
    cands = sorted(CACHE_DIR.glob("cpsc_since_*.json"))
    for c in cands:
        start = c.stem.removeprefix("cpsc_since_")
        if start <= since:
            rows = [r for r in json.loads(c.read_text(encoding="utf-8")) if (r.get("RecallDate") or "")[:10] >= since]
            return rows, f"snapshot ({c.name}, filtered >= {since})"
    return None


# ------------------------------------------------------------------------------------- normalize
_CHILD_TYPES = re.compile(
    r"bab|infant|toddler|child|kid|crib|bassinet|play ?yard|playpen|stroller|high ?chair|teeth|toy|rattle|"
    r"pacifier|bib|sleeper|walker|jumper|bouncer|swing|nursery|youth|car seat|carrier|lounger|tower stool|bath seat",
    re.I)
_ID_KEY = re.compile(
    r"(?:model|item|style|sku|lot|batch|ref|date code|serial|part|catalog|product)\s*"
    r"(?:numbers?|no\.?|#|code|ids?)?\s*[:#.]?\s*[\"“]?([A-Za-z0-9][A-Za-z0-9\-/.]{1,24}[A-Za-z0-9])", re.I)
_ID_SHAPE = re.compile(r"\b(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9][A-Z0-9-]{3,20}\b")
_UPC = re.compile(r"\b\d{12,13}\b")
_STOP_IDS = {"USB", "LED", "CPSC", "ASTM", "F2194", "F406", "F1169", "16CFR", "COVID-19", "AAA", "AA"}
_UNITISH = re.compile(r"\d+(?:W|V|MAH|BTU|IN|LB|LBS|MM|CM|PCS|PC|OZ|Y|M|T)|\d+-\d+(?:Y|M|T)")
_DATEISH = re.compile(r"^(?:19|20)\d\d(?:[-/]\d\d?)*$")


def extract_ids(text: str) -> list[str]:
    """Deterministic identifier extraction (model / item / lot / batch / UPC). A baseline AND a code-side check."""
    out: list[str] = []

    def add(tok: str):
        tok = tok.strip(" .,:;\"”’'()-/").upper()
        if re.fullmatch(r"[\d.]+", tok) and "." in tok or _UNITISH.fullmatch(tok):
            return
        if len(tok) < 3 or tok in _STOP_IDS or _DATEISH.match(tok) or not re.search(r"\d", tok):
            return
        if re.fullmatch(r"\d{1,3}", tok):
            return
        if tok not in out:
            out.append(tok)

    for m in _ID_KEY.finditer(text):
        add(m.group(1))
    for m in _ID_SHAPE.finditer(text):
        add(m.group(0))
    for m in _UPC.finditer(text):
        add(m.group(0))
    return out[:40]


def _names(xs) -> list[str]:
    return [str(x.get("Name") or "").strip() for x in (xs or []) if str(x.get("Name") or "").strip()]


def normalize(r: dict) -> dict:
    prods = r.get("Products") or []
    product_names = [p.get("Name", "").strip() for p in prods if p.get("Name")]
    types = " ".join(p.get("Type", "") or "" for p in prods)
    desc = (r.get("Description") or "").strip()
    title = (r.get("Title") or "").strip()
    remedies = _names(r.get("Remedies"))
    upcs = [str(u.get("UPC")).strip() for u in (r.get("ProductUPCs") or []) if u.get("UPC")]
    model_field = " ".join(p.get("Model", "") or "" for p in prods)
    text = f"{desc}\n{model_field}\n{' '.join(c.get('Caption', '') for c in r.get('Images') or [])}"
    rec = {
        "recall_number": str(r.get("RecallNumber") or "").strip(),
        "recall_id": r.get("RecallID"),
        "recall_date": (r.get("RecallDate") or "")[:10],
        "title": title,
        "description": desc,
        "url": r.get("URL") or "",
        "product_names": product_names,
        "units": next((p.get("NumberOfUnits") for p in prods if p.get("NumberOfUnits")), None),
        "hazards": _names(r.get("Hazards")),
        "remedies": remedies,
        "remedy_options": [x.get("Option") for x in (r.get("RemedyOptions") or []) if x.get("Option")],
        "retailers": _names(r.get("Retailers")),
        "manufacturers": _names(r.get("Manufacturers")),
        "importers": _names(r.get("Importers")),
        "images": [i.get("URL") for i in (r.get("Images") or []) if i.get("URL")],
        "upcs": upcs,
        "regex_ids": [i for i in extract_ids(text) if i not in upcs] + upcs,
        "is_childrens": bool(_CHILD_TYPES.search(types) or _CHILD_TYPES.search(" ".join(product_names))
                             or re.search(r"\bchild|\bbab(y|ies)|infant|toddler", title, re.I)),
        "corpus": ["A"] if (r.get("RecallDate") or "")[:10] >= CORPUS_A_START else [],
    }
    return rec


def load_corpus(since: str = CORPUS_A_START) -> tuple[list[dict], str]:
    """All known recalls since `since` as RecallRecord dicts + where they came from."""
    p = DATA_DIR / "recalls" / "recalls.jsonl"
    if p.exists():
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = [r for r in rows if r.get("recall_date", "") >= since]
        if rows:
            return rows, "data/recalls/recalls.jsonl"
    snap = best_snapshot(since)
    if snap:
        raw, src = snap
        return [normalize(r) for r in raw], src
    fx = Path(__file__).resolve().parent.parent / "shared" / "fixtures" / "recalls.json"
    if fx.exists():
        rows = json.loads(fx.read_text(encoding="utf-8"))
        return [r for r in rows if r.get("recall_date", "") >= since], "shared/fixtures/recalls.json"
    return [], "none"
