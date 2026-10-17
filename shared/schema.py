"""RecallDesk canonical shapes (source of truth; web/lib/types.ts mirrors this).

Pure pydantic + stdlib: safe to import anywhere (no keys, no network, no heavy deps).

    from shared.schema import RecallRecord, RecallSpec, Listing, MatchVerdict, RecallCard, parse_verdict
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Verdict = Literal["match", "check", "no_match"]
VERDICTS: tuple[str, ...] = ("match", "check", "no_match")
CARD_ACTION = {"match": "DO NOT SELL", "check": "CHECK LABEL", "no_match": None}


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------------------- RecallRecord
class RecallRecord(_Base):
    """Normalized CPSC recall (data/recalls/recalls.jsonl)."""

    recall_number: str
    recall_id: Optional[int] = None
    recall_date: str  # YYYY-MM-DD
    title: str
    description: str = ""
    url: str = ""
    product_names: list[str] = Field(default_factory=list)
    units: Optional[str] = None
    hazards: list[str] = Field(default_factory=list)
    remedies: list[str] = Field(default_factory=list)
    remedy_options: list[str] = Field(default_factory=list)
    retailers: list[str] = Field(default_factory=list)
    manufacturers: list[str] = Field(default_factory=list)
    importers: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    upcs: list[str] = Field(default_factory=list)
    regex_ids: list[str] = Field(default_factory=list)
    is_childrens: bool = False
    corpus: list[str] = Field(default_factory=list)  # "A" (since 2026-07-18) and/or "B" (children's since 2023)


# ----------------------------------------------------------------------------------- RecallSpec
class RecallSpec(_Base):
    """Identification spec extracted once per recall (data/specs/specs.jsonl)."""

    recall_number: str
    brand: str = ""
    product_type: str = ""
    product_name: str = ""
    model_numbers: list[str] = Field(default_factory=list)
    upcs: list[str] = Field(default_factory=list)
    other_identifiers: list[str] = Field(default_factory=list)  # lot / batch / date codes / SKUs / serial ranges
    sold_from: Optional[str] = None  # YYYY-MM
    sold_to: Optional[str] = None
    colors: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    not_included: list[str] = Field(default_factory=list)  # models / variants the recall explicitly excludes
    search_queries: list[str] = Field(default_factory=list)
    is_childrens: bool = False
    hazard_short: str = ""
    remedy_short: str = ""

    @field_validator("model_numbers", "upcs", "other_identifiers", "colors", "key_features", "not_included",
                     "search_queries", mode="before")
    @classmethod
    def _listify(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return [str(x) for x in v if x is not None and str(x).strip()]


# -------------------------------------------------------------------------------------- Listing
class Listing(_Base):
    """An eBay listing (via SerpApi) or an inventory row (data/listings/listings.jsonl)."""

    listing_id: str  # "ebay:<item id>" or "inv:<shop>:<n>"
    source: Literal["ebay", "inventory"] = "ebay"
    title: str
    subtitle: Optional[str] = None
    condition: Optional[str] = None
    price: Optional[str] = None
    link: Optional[str] = None
    thumbnail: Optional[str] = None
    seller_hash: Optional[str] = None  # "s_" + sha1(username)[:6]; never the raw username
    item_specifics: dict[str, Any] = Field(default_factory=dict)
    query: Optional[str] = None
    recall_number: Optional[str] = None  # the recall whose search found it (None for inventory)
    fetched_at: Optional[str] = None


# --------------------------------------------------------------------------------- MatchVerdict
class MatchVerdict(_Base):
    """The model's ONLY output (strict JSON)."""

    verdict: Verdict
    identifiers_found: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    reason: str = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _norm_verdict(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip().lower().replace("-", "_").replace(" ", "_")
            return {"nomatch": "no_match", "no": "no_match", "none": "no_match"}.get(s, s)
        return v

    @field_validator("identifiers_found", "conflicts", mode="before")
    @classmethod
    def _listify(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return [str(x) for x in v]


# ----------------------------------------------------------------------------------- RecallCard
class DoNotSellItem(_Base):
    item: str
    recall_number: str
    recall_title: str = ""
    why: str = ""
    remedy: str = ""


class CheckLabelItem(_Base):
    item: str
    recall_number: str
    look_for: str = ""


class AppliedMemory(_Base):
    memory_id: str
    text: str = ""


class RecallCard(_Base):
    """The one thing the shop prints."""

    id: str
    week_of: str
    shop_id: str
    shop_name: str = ""
    new_recalls: int = 0
    items_checked: int = 0
    do_not_sell: list[DoNotSellItem] = Field(default_factory=list)
    check_label: list[CheckLabelItem] = Field(default_factory=list)
    applied_memories: list[AppliedMemory] = Field(default_factory=list)
    workflow_id: str = ""
    model: str = ""
    generated_at: str = ""


# ------------------------------------------------------------------------------ JSON parsing
M = TypeVar("M", bound=BaseModel)

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)


def extract_json_object(text: Optional[str]) -> Optional[dict]:
    """Best-effort: strip <think> blocks and ``` fences, return the first balanced {...} that parses."""
    if not text:
        return None
    t = _THINK.sub("", text).strip()
    m = _FENCE.search(t)
    if m:
        t = m.group(1).strip()
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(t[start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
        start = t.find("{", start + 1)
    return None


def parse_model_json(text: Optional[str], model: type[M]) -> tuple[Optional[M], Optional[str]]:
    """Parse model text into `model`. Returns (obj, error)."""
    if not text or not text.strip():
        return None, "empty"
    obj = extract_json_object(text)
    if obj is None:
        return None, "no_json_object"
    try:
        return model.model_validate(obj), None
    except ValidationError as e:
        return None, "schema_error: " + "; ".join(
            f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:3])


def parse_verdict(text: Optional[str]) -> tuple[Optional[MatchVerdict], Optional[str]]:
    return parse_model_json(text, MatchVerdict)


def parse_spec(text: Optional[str], recall_number: str) -> tuple[Optional[RecallSpec], Optional[str]]:
    obj = extract_json_object(text)
    if obj is None:
        return None, "no_json_object" if text else "empty"
    obj["recall_number"] = recall_number  # never trust the model for the key
    try:
        return RecallSpec.model_validate(obj), None
    except ValidationError as e:
        return None, "schema_error: " + "; ".join(
            f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:3])


def verdict_json(v: MatchVerdict) -> str:
    """Canonical compact JSON (stable key order) used as the SFT target."""
    return json.dumps(v.model_dump(), ensure_ascii=False, separators=(", ", ": "))


__all__ = [
    "VERDICTS", "Verdict", "CARD_ACTION", "RecallRecord", "RecallSpec", "Listing", "MatchVerdict", "RecallCard",
    "DoNotSellItem", "CheckLabelItem", "AppliedMemory", "extract_json_object", "parse_model_json", "parse_verdict",
    "parse_spec", "verdict_json",
]
