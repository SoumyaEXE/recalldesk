"""Evaluate every classifier on the held-out TEST pairs against blind HUMAN gold labels.

    python -m ml.eval                              # all roles that can run (Tinker roles need TINKER_API_KEY)
    python -m ml.eval --roles heuristic            # free, no key
    python -m ml.eval --roles base,base_guided     # baselines before training
    python -m ml.eval --roles lora                 # after ml.train_tinker (reads ml/results/model_path.txt)
    python -m ml.eval --rebuild-only               # just rebuild eval.json from cached preds
    python -m ml.eval --gold teacher               # PROVISIONAL: score vs teacher labels before humans are done

Roles: heuristic (rules) | base (Qwen3.5-4B, short student prompt) | base_guided (4B + the teacher's long
rulebook) | lora (4B + RecallDesk LoRA, short prompt) | teacher (Qwen3.5-397B-A17B, long prompt + CPSC text;
reuses data/labeled/teacher.jsonl for test pairs unless --rerun-teacher) | backboard:<model> (from
ml/backboard_baselines.py -> ml/results/preds/backboard_<slug>.jsonl).
Single attempt, temperature 0, no retries for scored roles (invalid JSON = wrong). Stats: 10,000-sample bootstrap
CIs; paired comparisons = exact two-sided McNemar (binomial on discordant pairs) + paired bootstrap CI of the gain.
Writes ml/results/eval.json, ml/results/predictions.jsonl, ml/results/preds/<role>.jsonl.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from collections import Counter

from ml.common import (GOLD, LABELED, RESULTS, SPLITS, STUDENT_MODEL, TEACHER_MODEL, add_spend, load_env, load_listings,
                       load_recalls, load_specs, make_renderer, now_iso, percentile, read_jsonl, sample_cost_usd,
                       tinker_model_path, utf8_stdout, write_json, write_jsonl)
from ml.prompts import guided_messages, student_messages, teacher_messages

PREDS = RESULTS / "preds"
LABELS = ["match", "check", "no_match"]
RISKY = {"match", "check"}
SEED = 0
N_BOOT = 10_000


def short(m: str) -> str:
    return m.split("/")[-1]


ROLE_INFO = {
    "teacher": {"name": f"{short(TEACHER_MODEL)} (teacher)", "model": TEACHER_MODEL, "prompt": "teacher"},
    "base": {"name": f"{short(STUDENT_MODEL)} base", "model": STUDENT_MODEL, "prompt": "student"},
    "base_guided": {"name": f"{short(STUDENT_MODEL)} base + teacher's rulebook", "model": STUDENT_MODEL,
                    "prompt": "guided"},
    "lora": {"name": f"{short(STUDENT_MODEL)} + RecallDesk LoRA", "model": STUDENT_MODEL, "prompt": "student"},
    "heuristic": {"name": "identifier/keyword rules (no model)", "model": "heuristic", "prompt": None},
}
ORDER = ["teacher", "base", "base_guided", "lora", "heuristic"]
PAIRED = [("lora", "base"), ("lora", "base_guided"), ("lora", "teacher"), ("lora", "heuristic"),
          ("base_guided", "base"), ("teacher", "heuristic")]


# ------------------------------------------------------------------------------------- data
def load_test(gold_src: str) -> tuple[list[dict], dict[str, str], dict]:
    test = read_jsonl(SPLITS / "test.jsonl")
    if not test:
        raise SystemExit("data/splits/test.jsonl missing - run: python -m ml.make_pairs")
    if gold_src == "human":
        gold = {}
        for r in read_jsonl(GOLD / "labels.jsonl"):
            gold[r["pair_id"]] = r["label"]  # newest row wins
    else:
        gold = {r["pair_id"]: r["verdict"]["verdict"] for r in read_jsonl(LABELED / "teacher.jsonl") if r.get("valid")}
    rows = [t for t in test if t["pair_id"] in gold]
    if not rows:
        raise SystemExit("no gold labels for test pairs yet - label with: python -m ml.label_ui "
                         "(or pass --gold teacher for a PROVISIONAL score)")
    ctx = {"recalls": {r["recall_number"]: r for r in load_recalls("AB")}, "specs": load_specs(),
           "listings": load_listings()}
    return rows, gold, ctx


def messages_for(role_prompt: str, row: dict, ctx: dict) -> list[dict]:
    spec, lst = ctx["specs"][row["recall_number"]], ctx["listings"][row["listing_id"]]
    if role_prompt == "student":
        return student_messages(spec, lst)
    if role_prompt == "guided":
        return guided_messages(spec, lst)
    return teacher_messages(spec, lst, ctx["recalls"].get(row["recall_number"]))


# ------------------------------------------------------------------------------------- running
def run_heuristic(rows: list[dict], ctx: dict) -> list[dict]:
    from ml.heuristic import classify_heuristic

    out = []
    for r in rows:
        t0 = time.perf_counter()
        v = classify_heuristic(ctx["specs"][r["recall_number"]], ctx["listings"][r["listing_id"]])
        out.append({"pair_id": r["pair_id"], "verdict": v.model_dump(), "valid": True,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 4), "tokens_in": 0, "tokens_out": 0,
                    "error": None, "output_text": json.dumps(v.model_dump(), ensure_ascii=False)})
    return out


def reuse_teacher(rows: list[dict]) -> list[dict]:
    lab = {r["pair_id"]: r for r in read_jsonl(LABELED / "teacher.jsonl")}
    out = []
    for r in rows:
        t = lab.get(r["pair_id"])
        if not t:
            continue
        first_ok = bool(t.get("valid") and t.get("attempts", 1) == 1)
        out.append({"pair_id": r["pair_id"], "verdict": t.get("verdict") if first_ok else None, "valid": first_ok,
                    "latency_ms": t.get("latency_ms"), "tokens_in": t.get("tokens_in", 0),
                    "tokens_out": t.get("tokens_out", 0), "error": t.get("error"),
                    "output_text": t.get("raw_output"), "reused_teacher_labels": True})
    return out


async def run_tinker(role: str, rows: list[dict], ctx: dict, concurrency: int) -> list[dict]:
    import tinker

    from ml.tinker_sampling import classify_many

    info = ROLE_INFO[role]
    _tok, renderer = make_renderer(info["model"])
    service = tinker.ServiceClient()
    if role == "lora":
        mp = tinker_model_path()
        if not mp:
            raise SystemExit("no LoRA model path: run python -m ml.train_tinker (writes ml/results/model_path.txt)")
        sc = await service.create_sampling_client_async(model_path=mp)
        info["model_path"] = mp
    else:
        sc = await service.create_sampling_client_async(base_model=info["model"])
    items = [(r["pair_id"], messages_for(info["prompt"], r, ctx)) for r in rows]
    await classify_many(sc, renderer, items[:1], concurrency=1, max_tokens=200)  # warm-up
    t0 = time.time()
    res = await classify_many(sc, renderer, items, concurrency=concurrency, max_tokens=200, retries=0,
                              temperature=0.0)
    print(f"  {role}: {len(items)} pairs in {time.time() - t0:.1f}s")
    out = []
    for r in rows:
        x = res[r["pair_id"]]
        out.append({"pair_id": r["pair_id"], "verdict": x.verdict.model_dump() if x.verdict else None,
                    "valid": x.verdict is not None, "latency_ms": round(x.latency_ms, 1), "tokens_in": x.prompt_tokens,
                    "tokens_out": x.completion_tokens, "error": x.error, "output_text": x.first_text or x.text})
    return out


# ------------------------------------------------------------------------------------- stats
def boot_ci(correct: list[int], n_boot: int = N_BOOT, seed: int = SEED) -> list[float]:
    import numpy as np

    if not correct:
        return [0.0, 0.0]
    a = np.asarray(correct, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(n_boot, len(a)))
    m = a[idx].mean(axis=1)
    return [round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def paired_boot_ci(a: list[int], b: list[int], n_boot: int = N_BOOT, seed: int = SEED) -> list[float]:
    import numpy as np

    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    m = d[idx].mean(axis=1)
    return [round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def mcnemar_exact(only_a: int, only_b: int) -> float:
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return round(min(1.0, 2 * p), 6)


def f1(tp: int, fp: int, fn: int) -> float:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def pred_label(p: dict | None) -> str | None:
    return (p or {}).get("verdict", {}).get("verdict") if p and p.get("verdict") else None


def metrics(name: str, role: str, model: str, preds: dict[str, dict], rows: list[dict], gold: dict[str, str]) -> tuple[dict, dict]:
    n = len(rows)
    correct, conf, invalid = [], [[0] * 3 for _ in range(3)], 0
    risky_n = risky_hit = safe_n = false_alarm = 0
    lat, tin, tout = [], 0, 0
    child_c = []
    for r in rows:
        g = gold[r["pair_id"]]
        p = preds.get(r["pair_id"])
        y = pred_label(p)
        if y is None:
            invalid += 1
        correct.append(int(y == g))
        if r.get("is_childrens"):
            child_c.append(int(y == g))
        if y in LABELS:
            conf[LABELS.index(g)][LABELS.index(y)] += 1
        if g in RISKY:
            risky_n += 1
            risky_hit += y in RISKY
        else:
            safe_n += 1
            false_alarm += y in RISKY
        if p:
            if p.get("latency_ms") is not None:
                lat.append(p["latency_ms"])
            tin += p.get("tokens_in") or 0
            tout += p.get("tokens_out") or 0
    per_class = []
    for i, lab in enumerate(LABELS):
        tp = conf[i][i]
        fp = sum(conf[j][i] for j in range(3)) - tp
        fn = sum(1 for r in rows if gold[r["pair_id"]] == lab) - tp
        per_class.append(round(f1(tp, fp, fn), 4))
    cost = None
    if model == "heuristic":
        cost = 0.0
    elif not model.startswith("backboard"):
        cost = round(sample_cost_usd(model, tin, tout) / max(1, n) * 1000, 4)
    row = {
        "name": name, "role": role, "model": model, "n": n,
        "acc": round(sum(correct) / n, 4) if n else None, "acc_ci": boot_ci(correct),
        "macro_f1": round(sum(per_class) / 3, 4), "f1_by_class": dict(zip(LABELS, per_class)),
        "risky_caught": f"{risky_hit}/{risky_n}", "false_alarms": f"{false_alarm}/{safe_n}",
        "childrens_acc": round(sum(child_c) / len(child_c), 4) if child_c else None,
        "json_valid": round((n - invalid) / n, 4) if n else None,
        "p50_latency_ms": round(percentile(lat, 0.5), 2) if lat else None,
        "p95_latency_ms": round(percentile(lat, 0.95), 2) if lat else None,
        "avg_tokens_in": round(tin / n, 1) if n else None, "avg_tokens_out": round(tout / n, 1) if n else None,
        "cost_per_1k_usd": cost, "pending": False,
    }
    return row, {"labels": LABELS, "matrix": conf, "invalid": invalid}


def role_preds() -> dict[str, dict[str, dict]]:
    out = {}
    for role in ORDER:
        p = read_jsonl(PREDS / f"{role}.jsonl")
        if p:
            out[role] = {x["pair_id"]: x for x in p}
    for f in sorted(PREDS.glob("backboard_*.jsonl")) if PREDS.exists() else []:
        p = read_jsonl(f)
        if p:
            out["backboard:" + (p[0].get("model") or f.stem.removeprefix("backboard_"))] = {x["pair_id"]: x for x in p}
    return out


def pick_examples(rows, gold, by_role, ctx, k: int = 8) -> list[dict]:
    def lab(role, pid):
        return pred_label(by_role.get(role, {}).get(pid))

    scored = []
    for r in rows:
        pid, g = r["pair_id"], gold[r["pair_id"]]
        base, lora = lab("base", pid), lab("lora", pid)
        fixed = lora == g and base != g
        broke = base == g and lora != g
        scored.append((0 if fixed else (2 if broke else 1), 0 if g in RISKY else 1, 0 if r.get("is_childrens") else 1,
                       pid, r))
    scored.sort(key=lambda x: x[:4])
    out, per_recall = [], Counter()
    for *_, r in scored:
        if len(out) >= k:
            break
        if per_recall[r["recall_number"]] >= 2:
            continue
        per_recall[r["recall_number"]] += 1
        pid = r["pair_id"]

        def full(role):
            p = by_role.get(role, {}).get(pid)
            return (p or {}).get("verdict") if p else None

        out.append({"pair_id": pid, "listing_title": ctx["listings"][r["listing_id"]]["title"],
                    "recall_title": ctx["recalls"][r["recall_number"]]["title"], "recall_number": r["recall_number"],
                    "gold": gold[pid], "base": lab("base", pid), "lora": lab("lora", pid),
                    "teacher": lab("teacher", pid), "heuristic": lab("heuristic", pid),
                    "base_verdict": full("base"), "lora_verdict": full("lora")})
    return out


def build_eval(rows, gold, ctx, gold_src: str) -> tuple[dict, dict]:
    by_role = role_preds()
    models, confusion = [], {}
    for role, preds in by_role.items():
        info = ROLE_INFO.get(role) or {"name": role.split(":", 1)[1] + " (via Backboard)",
                                      "model": "backboard:" + role.split(":", 1)[1]}
        row, cm = metrics(info["name"], role, info["model"], preds, rows, gold)
        any_p = next(iter(preds.values()))
        if any_p.get("model_path"):
            row["model_path"] = any_p["model_path"]
        if any_p.get("reused_teacher_labels"):
            row["note"] = "verdicts reused from teacher labeling run (first attempt only)"
        if any_p.get("prompt"):
            row["prompt"] = any_p["prompt"]
        models.append(row)
        confusion[role] = cm
    for role in ("teacher", "base", "base_guided", "lora"):
        if role not in by_role:
            models.append({"name": ROLE_INFO[role]["name"], "role": role, "model": ROLE_INFO[role]["model"],
                           "pending": True, "acc": None})
    paired = []
    for a, b in PAIRED:
        if a in by_role and b in by_role:
            ca = [int(pred_label(by_role[a].get(r["pair_id"])) == gold[r["pair_id"]]) for r in rows]
            cb = [int(pred_label(by_role[b].get(r["pair_id"])) == gold[r["pair_id"]]) for r in rows]
            oa = sum(x and not y for x, y in zip(ca, cb))
            ob = sum(y and not x for x, y in zip(ca, cb))
            paired.append({"a": a, "b": b, "gain": round((sum(ca) - sum(cb)) / len(rows), 4),
                           "ci": paired_boot_ci(ca, cb), "only_a": oa, "only_b": ob, "p": mcnemar_exact(oa, ob)})
    for role in by_role:
        if role.startswith("backboard:") and "lora" in by_role:
            ca = [int(pred_label(by_role["lora"].get(r["pair_id"])) == gold[r["pair_id"]]) for r in rows]
            cb = [int(pred_label(by_role[role].get(r["pair_id"])) == gold[r["pair_id"]]) for r in rows]
            oa = sum(x and not y for x, y in zip(ca, cb))
            ob = sum(y and not x for x, y in zip(ca, cb))
            paired.append({"a": "lora", "b": role, "gain": round((sum(ca) - sum(cb)) / len(rows), 4),
                           "ci": paired_boot_ci(ca, cb), "only_a": oa, "only_b": ob, "p": mcnemar_exact(oa, ob)})
    tl = {}
    try:
        tl = json.loads((RESULTS / "training.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    training = {"base_model": tl.get("base_model", STUDENT_MODEL), "rank": tl.get("rank", 32),
                "steps": tl.get("steps", 0), "epochs": tl.get("epochs", 0), "lr": tl.get("lr"),
                "batch_size": tl.get("batch_size"), "train_examples": tl.get("train_examples"),
                "loss_curve": tl.get("loss_curve", []), "test_nll": tl.get("test_nll", []),
                "model_path": tl.get("model_path")}
    split_stats = {}
    try:
        split_stats = json.loads((SPLITS / "split_stats.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    ev = {
        "test_size": len(rows), "generated_at": now_iso(),
        "gold": "human (blind)" if gold_src == "human" else "teacher (PROVISIONAL - not human gold)",
        "gold_dist": dict(Counter(gold[r["pair_id"]] for r in rows)),
        "test_recalls": len({r["recall_number"] for r in rows}),
        "test_childrens_pairs": sum(bool(r.get("is_childrens")) for r in rows),
        "teacher_model": TEACHER_MODEL, "student_model": STUDENT_MODEL,
        "models": models, "paired": paired, "confusion": confusion, "training": training,
        "examples": pick_examples(rows, gold, by_role, ctx), "split": split_stats,
        "notes": [
            "Gold = blind human labels from ml/label_ui (no model output shown); test recalls never appear in train.",
            "Single attempt, temperature 0; invalid JSON counts as wrong. risky = gold in {match, check}.",
            "acc_ci = 10,000-sample bootstrap 95% CI; paired p = exact two-sided McNemar on discordant pairs.",
            "base/lora use the short student prompt; base_guided adds the teacher's long rulebook; the teacher also "
            "sees the CPSC description.",
            "Cost = measured tokens x Tinker list prices (models.json 2026-10-17); latency = wall-clock per request.",
        ],
    }
    return ev, by_role


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--roles", default="auto", help="comma list: heuristic,base,base_guided,lora,teacher")
    ap.add_argument("--gold", default="human", choices=["human", "teacher"])
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--rebuild-only", action="store_true")
    ap.add_argument("--rerun-teacher", action="store_true")
    args = ap.parse_args()
    load_env()
    rows, gold, ctx = load_test(args.gold)
    has_key = bool(os.environ.get("TINKER_API_KEY"))
    if args.roles == "auto":
        roles = ["heuristic"]
        if (LABELED / "teacher.jsonl").exists():
            roles.append("teacher")
        if has_key:
            roles += ["base", "base_guided"] + (["lora"] if tinker_model_path() else [])
    else:
        roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    PREDS.mkdir(parents=True, exist_ok=True)
    if not args.rebuild_only:
        for role in roles:
            info = ROLE_INFO[role]
            if role == "heuristic":
                preds = run_heuristic(rows, ctx)
            elif role == "teacher" and not args.rerun_teacher:
                preds = reuse_teacher(rows)
            else:
                if not has_key:
                    raise SystemExit(f"TINKER_API_KEY is not set (needed for role {role!r}). Put it in .env.")
                preds = asyncio.run(run_tinker(role, rows, ctx, args.concurrency))
                pt, ct = sum(p["tokens_in"] for p in preds), sum(p["tokens_out"] for p in preds)
                add_spend(f"eval_{role}", {"model": info["model"], "prompt_tokens": pt, "completion_tokens": ct,
                                           "est_usd": round(sample_cost_usd(info["model"], pt, ct), 4)})
            for p in preds:
                p.update(role=role, model=info["model"], prompt=info["prompt"])
                if info.get("model_path"):
                    p["model_path"] = info["model_path"]
            write_jsonl(PREDS / f"{role}.jsonl", preds)
    ev, by_role = build_eval(rows, gold, ctx, args.gold)
    write_json(RESULTS / "eval.json", ev)
    flat = []
    for role, preds in by_role.items():
        for r in rows:
            p = preds.get(r["pair_id"])
            if p:
                flat.append({**p, "role": role, "gold": gold[r["pair_id"]], "recall_number": r["recall_number"],
                             "listing_id": r["listing_id"]})
    write_jsonl(RESULTS / "predictions.jsonl", flat)
    cols = ["acc", "macro_f1", "risky_caught", "false_alarms", "json_valid", "p50_latency_ms", "cost_per_1k_usd"]
    print(f"\ntest_size={ev['test_size']} gold={ev['gold']} dist={ev['gold_dist']}")
    print(f"{'role':24s} " + " ".join(f"{c[:12]:>12s}" for c in cols))
    for m in ev["models"]:
        print(f"{m['role'][:24]:24s} " + " ".join(
            f"{'pending' if m.get('pending') else str(m.get(c)):>12s}"[:12].rjust(12) for c in cols))
    for p in ev["paired"]:
        print(f"  {p['a']} vs {p['b']}: gain {p['gain']:+.3f} CI {p['ci']} only_a={p['only_a']} only_b={p['only_b']} "
              f"p={p['p']}")


if __name__ == "__main__":
    main()
