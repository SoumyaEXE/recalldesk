"""LoRA SFT of the student (Qwen3.5-4B) on teacher MatchVerdict JSON via Tinker.

    python -m ml.train_tinker [--epochs 3] [--batch-size 16] [--rank 32] [--lr auto] [--dry-run]

- Input = SHORT student prompt (ml/prompts.STUDENT_SYSTEM + compact spec + listing); target = teacher JSON.
  The teacher labeled with a long guided prompt + the CPSC text -> prompt/privileged-info distillation.
- Train pairs only (split by recall); no human labels are ever used for training.
- Loss only on the assistant JSON (TrainOnWhat.LAST_ASSISTANT_MESSAGE), renderer qwen3_5_disable_thinking.
- LR: tinker_cookbook.hyperparam_utils.get_lr(student) (cookbook LoRA default), linear decay to 0, Adam
  (beta1 .9, beta2 .95, eps 1e-8). Held-out NLL (test pairs vs teacher targets) at step 0 and after each epoch.
- Saves sampler weights; tinker:// path -> ml/results/model_path.txt; curves -> ml/results/training.json.
`--dry-run` builds the dataset and prints token counts / cost estimate without a key.
"""
from __future__ import annotations

import argparse
import math
import random
import time
from collections import Counter

from ml.common import (LABELED, RENDERER_NAME, RESULTS, SPLITS, STUDENT_MODEL, add_spend, load_listings, load_specs, now_iso,
                       price_of, read_jsonl, require_key, utf8_stdout, write_json)
from ml.prompts import student_messages
from shared.schema import MatchVerdict, verdict_json


def build_conversations(split: str) -> list[dict]:
    rows = read_jsonl(SPLITS / f"{split}.jsonl")
    teacher = {r["pair_id"]: r for r in read_jsonl(LABELED / "teacher.jsonl") if r.get("valid")}
    specs, listings = load_specs(), load_listings()
    out = []
    for r in rows:
        t = teacher.get(r["pair_id"])
        spec, lst = specs.get(r["recall_number"]), listings.get(r["listing_id"])
        if not (t and spec and lst):
            continue
        v = MatchVerdict.model_validate(t["verdict"])
        msgs = student_messages(spec, lst) + [{"role": "assistant", "content": verdict_json(v)}]
        out.append({"pair_id": r["pair_id"], "messages": msgs, "label": v.verdict})
    return out


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--rank", type=int, default=32)
    ap.add_argument("--lr", type=str, default="auto")
    ap.add_argument("--max-length", type=int, default=1536)
    ap.add_argument("--name", type=str, default="recalldesk-qwen3.5-4b-lora")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    train, test = build_conversations("train"), build_conversations("test")
    if not train:
        raise SystemExit("no training conversations: need data/splits/train.jsonl + data/labeled/teacher.jsonl "
                         "(run ml.make_pairs then ml.teacher_label)")
    print(f"train={len(train)} {dict(Counter(c['label'] for c in train))}  heldout={len(test)}")
    approx_tokens = sum(len(m["content"]) for c in train for m in c["messages"]) // 3.5
    if args.dry_run:
        est = approx_tokens * args.epochs * price_of(STUDENT_MODEL)["train"] / 1e6
        print(f"[dry-run] ~{int(approx_tokens)} tokens/epoch (chars/3.5), est train ~${est:.3f}")
        print(train[0]["messages"][1]["content"][:800])
        print("->", train[0]["messages"][2]["content"])
        return
    require_key("TINKER_API_KEY", "LoRA training")

    import tinker
    from tinker_cookbook.hyperparam_utils import get_lr
    from tinker_cookbook.renderers import TrainOnWhat
    from tinker_cookbook.supervised.common import compute_mean_nll
    from tinker_cookbook.supervised.data import conversation_to_datum

    from ml.common import make_renderer

    _tok, renderer = make_renderer(STUDENT_MODEL)

    def to_datum(c):
        return conversation_to_datum(c["messages"], renderer, args.max_length, TrainOnWhat.LAST_ASSISTANT_MESSAGE)

    train_data = [to_datum(c) for c in train]
    test_data = [to_datum(c) for c in test]
    train_tokens = sum(d.model_input.length for d in train_data)
    lr = get_lr(STUDENT_MODEL) if args.lr == "auto" else float(args.lr)
    steps_per_epoch = math.ceil(len(train_data) / args.batch_size)
    total_steps = steps_per_epoch * args.epochs
    est_usd = train_tokens * args.epochs * price_of(STUDENT_MODEL)["train"] / 1e6
    print(f"student={STUDENT_MODEL} renderer={RENDERER_NAME} rank={args.rank} lr={lr:.2e} steps={total_steps} "
          f"tokens/epoch={train_tokens} est_train_usd~{est_usd:.3f}")

    service = tinker.ServiceClient()
    tc = service.create_lora_training_client(base_model=STUDENT_MODEL, rank=args.rank, seed=args.seed)
    log = {"base_model": STUDENT_MODEL, "renderer": RENDERER_NAME, "rank": args.rank, "lr": lr,
           "lr_schedule": "linear", "batch_size": args.batch_size, "epochs": args.epochs, "steps": 0,
           "train_examples": len(train_data), "heldout_examples": len(test_data),
           "train_label_dist": dict(Counter(c["label"] for c in train)), "label_source": "teacher",
           "train_tokens_per_epoch": train_tokens, "loss_curve": [], "test_nll": [], "started_at": now_iso()}

    def eval_test(step: int) -> None:
        if not test_data:
            return
        lps, ws = [], []
        for i in range(0, len(test_data), 64):
            batch = test_data[i : i + 64]
            out = tc.forward(batch, "cross_entropy").result()
            lps += [o["logprobs"] for o in out.loss_fn_outputs]
            ws += [d.loss_fn_inputs["weights"] for d in batch]
        nll = compute_mean_nll(lps, ws)
        log["test_nll"].append([step, round(nll, 5)])
        print(f"  [heldout] step {step}: NLL {nll:.4f}")

    rng = random.Random(args.seed)
    eval_test(0)
    step = 0
    t0 = time.time()
    for epoch in range(args.epochs):
        order = list(range(len(train_data)))
        rng.shuffle(order)
        for b in range(steps_per_epoch):
            batch = [train_data[i] for i in order[b * args.batch_size : (b + 1) * args.batch_size]]
            if not batch:
                continue
            cur_lr = lr * max(0.0, 1.0 - step / total_steps)
            fwd_f = tc.forward_backward(batch, "cross_entropy")
            opt_f = tc.optim_step(tinker.AdamParams(learning_rate=cur_lr, beta1=0.9, beta2=0.95, eps=1e-8))
            fwd = fwd_f.result()
            opt_f.result()
            nll = compute_mean_nll([o["logprobs"] for o in fwd.loss_fn_outputs],
                                   [d.loss_fn_inputs["weights"] for d in batch])
            step += 1
            log["loss_curve"].append([step, round(nll, 5)])
            if step % 5 == 0 or step == 1:
                print(f"  epoch {epoch + 1} step {step}/{total_steps} lr {cur_lr:.2e} train NLL {nll:.4f} "
                      f"({time.time() - t0:.0f}s)")
        eval_test(step)
        log["steps"] = step
        write_json(RESULTS / "training.json", log)

    print("saving sampler weights ...")
    model_path = tc.save_weights_for_sampler(name=args.name).result().path
    (RESULTS / "model_path.txt").write_text(model_path + "\n", encoding="utf-8")
    log.update({"model_path": model_path, "finished_at": now_iso(), "wall_seconds": round(time.time() - t0, 1)})
    try:
        log["state_path"] = tc.save_state(name=args.name + "-state").result().path
    except Exception as e:  # noqa: BLE001
        log["state_path_error"] = repr(e)[:200]
    write_json(RESULTS / "training.json", log)
    fwd_tokens = sum(d.model_input.length for d in test_data) * (args.epochs + 1)
    add_spend("train_tinker", {"model": STUDENT_MODEL, "train_tokens": train_tokens * args.epochs,
                               "heldout_forward_tokens": fwd_tokens,
                               "est_usd": round((train_tokens * args.epochs + fwd_tokens)
                                                * price_of(STUDENT_MODEL)["train"] / 1e6, 4)})
    print(f"done. model_path={model_path}")


if __name__ == "__main__":
    main()
