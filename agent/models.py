"""Activity / workflow I/O types (pydantic, serialized by temporalio.contrib.pydantic)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from shared.schema import MatchVerdict, RecallSpec

StepStatus = Literal["pending", "running", "retrying", "completed", "failed", "skipped"]


class Item(BaseModel):
    """An inventory row as POSTed to /api/check."""
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    notes: Optional[str] = None


class CandidateSpec(BaseModel):
    spec: RecallSpec
    title: str = ""
    recall_date: str = ""
    label_hint: str = ""     # where the deciding identifier lives, from the CPSC description
    url: str = ""


class SpecSet(BaseModel):
    """Recalls a check runs against. `specs` is only filled for small sets (the weekly sweep's new recalls);
    on-demand checks keep the full corpus on disk and pass `corpus` instead (keeps event history small)."""
    corpus: str = "A"
    specs: list[CandidateSpec] = Field(default_factory=list)
    count: int = 0
    new_recalls: int = 0
    week_of: str = ""
    source: str = ""
    attempt: int = 1


class FetchResult(BaseModel):
    since: str
    recalls: list[dict[str, Any]]
    source: str               # cpsc-live | snapshot (...)
    attempt: int = 1


class SpecResult(BaseModel):
    candidate: CandidateSpec
    source: str
    attempt: int = 1


class MemoryHit(BaseModel):
    memory_id: str
    text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None
    backend: str = ""


class MemoryInput(BaseModel):
    shop_id: str
    items: list[Item]


class MemorySet(BaseModel):
    by_item: dict[str, list[MemoryHit]] = Field(default_factory=dict)  # str(index) -> hits
    backend: str = ""
    total: int = 0
    attempt: int = 1


class RetrieveInput(BaseModel):
    items: list[Item]
    spec_set: SpecSet
    k: int = 3


class Candidates(BaseModel):
    per_item: list[list[CandidateSpec]]
    source: str = ""


class CheckItemInput(BaseModel):
    workflow_id: str
    shop_id: str
    index: int
    item: Item
    candidates: list[CandidateSpec]
    memories: list[MemoryHit] = Field(default_factory=list)


class PairResult(BaseModel):
    recall_number: str
    recall_title: str = ""
    verdict: MatchVerdict
    model_verdict: Optional[str] = None      # before memory overrides / code guards
    source: str = "model"                     # model | heuristic | heuristic-fallback | memory-override | code-guard
    model: str = ""
    guard: Optional[str] = None
    applied_memory: Optional[MemoryHit] = None
    look_for: str = ""
    why: str = ""
    remedy: str = ""


class ItemResult(BaseModel):
    index: int
    item: Item
    pairs: list[PairResult] = Field(default_factory=list)
    attempt: int = 1
    fallback: bool = False
    latency_ms: int = 0
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class StoreScanInput(BaseModel):
    shop_id: str
    spec_set: SpecSet


class StoreListingHit(BaseModel):
    title: str
    link: Optional[str] = None
    price: Optional[str] = None
    pair: PairResult


class StoreScan(BaseModel):
    source: str
    listings_seen: int = 0
    searches_spent: int = 0
    flagged: list[StoreListingHit] = Field(default_factory=list)
    skipped: bool = False
    attempt: int = 1


class ComposeInput(BaseModel):
    shop_id: str
    shop_name: str
    week_of: str
    new_recalls: int
    results: list[ItemResult]
    store: Optional[StoreScan] = None
    workflow_id: str
    generated_at: str
    model: str
    notes: list[str] = Field(default_factory=list)
    memory_backend: str = ""


class PublishResult(BaseModel):
    card_id: str
    path: str
    attempt: int = 1


class CheckInput(BaseModel):
    shop_id: str
    items: list[Item] = Field(default_factory=list)   # empty -> shop's inventory CSV
    corpus: Optional[str] = None                       # "A" (since 2026-07-18) | "AB" (+ children's since 2023)
    spec_set: Optional[SpecSet] = None                 # set by WeeklyRecallSweep (this week's new recalls)


class SweepInput(BaseModel):
    since: Optional[str] = None       # default: 7 days before the run
    shops: list[str] = Field(default_factory=list)   # default: every watched shop in agent/shops.json


class Step(BaseModel):
    name: str
    status: StepStatus = "pending"
    attempt: int = 0
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error: Optional[str] = None
    note: Optional[str] = None


class Progress(BaseModel):
    workflow_id: str
    workflow_type: str
    shop_id: Optional[str] = None
    status: str = "running"
    started_at: str
    steps: list[Step] = Field(default_factory=list)
    card: Optional[dict[str, Any]] = None
    children: list[str] = Field(default_factory=list)
