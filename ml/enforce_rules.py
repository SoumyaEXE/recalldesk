"""Training targets = teacher labels, with LABELING.md rule 7 (unbranded look-alikes) enforced by code.

The teacher (even with rule 7 in its prompt) often calls a generic, unbranded listing "check" and
claims the brand matches when the listing names no brand. Code decides that case:

  teacher says match|check  AND  the listing title names no brand word
                            AND  no recalled identifier appears in the title
                            AND  fewer than 2 distinctive product-name words appear
  -> target becomes no_match ("generic look-alike").

targets.jsonl is both the TRAINING TARGET (train pairs) and the eval ANSWER KEY (test pairs; ml.eval --gold targets,
eval.json gold = "teacher + rule 7 by code (not human)"). The raw teacher output stays in data/labeled/teacher.jsonl.
No human labels were collected; ml.label_ui (data/gold/labels.jsonl) is only an optional audit.

    python -m ml.enforce_rules            # writes targets.jsonl + targets_stats.json
"""
from __future__ import annotations

import re
from collections import Counter

from ml.common import LABELED, load_listings, load_specs, read_jsonl, utf8_stdout, write_json

# words that say nothing about WHICH brand or product it is
STOP = set("""
inc llc ltd co corp corporation company of the and usa us international group dba products product toys toy baby
kids kid home store brand trading technology industrial limited children childrens child s for with set pcs pc
pack new set of in on to a an by from mini large small kit plus pro edition series style type light lights led up
""".split())


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def squash(s: str) -> str:
    return norm(s).replace(" ", "")


def brand_words(brand: str) -> set[str]:
    words = set(norm(brand).split()) - STOP
    first = norm(brand).split()[:1]          # keep a short leading brand word such as "DR" or "3M"
    return {w for w in words if len(w) >= 3} | set(first)


def distinctive_words(spec: dict) -> set[str]:
    name = set(norm(spec.get("product_name", "")).split())
    generic = set(norm(spec.get("product_type", "")).split()) | brand_words(spec.get("brand", "")) | STOP
    return {w for w in name - generic if len(w) >= 3 or w.isdigit()}


def id_hit(spec: dict, title: str) -> bool:
    t = squash(title)
    ids = (spec.get("model_numbers") or []) + (spec.get("upcs") or []) + (spec.get("other_identifiers") or [])
    return any(len(squash(i)) >= 4 and squash(i) in t for i in ids)


def is_generic_lookalike(spec: dict, title: str) -> bool:
    words = set(norm(title).split())
    if brand_words(spec.get("brand", "")) & words:
        return False
    if id_hit(spec, title):
        return False
    return len(distinctive_words(spec) & words) < 2


def main() -> None:
    utf8_stdout()
    specs, listings = load_specs(), load_listings()
    pairs = {r["pair_id"]: r for r in read_jsonl(LABELED.parent / "pairs" / "pairs.jsonl")}
    out, changed = [], Counter()
    for t in read_jsonl(LABELED / "teacher.jsonl"):
        row = dict(t)
        p = pairs.get(t["pair_id"])
        v = (t.get("verdict") or {}).get("verdict")
        if p and t.get("valid") and v in ("match", "check"):
            spec, lst = specs.get(p["recall_number"]), listings.get(p["listing_id"])
            if spec and lst and is_generic_lookalike(spec, lst.get("title", "")):
                row["teacher_verdict"] = t["verdict"]
                row["verdict"] = {"verdict": "no_match", "identifiers_found": [], "conflicts": [],
                                  "reason": "Generic look-alike: no brand and no recalled identifier in the listing."}
                row["corrected"] = "rule7"
                changed[(v, p.get("split", "?"))] += 1
        out.append(row)
    (LABELED / "targets.jsonl").write_text("".join(__import__("json").dumps(r, ensure_ascii=False) + "\n" for r in out),
                                           encoding="utf-8")
    dist = Counter((r.get("verdict") or {}).get("verdict") for r in out)
    stats = {"pairs": len(out), "corrected_rule7": sum(changed.values()),
             "corrected_by": {f"{k[0]}->no_match ({k[1]})": n for k, n in changed.items()},
             "target_distribution": dict(dist)}
    write_json(LABELED / "targets_stats.json", stats)
    print(stats)


if __name__ == "__main__":
    main()
