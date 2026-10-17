"""Collect every number the RecallDesk blog visuals use from the real result files.

Writes docs/visuals/data.js (window.RD = {...}). Nothing in the charts is typed by hand: re-run this after any
scan / re-train / re-eval, then re-render.

    python docs/visuals/build_data.py && python docs/visuals/render.py

Every section carries a `status`:
    real         the source file exists and is not marked placeholder
    provisional  eval.json exists but is scored against teacher labels, not human gold
    placeholder  the source file is missing or has "placeholder": true. The section is then filled with
                 ILLUSTRATIVE values from PLACEHOLDER below, and every page that uses it draws a
                 "PLACEHOLDER - NOT REAL DATA" watermark (common.js). Never quote a placeholder image.
Only the standard library is used (it runs with any Python 3.10+).
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "data.js"
RES = Path(os.environ["RECALLDESK_RESULTS"]) if os.environ.get("RECALLDESK_RESULTS") else ROOT / "ml" / "results"
LOGS = ROOT / "agent" / "demo_logs"

SOURCES: dict[str, dict] = {}
RISKY = ("match", "check")
LABELS = ["match", "check", "no_match"]
MODEL_KINDS = ("model", "item", "style", "sku", "part", "product_id", "ref")


def rel(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:  # RECALLDESK_RESULTS outside the repo (smoke tests)
        return p.as_posix()


def load_json(key: str, p: Path):
    """-> (obj | None, status). Records the source in SOURCES."""
    if not p.exists():
        SOURCES[key] = {"path": rel(p), "status": "placeholder", "why": "file missing"}
        return None, "placeholder"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        SOURCES[key] = {"path": rel(p), "status": "placeholder", "why": f"unreadable ({type(e).__name__})"}
        return None, "placeholder"
    if isinstance(obj, dict) and obj.get("placeholder"):
        SOURCES[key] = {"path": rel(p), "status": "placeholder", "why": '"placeholder": true'}
        return obj, "placeholder"
    SOURCES[key] = {"path": rel(p), "status": "real", "why": ""}
    return obj, "real"


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def frac(s) -> tuple[int, int]:
    """'12/30' -> (12, 30)."""
    try:
        a, b = str(s).split("/")
        return int(a), int(b)
    except Exception:  # noqa: BLE001
        return 0, 0


# ============================================================================ PLACEHOLDER values (illustrative)
# Round, obviously-fake numbers so a placeholder image is never mistaken for a result.
PLACEHOLDER = {
    "scan": {"recalls_scanned": 151, "searches_spent": 150, "listings_seen": 6000, "pairs_classified": 6000,
             "flagged_match": 100, "flagged_check": 300, "human_verified_match": 50, "human_reviewed_flags": 100,
             "childrens_flagged": 200, "childrens_recalls_with_flags": 20, "recalls_with_match": 30,
             "classifier": {"provider": "placeholder", "model": "placeholder"},
             "by_recall": [{"recall_number": "00000", "title": f"Placeholder recall {i + 1}", "listings": 50,
                            "match": 10 - i, "check": 20 - 2 * i, "is_childrens": i % 2 == 0} for i in range(6)]},
    "models": [
        {"role": "lora", "name": "Qwen3.5-4B + RecallDesk LoRA", "acc": 0.80, "acc_ci": [0.75, 0.85], "macro_f1": 0.75,
         "risky_caught": "90/100", "false_alarms": "20/100", "cost_per_1k_usd": 0.10, "p50_latency_ms": 2000},
        {"role": "teacher", "name": "Qwen3.5-397B-A17B (teacher)", "acc": 0.75, "acc_ci": [0.70, 0.80],
         "macro_f1": 0.70, "risky_caught": "85/100", "false_alarms": "20/100", "cost_per_1k_usd": 1.00,
         "p50_latency_ms": 2000},
        {"role": "base_guided", "name": "Qwen3.5-4B base + teacher's rulebook", "acc": 0.65, "acc_ci": [0.60, 0.70],
         "macro_f1": 0.60, "risky_caught": "70/100", "false_alarms": "25/100", "cost_per_1k_usd": 0.20,
         "p50_latency_ms": 2000},
        {"role": "base", "name": "Qwen3.5-4B base", "acc": 0.60, "acc_ci": [0.55, 0.65], "macro_f1": 0.55,
         "risky_caught": "60/100", "false_alarms": "25/100", "cost_per_1k_usd": 0.10, "p50_latency_ms": 2000},
        {"role": "heuristic", "name": "identifier/keyword rules (no model)", "acc": 0.50, "acc_ci": [0.45, 0.55],
         "macro_f1": 0.45, "risky_caught": "50/100", "false_alarms": "10/100", "cost_per_1k_usd": 0.0,
         "p50_latency_ms": 1},
    ],
    "confusion": {
        "base": {"labels": LABELS, "matrix": [[25, 15, 10], [10, 25, 15], [5, 20, 75]]},
        "lora": {"labels": LABELS, "matrix": [[40, 8, 2], [5, 40, 5], [5, 15, 80]]},
    },
    "paired": [{"a": "lora", "b": "base", "gain": 0.20, "ci": [0.10, 0.30], "only_a": 50, "only_b": 10, "p": 0.001}],
    "training": {"base_model": "Qwen/Qwen3.5-4B", "rank": 32, "steps": 60, "epochs": 3, "lr": 5e-4, "batch_size": 16,
                 "train_examples": 300, "wall_seconds": 300,
                 "loss_curve": [[s, round(0.9 * (0.985 ** s) + 0.15, 4)] for s in range(1, 61)],
                 "test_nll": [[0, 1.0], [20, 0.40], [40, 0.32], [60, 0.33]]},
    "spend": {"stages": {"spec_extract": {"est_usd": 0.60, "model": "Qwen/Qwen3.5-397B-A17B"},
                         "teacher_label": {"est_usd": 4.50, "model": "Qwen/Qwen3.5-397B-A17B"},
                         "train_tinker": {"est_usd": 1.50, "model": "Qwen/Qwen3.5-4B"},
                         "eval_base": {"est_usd": 0.05, "model": "Qwen/Qwen3.5-4B"},
                         "eval_lora": {"est_usd": 0.05, "model": "Qwen/Qwen3.5-4B"},
                         "serp_scan": {"est_usd": 0.0, "searches_spent": 150}},
              "total": 6.70, "serpapi_searches_spent": 150},
    "example": {"pair_id": "placeholder", "recall_number": "26658",
                "recall_title": "Woodure Toddler Kitchen Step Stools Recalled Due to Risk of Serious Injury and Death "
                                "from Entrapment and Fall Hazards",
                "listing_title": "PLACEHOLDER listing: Woodure kids kitchen helper tower, natural wood",
                "gold": "check", "base": "no_match", "lora": "check",
                "base_verdict": {"verdict": "no_match", "identifiers_found": [], "conflicts": [],
                                 "reason": "PLACEHOLDER: no model number in the title."},
                "lora_verdict": {"verdict": "check", "identifiers_found": [], "conflicts": [],
                                 "reason": "PLACEHOLDER: same Woodure tower line; model no. (WD1764/WD1357/WD1720) "
                                           "is engraved under the bottom step."}},
}


# ============================================================================ corpus (CPSC, always real)
def build_corpus() -> dict:
    stats, st = load_json("stats", ROOT / "data" / "recalls" / "stats.json")
    recs = read_jsonl(ROOT / "data" / "recalls" / "recalls.jsonl")
    SOURCES["recalls"] = {"path": "data/recalls/recalls.jsonl", "status": "real" if recs else "placeholder",
                          "why": "" if recs else "file missing"}
    since = (stats or {}).get("since_a", "2026-07-18")
    A = [r for r in recs if "A" in (r.get("corpus") or [])]
    try:  # same typed extraction ml/heuristic.py uses
        import sys
        sys.path.insert(0, str(ROOT))
        from ml.regex_ids import extract_ids_typed, norm_id  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        extract_ids_typed = None

        def norm_id(s):
            return re.sub(r"[^a-z0-9]", "", s.lower())

    by_day: dict[str, dict] = defaultdict(lambda: {"n": 0, "childrens": 0})
    with_model = buried = with_any = words = 0
    for r in A:
        d = by_day[r["recall_date"]]
        d["n"] += 1
        d["childrens"] += bool(r.get("is_childrens"))
        words += len((r.get("description") or "").split())
        if r.get("regex_ids"):
            with_any += 1
        if extract_ids_typed:
            typed = extract_ids_typed(r.get("description") or "", r.get("upcs") or [])
            ms = [x["id"] for x in typed if not x["excluded"] and x["kind"] in MODEL_KINDS]
        else:
            ms = r.get("regex_ids") or []
        if ms:
            with_model += 1
            hay = norm_id((r.get("title") or "") + " " + " ".join(r.get("product_names") or []))
            if not any(norm_id(m) in hay for m in ms):
                buried += 1
    days = sorted(by_day)
    weekdays = Counter(date.fromisoformat(d).strftime("%A") for d in days)
    n = len(A)
    return {
        "status": "real" if recs else "placeholder",
        "since": since, "recalls": n, "childrens": sum(bool(r.get("is_childrens")) for r in A),
        "by_day": [{"date": d, **by_day[d]} for d in days],
        "weekday": weekdays.most_common(1)[0][0] if weekdays else "Thursday",
        "all_same_weekday": len(weekdays) == 1,
        "with_any_id": with_any, "with_model_ids": with_model, "buried": buried,
        "buried_pct": round(100 * buried / n, 1) if n else 0,
        "description_words": words,
        "corpus_b": (stats or {}).get("B", {}).get("recalls"), "total_unique": (stats or {}).get("total_unique"),
        "sold_online": (stats or {}).get("A", {}).get("sold_online"),
        "retailers": (stats or {}).get("A", {}).get("retailers_mentioning", {}),
        "definition": "buried = the recall's model/item/style/SKU/part number appears in the description but not in "
                      "the title or product name (ml.regex_ids typed extraction, exclusions dropped)",
    }


# ============================================================================ scan
def build_scan() -> dict:
    sc, st = load_json("scan_summary", RES / "scan_summary.json")
    if st != "real":
        d = dict(PLACEHOLDER["scan"])
    else:
        d = {k: v for k, v in sc.items() if k != "by_recall"}
        d["by_recall"] = sc.get("by_recall", [])
    top = sorted(d["by_recall"], key=lambda b: (-(b.get("match", 0) + b.get("check", 0)), b.get("recall_number", "")))
    d["top"] = [{k: b.get(k) for k in ("recall_number", "title", "listings", "match", "check", "is_childrens")}
                for b in top[:6] if (b.get("match", 0) + b.get("check", 0)) > 0]
    d.pop("by_recall", None)
    d["status"] = st
    return d


# ============================================================================ eval + training
def build_eval() -> dict:
    ev, st = load_json("eval", RES / "eval.json")
    if st == "real" and ev and "teacher" in str(ev.get("gold", "")).lower():
        st = "provisional"
        SOURCES["eval"]["status"] = "provisional"
        SOURCES["eval"]["why"] = f'gold = {ev.get("gold")}'
    usable = st != "placeholder" and ev and any(m.get("acc") is not None and not m.get("pending")
                                                for m in ev.get("models", []))
    if not usable:
        if st != "placeholder":
            SOURCES["eval"].update(status="placeholder", why="no scored models yet")
        st = "placeholder"
        models = PLACEHOLDER["models"]
        confusion, paired, examples = PLACEHOLDER["confusion"], PLACEHOLDER["paired"], [PLACEHOLDER["example"]]
        test_size, gold = 220, "placeholder"
    else:
        models = [m for m in ev["models"] if m.get("acc") is not None and not m.get("pending")]
        confusion, paired = ev.get("confusion", {}), ev.get("paired", [])
        examples, test_size, gold = ev.get("examples") or [], ev.get("test_size"), ev.get("gold")
    by_role = {m["role"]: m for m in models}
    risky = {}
    for role, cm in confusion.items():
        mat = cm.get("matrix") or []
        if len(mat) == 3:
            # rows = gold (match, check, no_match); cols = predicted
            risky[role] = {"gold_match": sum(mat[0]), "gold_check": sum(mat[1]),
                           "match_caught": mat[0][0] + mat[0][1], "check_caught": mat[1][0] + mat[1][1],
                           "match_as_match": mat[0][0], "match_as_check": mat[0][1],
                           "check_as_match": mat[1][0], "check_as_check": mat[1][1]}
    ex = None
    for e in examples:  # first example the LoRA fixed (pick_examples sorts those first)
        if e.get("base_verdict") and e.get("lora_verdict"):
            ex = e
            break
    ex_status = st
    if ex is None:
        ex, ex_status = PLACEHOLDER["example"], "placeholder"
    return {"status": st, "test_size": test_size, "gold": gold,
            "test_recalls": (ev or {}).get("test_recalls"), "gold_dist": (ev or {}).get("gold_dist"),
            "models": {r: {k: m.get(k) for k in ("name", "role", "model", "n", "acc", "acc_ci", "macro_f1",
                                                 "risky_caught", "false_alarms", "json_valid", "p50_latency_ms",
                                                 "cost_per_1k_usd", "childrens_acc")} for r, m in by_role.items()},
            "order": [m["role"] for m in models], "paired": paired, "confusion": confusion, "risky": risky,
            "example": {**ex, "status": ex_status}}


def build_training(eval_training: dict | None) -> dict:
    tl, st = load_json("training", RES / "training.json")
    if st != "real" or not (tl or {}).get("loss_curve"):
        if eval_training and eval_training.get("loss_curve"):
            tl, st = eval_training, "real"
            SOURCES["training"] = {"path": "ml/results/eval.json#training", "status": "real", "why": ""}
        else:
            if st == "real":
                SOURCES["training"].update(status="placeholder", why="no loss_curve yet")
            tl, st = PLACEHOLDER["training"], "placeholder"
    keys = ("base_model", "rank", "steps", "epochs", "lr", "batch_size", "train_examples", "heldout_examples",
            "wall_seconds", "loss_curve", "test_nll", "label_source")
    return {"status": st, **{k: tl.get(k) for k in keys}}


def build_spend() -> dict:
    sp, st = load_json("spend", RES / "spend.json")
    if st != "real" or not (sp or {}).get("stages"):
        if st == "real":
            SOURCES["spend"].update(status="placeholder", why="no stages yet")
        sp, st = PLACEHOLDER["spend"], "placeholder"
        return {"status": st, "stages": sp["stages"], "total": sp["total"],
                "searches": sp["serpapi_searches_spent"], "note": "placeholder"}
    return {"status": st, "stages": sp["stages"], "total": sp.get("total_est_usd", 0),
            "searches": sp.get("serpapi_searches_spent", 0), "note": sp.get("note", "")}


# ============================================================================ crash / resume transcript
def secs(ts: str) -> float:
    t = datetime.strptime(ts, "%H:%M:%S.%f")
    return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6


def build_crash() -> dict:
    p = LOGS / "04_crash_resume.txt"
    if not p.exists():
        SOURCES["crash"] = {"path": rel(p), "status": "placeholder", "why": "file missing"}
        return {"status": "placeholder"}
    SOURCES["crash"] = {"path": rel(p), "status": "real", "why": ""}
    log = p.read_text(encoding="utf-8")

    def g(pat, cast=str, default=None, flags=0):
        m = re.search(pat, log, flags)
        return cast(m.group(1)) if m else default

    demo = [(float(t), m.strip()) for t, m in re.findall(r"\[demo t\+\s*([\d.]+)s\]\s*(.*)", log)]
    wl = [(int(w), ts, m.strip()) for w, ts, m in re.findall(r"worker#(\d) \| (\d\d:\d\d:\d\d\.\d+) \[worker\] (.*)", log)]

    def demo_t(pat):
        return next((t for t, m in demo if re.search(pat, m)), None)

    t_wf = demo_t(r"started InventoryCheckWorkflow")
    # Align worker wall clock to the demo t+ clock: the workflow starts at t_wf and worker #1 logs its first
    # activity (load_inventory) at once.
    first = next((secs(ts) for w, ts, m in wl if m.startswith("[load_")), None)
    off = (first - t_wf) if (first is not None and t_wf is not None) else 0.0
    events = []
    for w, ts, m in wl:
        e = {"w": w, "clock": ts, "t": round(secs(ts) - off, 2), "msg": m}
        cm = re.match(r"\[check_item\] #(\d+) (.*?) -> (\S+)(?: \(attempt (\d+)\))?$", m)
        if cm:
            v = cm.group(3)
            e.update(kind="check_item", idx=int(cm.group(1)), item=cm.group(2),
                     verdict=v.split(":")[-1] if ":" in v else v, recall=v.split(":")[0] if ":" in v else None,
                     attempt=int(cm.group(4) or 1))
        else:
            km = re.match(r"\[(\w+)\]", m)
            e["kind"] = km.group(1) if km else ("up" if "worker pid=" in m else "other")
        events.append(e)
    return {
        "status": "real",
        "workflow_id": g(r"started InventoryCheckWorkflow id=(\S+)"),
        "shop": g(r"started InventoryCheckWorkflow id=\S+ shop=(\S+)"),
        "model": g(r"\] model: (.*)"),
        "items": g(r"\[load_inventory\] shop=\S+: (\d+) items", int),
        "pairs": g(r"-> (\d+) \(item, recall\) pairs", int),
        "worker1_pid": g(r"worker#1 \| \S+ \[worker\] worker pid=(\d+)", int),
        "worker2_pid": g(r"worker#2 \| \S+ \[worker\] worker pid=(\d+)", int),
        "t_worker1_start": demo_t(r"starting worker #1"), "t_wf_start": t_wf,
        "t_kill": demo_t(r"\[CRASH\]"), "t_dead": demo_t(r"worker #1 is dead"),
        "t_worker2_start": demo_t(r"starting worker #2"), "t_done": demo_t(r"workflow COMPLETED"),
        "progress_at_kill": g(r"check_items\s+running\s+attempt=1\s+(\d+/\d+) items"),
        "in_flight": g(r"(\d+) check_item activities in flight", int),
        "history_len_at_crash": g(r"history length=(\d+)", int),
        "downtime_s": g(r"waiting ([\d.]+)s of downtime", float),
        "heartbeat_s": g(r"(\d+)s heartbeat timeout", int),
        "scheduled": g(r"check_item activities scheduled\s*: (\d+)", int),
        "kept": g(r"completed before the crash\s*: (\d+)", int),
        "after_restart": g(r"completed after restart\s*: (\d+)", int),
        "twice": g(r"activities completed twice\s*: (\d+)", int),
        "retried": g(r"attempts >= 2 \(retried\)\s*: (\d+)", int),
        "history_events": g(r"total history events\s*: (\d+)", int),
        "card_line": g(r"\[compose_card\] (.*)"),
        "result": g(r"RESULT: (.*)"),
        "workers": g(r"workers that touched this run: (\[.*?\])"),
        "events": events,
        "anchor_note": f"worker clock aligned to the demo clock at workflow start (first activity = t+{t_wf}s)",
    }


# ============================================================================ memory loop
def load_card(wf: str) -> dict | None:
    p = ROOT / "agent" / "cards" / f"{wf}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def card_rows(card: dict, rn: str) -> list[dict]:
    out = []
    for kind in ("do_not_sell", "check_label"):
        for r in card.get(kind) or []:
            if r.get("recall_number") == rn:
                out.append({**r, "kind": kind})
    return out


def build_memory() -> dict:
    """Correction -> memory -> next run's verdict changes, from the dev-stack transcript + the published cards."""
    best = None
    for p in sorted(LOGS.glob("*.txt")):
        txt = p.read_text(encoding="utf-8", errors="replace")
        adds = list(re.finditer(r"(\d\d:\d\d:\d\d\.\d+) \[api\] memory (\S+) added for (\S+) \((.*?)\): recall (\S+) -> (\w+)", txt))
        if not adds:
            continue
        pubs = [(m.start(), m.group(1), m.group(2)) for m in
                re.finditer(r"(\d\d:\d\d:\d\d\.\d+) \[worker\] \[publish_card\] wrote agent/cards/(\S+)\.json", txt)]
        for a in adds:
            mem_id, shop, backend, rn, verdict = a.group(2), a.group(3), a.group(4), a.group(5), a.group(6)
            before = after = None
            for pos, clock, wf in pubs:
                c = load_card(wf)
                if not c or c.get("shop_id") != shop:
                    continue
                applied = [m for m in c.get("applied_memories") or [] if m.get("memory_id") == mem_id]
                if applied and after is None:
                    after = (wf, clock, c, applied[0])
                elif not applied and after is None and card_rows(c, rn):
                    before = (wf, clock, c)
            if before and after:
                best = (p, a, mem_id, shop, backend, rn, verdict, before, after)
    if not best:
        SOURCES["memory"] = {"path": "agent/demo_logs/*.txt + agent/cards/", "status": "placeholder",
                             "why": "no correction -> next-run pair found"}
        return {"status": "placeholder"}
    p, a, mem_id, shop, backend, rn, verdict, before, after = best
    SOURCES["memory"] = {"path": f"{rel(p)} + agent/cards/{before[0]}.json + agent/cards/{after[0]}.json",
                         "status": "real", "why": ""}
    # the correction request/response (05_api_endpoints.txt) gives the shop's own words
    note = item = None
    api = LOGS / "05_api_endpoints.txt"
    if api.exists():
        t = api.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"/corrections .*?-d (\{.*?\})\s*\n(\{.*?\})\s*\n", t)
        if m:
            try:
                req, resp = json.loads(m.group(1)), json.loads(m.group(2))
                if resp.get("memory_id") == mem_id:
                    note, item = req.get("note"), req.get("listing_or_item")
            except json.JSONDecodeError:
                pass
    bc, ac, applied = before[2], after[2], after[3]
    txt = p.read_text(encoding="utf-8", errors="replace")

    def times(wf: str) -> dict:
        m = re.search(r"(\d\d:\d\d:\d\d\.\d+) \[api\] started InventoryCheckWorkflow " + re.escape(wf), txt)
        if not m:
            return {}
        lm = re.compile(r"(\d\d:\d\d:\d\d\.\d+) \[worker\] \[load_shop_memories\] shop=" + re.escape(shop) + r"[ :]")
        l2 = lm.search(txt, m.end())
        return {"started": m.group(1), "memories_loaded": l2.group(1) if l2 else None}
    return {
        "status": "real", "transcript": rel(p), "memory_id": mem_id, "shop_id": shop,
        "shop_name": ac.get("shop_name"), "backend": backend, "recall_number": rn, "correct_verdict": verdict,
        "item": item or applied.get("item"), "note": note, "memory_text": applied.get("text"),
        "added_at": a.group(1),
        "before": {"workflow_id": before[0], "published": before[1], **times(before[0]), "rows": card_rows(bc, rn),
                   "do_not_sell": len(bc.get("do_not_sell") or []), "check_label": len(bc.get("check_label") or []),
                   "memories_applied": len(bc.get("applied_memories") or []), "model": bc.get("model")},
        "after": {"workflow_id": after[0], "published": after[1], **times(after[0]), "rows": card_rows(ac, rn),
                  "do_not_sell": len(ac.get("do_not_sell") or []), "check_label": len(ac.get("check_label") or []),
                  "memories_applied": len(ac.get("applied_memories") or []), "model_verdict": applied.get("model_verdict"),
                  "applied_verdict": applied.get("applied_verdict"), "model": ac.get("model")},
        "uses_backboard": "local" not in backend.lower(),
    }


# ============================================================================ the printed card (cover)
def build_card() -> dict:
    for p in (ROOT / "agent" / "cards" / "latest_little-loop.json", ROOT / "shared" / "fixtures" / "card_little-loop.json"):
        if p.exists():
            c = json.loads(p.read_text(encoding="utf-8"))
            SOURCES["card"] = {"path": rel(p), "status": "placeholder" if c.get("placeholder") else "real", "why": ""}
            return {"status": SOURCES["card"]["status"], **{k: c.get(k) for k in (
                "id", "week_of", "shop_name", "new_recalls", "items_checked", "do_not_sell", "check_label",
                "applied_memories", "workflow_id", "model")}}
    SOURCES["card"] = {"path": "agent/cards/latest_little-loop.json", "status": "placeholder", "why": "file missing"}
    return {"status": "placeholder", "do_not_sell": [], "check_label": []}


def main() -> None:
    corpus = build_corpus()
    ev_raw, _ = (json.loads((RES / "eval.json").read_text(encoding="utf-8")), None) if (RES / "eval.json").exists() else (None, None)
    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "corpus": corpus, "scan": build_scan(), "eval": build_eval(),
        "training": build_training((ev_raw or {}).get("training") if not (ev_raw or {}).get("placeholder") else None),
        "spend": build_spend(), "crash": build_crash(), "memory": build_memory(), "card": build_card(),
    }
    data["sources"] = SOURCES
    OUT.write_text("// generated by docs/visuals/build_data.py from ml/results, data/recalls, agent/demo_logs, "
                   "agent/cards; do not edit\nwindow.RD = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
                   encoding="utf-8")
    print("wrote", rel(OUT))
    for k, s in SOURCES.items():
        print(f"  {k:13s} {s['status']:12s} {s['path']}" + (f"  ({s['why']})" if s["why"] else ""))
    c = corpus
    print(f"  corpus: {c['recalls']} recalls since {c['since']}, {c['childrens']} children's, {len(c['by_day'])} "
          f"{c['weekday']}s; {c['with_model_ids']} with model-type ids, {c['buried']} buried ({c['buried_pct']}%)")


if __name__ == "__main__":
    main()
