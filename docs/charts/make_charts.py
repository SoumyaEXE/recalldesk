"""RecallDesk blog charts (matplotlib) -> docs/charts/*.png, plus docs/charts/chart_data.json (every number drawn).

    docs/charts/.venv/Scripts/python.exe docs/charts/make_charts.py          # all charts
    docs/charts/.venv/Scripts/python.exe docs/charts/make_charts.py hazard-types where-sold

Idempotent: it only READS data/ and ml/results/ (and the raw SerpApi cache data/serp/*.json, never spending a search),
then overwrites the PNGs. Charts a-f are built from real CPSC + SerpApi data. Charts in group g come from
ml/results/*; while those files are missing (or marked "placeholder": true) they use the illustrative values from
docs/visuals/build_data.py and carry a red PLACEHOLDER watermark. The project's answer key is eval.json
gold = "teacher + rule 7 by code (not human)" (data/labeled/targets.jsonl): that is final, so those charts are real and
their source line says "answer key: teacher + rule 7 (code), not human". Only eval.json graded against RAW teacher
labels (no rule 7) is drawn with an amber PROVISIONAL watermark.

Seller names never leave this script: only titles, conditions and counts are read from the cache.
Setup (once):
    python -m uv venv --python 3.12 docs/charts/.venv
    python -m uv pip install --python docs/charts/.venv/Scripts/python.exe matplotlib numpy
Fonts: docs/charts/fonts/*.ttf (Barlow Condensed, Public Sans, IBM Plex Mono from Google Fonts / Fontsource);
missing fonts fall back to DejaVu.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import textwrap
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.patches import Rectangle, RegularPolygon  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = Path(os.environ["RECALLDESK_DATA"]) if os.environ.get("RECALLDESK_DATA") else ROOT / "data"
RES = Path(os.environ["RECALLDESK_RESULTS"]) if os.environ.get("RECALLDESK_RESULTS") else ROOT / "ml" / "results"
OUT = Path(os.environ["RECALLDESK_CHARTS_OUT"]) if os.environ.get("RECALLDESK_CHARTS_OUT") else HERE
sys.path.insert(0, str(ROOT))
from ml.regex_ids import extract_ids_typed, find_ids_in_text, norm_id  # noqa: E402

SRC_LINE = "Source: CPSC Recalls API / SerpApi eBay, fetched 2026-10-17"
CPSC_LINE = "Source: CPSC Recalls API, fetched 2026-10-17"
SINCE_A = "2026-07-18"
MODEL_KINDS = ("model", "item", "style", "sku", "part", "product_id", "ref")
LABELS = ["match", "check", "no_match"]

# ------------------------------------------------------------------------------------------------ tokens
C = dict(
    bg="#faf7f0", paper="#fffdf8", ink="#1d1c19", ink2="#5b5548", ink3="#797262", grid="#e6e0d1", rule="#d7d0be",
    blue="#2b5fab", blue_l="#85a6d4", blue_xl="#d9e4f3", other="#b9b2a2", other_l="#e2ddd0", stop="#c8102e",
    stop_l="#f1b3b8", amber="#e8a200", amber_l="#efcf78", clear="#2e7d4f", clear_l="#acd6bb", s1="#2a78d6",
    s2="#eb6834", kicker="#28508c", n900="#1d1c19",
)

FONTS = {"sans": "DejaVu Sans", "notice": "DejaVu Sans", "mono": "DejaVu Sans Mono"}


def load_fonts() -> None:
    fdir = HERE / "fonts"
    for f in sorted(fdir.glob("*.ttf")):
        try:
            fm.fontManager.addfont(str(f))
            name = fm.FontProperties(fname=str(f)).get_name()
        except Exception:  # noqa: BLE001
            continue
        if name.startswith("Barlow"):
            FONTS["notice"] = name
        elif name.startswith("IBM Plex Mono"):
            FONTS["mono"] = name
        elif name.startswith("Public Sans"):
            FONTS["sans"] = name
    plt.rcParams.update({
        "font.family": [FONTS["sans"], "DejaVu Sans"], "font.size": 10, "axes.edgecolor": C["rule"], "axes.labelcolor": C["ink2"],
        "xtick.color": C["ink2"], "ytick.color": C["ink2"], "axes.linewidth": 0.8, "xtick.major.width": 0.8,
        "ytick.major.width": 0.8, "svg.fonttype": "none", "figure.dpi": 200, "savefig.dpi": 200,
    })


# ------------------------------------------------------------------------------------------------ io
def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def placeholder_values() -> dict:
    """Illustrative values shared with docs/visuals (so placeholder charts agree with placeholder visuals)."""
    spec = importlib.util.spec_from_file_location("rd_build_data", ROOT / "docs" / "visuals" / "build_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PLACEHOLDER


# ------------------------------------------------------------------------------------------------ figure frame
W = 8.0  # inches; at 200 dpi -> 1600 px wide (2x of an 800 css-px column)


class Frame:
    """Header (hazard tape, kicker, title, subtitle), a content rect, and a footer (source + brand)."""

    def __init__(self, h: float, kicker: str, title: str, sub: str, source: str, status: str = "real",
                 notes: str = ""):
        self.fig = plt.figure(figsize=(W, h), facecolor=C["bg"])
        self.h = h
        f = self.fig
        # hazard tape
        tape = f.add_axes([0, 1 - 0.07 / h, 1, 0.07 / h])
        tape.set_xlim(0, 160)
        tape.set_ylim(0, 1)
        tape.axis("off")
        for i in range(-2, 170, 2):
            tape.add_patch(plt.Polygon([[i, 0], [i + 1, 0], [i + 2, 1], [i + 1, 1]], color=C["amber"], lw=0))
            tape.add_patch(plt.Polygon([[i + 1, 0], [i + 2, 0], [i + 3, 1], [i + 2, 1]], color=C["n900"], lw=0))
        y = h - 0.32
        f.text(0.5 / W, y / h, kicker.upper(), fontfamily=FONTS["mono"], fontsize=8, fontweight=600,
               color=C["kicker"], va="baseline")
        y -= 0.40
        t = f.text(0.5 / W, y / h, title, fontfamily=FONTS["notice"], fontsize=19, fontweight=700, color=C["ink"],
                   va="baseline")
        r = f.canvas.get_renderer()
        size = 19.0
        while size > 12 and t.get_window_extent(r).width > (W - 1.0) * f.dpi:
            size -= 0.5
            t.set_fontsize(size)
        y -= 0.10
        for line in textwrap.wrap(sub, 118):
            y -= 0.21
            f.text(0.5 / W, y / h, line, fontsize=9, color=C["ink2"], va="baseline")
        self.top = y - 0.22  # inches from bottom where content may start
        foot_lines = textwrap.wrap(notes, 130) if notes else []
        fy = 0.22
        f.add_artist(plt.Line2D([0.5 / W, 1 - 0.5 / W], [(fy + 0.17) / h] * 2, color=C["rule"], lw=0.8))
        f.text(0.5 / W, fy / h, source, fontfamily=FONTS["mono"], fontsize=6.6, color=C["ink3"], va="baseline")
        f.text(1 - 0.5 / W, fy / h, "RECALLDESK", fontfamily=FONTS["mono"], fontsize=6.6, fontweight=600,
               color=C["kicker"], ha="right", va="baseline")
        ny = fy + 0.17 + 0.12
        for line in reversed(foot_lines):
            f.text(0.5 / W, ny / h, line, fontsize=7.4, color=C["ink2"], va="baseline")
            ny += 0.17
        self.bottom = ny + 0.08
        self.status = status

    def axes(self, left=1.0, right=0.5, top_pad=0.0, bottom_pad=0.35, rect=None):
        if rect is not None:  # inches: x, y, w, h
            x, y, w, hh = rect
            return self.fig.add_axes([x / W, y / self.h, w / W, hh / self.h])
        y0 = self.bottom + bottom_pad
        y1 = self.top - top_pad
        return self.fig.add_axes([left / W, y0 / self.h, (W - left - right) / W, (y1 - y0) / self.h])

    def save(self, name: str) -> Path:
        if self.status in ("placeholder", "provisional"):
            word, col = ("PLACEHOLDER", C["stop"]) if self.status == "placeholder" else ("PROVISIONAL", C["amber"])
            badge = "PLACEHOLDER · NOT REAL DATA" if self.status == "placeholder" else \
                "PROVISIONAL · RAW TEACHER LABELS"
            self.fig.text(0.5, 0.48, word, fontfamily=FONTS["notice"], fontsize=88, fontweight=700, color=col,
                          alpha=0.16, rotation=18, ha="center", va="center", zorder=100)
            self.fig.text(1 - 0.5 / W, (self.h - 0.32) / self.h, badge, fontfamily=FONTS["mono"], fontsize=7.5,
                          fontweight=600, color="white", ha="right", va="baseline", zorder=101,
                          bbox=dict(boxstyle="round,pad=0.35", fc=col, ec="none"))
        p = OUT / f"{name}.png"
        self.fig.savefig(p, facecolor=C["bg"])
        plt.close(self.fig)
        return p


def style_ax(ax, grid_axis="x"):
    ax.set_facecolor(C["bg"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if grid_axis == "x":
        ax.spines["left"].set_visible(False)
        ax.xaxis.grid(True, color=C["grid"], lw=0.7)
        ax.tick_params(axis="y", length=0)
    elif grid_axis == "y":
        ax.yaxis.grid(True, color=C["grid"], lw=0.7)
        ax.tick_params(axis="x", length=0)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=8.5)


def legend_row(fig_or_frame: Frame, items: list[tuple[str, str]], y_in: float, x_in: float = 0.5,
               hatch: dict | None = None):
    """A legend row drawn directly under the subtitle: [(color, label)]."""
    f = fig_or_frame.fig
    h = fig_or_frame.h
    x = x_in
    for col, lab in items:
        f.patches.append(Rectangle((x / W, (y_in - 0.02) / h), 0.13 / W, 0.13 / h, transform=f.transFigure,
                                   fc=col, ec="none", hatch=(hatch or {}).get(lab)))
        t = f.text((x + 0.19) / W, y_in / h, lab, fontsize=8.3, color=C["ink2"], va="baseline")
        x += 0.19 + 0.066 * len(lab) + 0.35
    return t


# ================================================================================================ data
class D:
    recalls: list[dict] = []
    A: list[dict] = []
    B: list[dict] = []
    specs: dict[str, dict] = {}
    searches: list[dict] = []  # one row per cached search: recall_number, n, titles+conditions


def load_data() -> None:
    D.recalls = read_jsonl(DATA / "recalls" / "recalls.jsonl")
    D.A = [r for r in D.recalls if "A" in (r.get("corpus") or [])]
    D.B = [r for r in D.recalls if "B" in (r.get("corpus") or [])]
    sp = DATA / "specs" / "specs.jsonl"
    if not sp.exists():
        sp = DATA / "specs" / "specs.heuristic.jsonl"
    D.specs = {s["recall_number"]: s for s in read_jsonl(sp)}
    rows = []
    for i in read_jsonl(DATA / "listings" / "search_index.jsonl"):
        if i.get("error"):
            continue
        p = DATA / "serp" / f"{i.get('cache_key')}.json"
        raw = load_json(p)
        if raw is None:
            continue
        items = [{"key": o.get("product_id") or o.get("link"), "title": o.get("title") or "",
                  "condition": o.get("condition")} for o in raw.get("organic_results") or []]
        rows.append({"recall_number": i["recall_number"], "query": i.get("query"), "items": items})
    D.searches = rows


def recall_ids(rn: str) -> list[str]:
    """Recalled identifiers for exact matching: teacher spec model numbers + UPCs (grounded in the CPSC text)."""
    s = D.specs.get(rn, {})
    return [*s.get("model_numbers", []), *s.get("upcs", [])]


def norm_condition(c: str | None) -> str:
    c = (c or "").lower()
    if not c:
        return "Not stated"
    if "pre-owned" in c or "used" in c:
        return "Pre-Owned"
    if "open box" in c:
        return "Open box"
    if "refurb" in c:
        return "Refurbished"
    if "parts" in c:
        return "For parts"
    if "new" in c:
        return "New"
    return "Other"


# ================================================================================================ charts a-f
def chart_recalls_per_thursday(stats: dict):
    by = defaultdict(lambda: [0, 0])
    for r in D.A:
        by[r["recall_date"]][0 if r.get("is_childrens") else 1] += 1
    days = sorted(by)
    weekdays = Counter(date.fromisoformat(d).strftime("%A") for d in days)
    kids = [by[d][0] for d in days]
    rest = [by[d][1] for d in days]
    n, nk = len(D.A), sum(kids)
    wd = weekdays.most_common(1)[0][0] if weekdays else "Thursday"
    allsame = len(weekdays) == 1
    fr = Frame(4.6, f"CPSC recalls since {SINCE_A}",
               f"{n} recalls in {len(days)} weeks, every one posted on a {wd}" if allsame else
               f"{n} recalls on {len(days)} posting days",
               f"About {round(n / max(len(days), 1))} a week; {nk} of them ({100 * nk / max(n, 1):.0f}%) are "
               f"children's products, the ones kids' consignment shops and resellers see most.",
               CPSC_LINE, notes="Children's = ml/fetch_recalls.is_childrens (title head, product names, first two "
                                "sentences; child-resistant packaging and battery-law mentions excluded).")
    legend_row(fr, [(C["blue"], f"Children's products ({nk})"), (C["other"], f"Other products ({n - nk})")],
               fr.top - 0.05)
    ax = fr.axes(left=0.75, right=0.5, top_pad=0.3, bottom_pad=0.42)
    x = range(len(days))
    ax.bar(x, kids, width=0.66, color=C["blue"], edgecolor=C["bg"], lw=1.2, zorder=3)
    ax.bar(x, rest, width=0.66, bottom=kids, color=C["other"], edgecolor=C["bg"], lw=1.2, zorder=3)
    for i, d in enumerate(days):
        ax.text(i, kids[i] + rest[i] + 0.35, str(kids[i] + rest[i]), ha="center", va="bottom", fontsize=8.5,
                fontfamily=FONTS["notice"], fontweight=600, color=C["ink"])
    ax.set_xticks(list(x), [date.fromisoformat(d).strftime("%b %-d" if os.name != "nt" else "%b %#d") for d in days],
                  fontsize=8)
    style_ax(ax, "y")
    ax.set_ylim(0, max(k + r for k, r in zip(kids, rest)) * 1.18 + 1)
    ax.set_ylabel("recalls posted", fontsize=8.5)
    return fr.save("recalls-per-thursday"), {
        "recalls": n, "childrens": nk, "posting_days": len(days), "weekday": wd, "all_same_weekday": allsame,
        "by_day": [{"date": d, "childrens": by[d][0], "other": by[d][1]} for d in days]}


def ids_buried_counts(rows: list[dict]) -> dict:
    """Primary method (same as docs/visuals/build_data.py): typed regex extraction from the description,
    model/item/style/SKU/part/product-id/ref kinds, exclusions dropped. buried = none of them occurs in the
    normalized title + product names."""
    out = Counter()
    teacher = Counter()
    for r in rows:
        typed = extract_ids_typed(r.get("description") or "", r.get("upcs") or [])
        ms = [x["id"] for x in typed if not x["excluded"] and x["kind"] in MODEL_KINDS]
        hay = norm_id((r.get("title") or "") + " " + " ".join(r.get("product_names") or []))
        if not ms:
            out["none"] += 1
        elif any(norm_id(m) in hay for m in ms):
            out["title"] += 1
        else:
            out["buried"] += 1
        # cross-check: teacher spec model numbers (grounded in the notice by ml.spec_extract.ground_ids)
        tm = (D.specs.get(r["recall_number"]) or {}).get("model_numbers") or []
        if not tm:
            teacher["none"] += 1
        elif any(norm_id(m) in hay for m in tm):
            teacher["title"] += 1
        else:
            teacher["buried"] += 1
    any_regex = sum(bool(r.get("regex_ids")) for r in rows)
    return {"n": len(rows), "buried": out["buried"], "in_title": out["title"], "no_model_id": out["none"],
            "with_model_id": out["buried"] + out["title"], "with_any_regex_id": any_regex,
            "teacher": {"buried": teacher["buried"], "in_title": teacher["title"], "no_model_id": teacher["none"]}}


def chart_ids_buried(_):
    a = ids_buried_counts(D.A)
    k = ids_buried_counts([r for r in D.A if r.get("is_childrens")])
    fr = Frame(3.9, "Where the model number lives",
               f"In {a['buried']} of {a['n']} recalls, the model number is only in the fine print",
               f"{a['with_model_id']} recalls since {SINCE_A} name a model, item, style, SKU or part number. In "
               f"{a['buried']} of them it appears only in the description paragraph, never in the title or "
               f"product name, so a title search finds the product line but not whether your unit is the one.",
               CPSC_LINE,
               notes=f"Method: deterministic typed regex (ml/regex_ids.extract_ids_typed) on the description, model-like "
                     f"kinds only, excluded models dropped; 'in title' = any id appears in the separator-normalized "
                     f"title + product names. Cross-check with the teacher's spec model numbers: {a['teacher']['buried']} "
                     f"buried, {a['teacher']['in_title']} in title, {a['teacher']['no_model_id']} none.")
    segs = [("buried", C["blue"], "Only in the description"), ("in_title", C["ink3"], "Also in title / product name"),
            ("no_model_id", C["other_l"], "No model-type number in the notice")]
    legend_row(fr, [(c, l) for _, c, l in segs], fr.top - 0.05)
    ax = fr.axes(left=1.75, right=0.5, top_pad=0.32, bottom_pad=0.38)
    rows = [(f"All recalls ({a['n']})", a), (f"Children's ({k['n']})", k)]
    for yi, (lab, d) in enumerate(rows):
        left = 0
        for key, col, _ in segs:
            v = d[key]
            pct = 100 * v / d["n"]
            ax.barh(yi, pct, left=left, height=0.66, color=col, edgecolor=C["bg"], lw=2, zorder=3)
            if pct > 6:
                ax.text(left + pct / 2, yi, f"{v}", ha="center", va="center", fontfamily=FONTS["notice"],
                        fontweight=700, fontsize=12, color="white" if key != "no_model_id" else C["ink"])
            left += pct
    ax.set_yticks([0, 1], [r[0] for r in rows], fontsize=9, color=C["ink"])
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylim(1.5, -0.5)
    style_ax(ax, "x")
    ax.xaxis.grid(False)
    return fr.save("ids-buried"), {"all": a, "childrens": k, "writer_figure": "73 of 151",
                                   "contract_figure": "69 of 151 (stale)"}


RETAILERS = [
    ("Amazon", r"\bamazon"), ("Walmart", r"\bwalmart"), ("Target", r"\btarget(?:\.com|\s+stores?|\b)"),
    ("Temu", r"\btemu\b"), ("SHEIN", r"\bshein\b"), ("Wayfair", r"\bwayfair"), ("Etsy", r"\betsy"),
    ("TikTok Shop", r"tiktok"), ("AliExpress", r"aliexpress"), ("Home Depot", r"home\s*depot"),
    ("Lowe's", r"\blowe['’]?s\b"), ("Costco", r"\bcostco"), ("eBay", r"\bebay"), ("Best Buy", r"best\s*buy"),
    ("Kohl's", r"\bkohl['’]?s"), ("TJX stores", r"t\.?j\.?\s*maxx|marshalls|homegoods"),
    ("Burlington", r"burlington"), ("Ross", r"\bross\s+(?:dress|stores)"), ("Five Below", r"five\s+below"),
]


def retailer_counts(rows):
    c = Counter()
    online = 0
    for r in rows:
        t = " ".join(r.get("retailers") or [])
        if re.search(r"online|\.com|website|amazon|temu|shein|etsy", t, re.I):
            online += 1
        for name, pat in RETAILERS:
            if re.search(pat, t, re.I):
                c[name] += 1
    return c, online


def chart_where_sold(stats):
    ca, oa = retailer_counts(D.A)
    cb, ob = retailer_counts(D.B)
    # 'sold online' uses ml/fetch_recalls' own definition (stats.json) so the post quotes one number
    oa = (stats.get("A") or {}).get("sold_online", oa)
    ob = (stats.get("B") or {}).get("sold_online", ob)
    na, nb = len(D.A), len(D.B)
    names = [n for n, _ in sorted(((n, ca[n] / na + cb[n] / max(nb, 1)) for n, _ in RETAILERS), key=lambda x: -x[1])
             if ca[n] + cb[n] > 0][:10]
    fr = Frame(6.6, "Where recalled products were sold",
               f"{ca['Amazon']} of {na} recent recalls were sold on Amazon",
               f"Retailers named in the CPSC 'Sold at' field. {oa} of {na} recalls since {SINCE_A} were sold online; "
               f"for children's products recalled since 2023 it is {ob} of {nb}. Marketplace sellers are where most "
               f"recalled stock came from, and where secondhand units go back to.",
               CPSC_LINE, notes="A recall counts once per retailer named; most name several. Share of recalls in each "
                                "corpus. Keyword match on the 'Sold at' text (docs/charts/make_charts.py RETAILERS).")
    legend_row(fr, [(C["blue"], f"All recalls since Jul 18 (n={na})"),
                    (C["other"], f"Children's recalls since 2023 (n={nb})")], fr.top - 0.05)
    ax = fr.axes(left=1.6, right=0.6, top_pad=0.3, bottom_pad=0.38)
    y = list(range(len(names)))
    h = 0.36
    va = [100 * ca[n] / na for n in names]
    vb = [100 * cb[n] / nb for n in names]
    ax.barh([i - h / 2 - 0.02 for i in y], va, height=h, color=C["blue"], zorder=3)
    ax.barh([i + h / 2 + 0.02 for i in y], vb, height=h, color=C["other"], zorder=3)
    for i, n in enumerate(names):
        ax.text(va[i] + 0.6, i - h / 2 - 0.02, f"{va[i]:.0f}% · {ca[n]}", va="center", fontsize=7,
                color=C["ink"], fontfamily=FONTS["mono"])
        ax.text(vb[i] + 0.6, i + h / 2 + 0.02, f"{vb[i]:.0f}% · {cb[n]}", va="center", fontsize=7,
                color=C["ink2"], fontfamily=FONTS["mono"])
    ax.set_yticks(y, names, fontsize=9, color=C["ink"])
    ax.invert_yaxis()
    ax.set_xlim(0, max(va + vb) * 1.22)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    style_ax(ax, "x")
    return fr.save("where-sold"), {"A": dict(ca), "A_n": na, "A_sold_online": oa, "B": dict(cb), "B_n": nb,
                                   "B_sold_online": ob}


def scan_stats() -> dict:
    per_recall = defaultdict(lambda: {"results": 0, "hits": set(), "keys": set()})
    unique_all, hit_all = {}, {}
    for s in D.searches:
        rn = s["recall_number"]
        ids = recall_ids(rn)
        pr = per_recall[rn]
        for it in s["items"]:
            pr["results"] += 1
            pr["keys"].add(it["key"])
            unique_all.setdefault(it["key"], it)
            if ids and find_ids_in_text(ids, it["title"]):
                pr["hits"].add(it["key"])
                hit_all.setdefault(it["key"], {**it, "recall_number": rn})
    rec = {r["recall_number"]: r for r in D.recalls}
    searched = len(per_recall)
    with_any = sum(1 for v in per_recall.values() if v["keys"])
    with_ids = sum(1 for rn in per_recall if recall_ids(rn))
    with_hit = sorted(rn for rn, v in per_recall.items() if v["hits"])
    kids_hit = [rn for rn in with_hit if rec.get(rn, {}).get("is_childrens")]
    sa = sum(1 for rn in per_recall if "A" in (rec.get(rn, {}).get("corpus") or []))
    return {"searches": len(D.searches), "recalls_searched": searched, "searched_A": sa,
            "searched_B_only": searched - sa, "recalls_with_results": with_any,
            "recalls_with_ids": with_ids, "results_total": sum(v["results"] for v in per_recall.values()),
            "unique_listings": len(unique_all), "per_recall_counts": [len(v["keys"]) for v in per_recall.values()],
            "recalls_with_exact_id_hit": len(with_hit), "childrens_recalls_with_exact_id_hit": len(kids_hit),
            "exact_id_hit_listings": len(hit_all),
            "exact_id_hits_by_recall": [{"recall_number": rn, "title": rec.get(rn, {}).get("title"),
                                         "is_childrens": bool(rec.get(rn, {}).get("is_childrens")),
                                         "hits": len(per_recall[rn]["hits"]),
                                         "ids": recall_ids(rn)} for rn in with_hit],
            "_unique": unique_all, "_hits": hit_all, "_rec": rec, "_per_recall": per_recall}


def chart_listings_per_recall(ss: dict):
    counts = ss["per_recall_counts"]
    bins = [(0, 0, "0"), (1, 9, "1-9"), (10, 24, "10-24"), (25, 49, "25-49"), (50, 10**6, "50+")]
    hist = [sum(lo <= c <= hi for c in counts) for lo, hi, _ in bins]
    n = ss["recalls_searched"]
    fr = Frame(4.7, "SerpApi eBay engine, one search per recall",
               f"{ss['unique_listings']:,} live eBay listings for {n} recalls; "
               f"{ss['recalls_with_exact_id_hit']} recalls have a listing that names the recalled number",
               f"{ss['searches']} searches ({ss['searched_A']} recalls since Jul 18 + {ss['searched_B_only']} older "
               f"children's recalls; _ipg=50, every response cached). Left: unique listings returned per "
               f"recall. Right: how many recalls get from 'searched' to a listing whose title contains a recalled "
               f"model number or UPC, exactly.",
               SRC_LINE,
               notes="Exact identifier in title (deterministic, not model): ml.regex_ids.find_ids_in_text of the "
                     "teacher spec's model numbers + UPCs against the listing title (case/separator-insensitive, "
                     "token-bounded). It includes accessories that name the model; a hit is a lead, not a verdict.")
    ax = fr.axes(rect=(0.75, fr.bottom + 0.42, 2.9, fr.top - fr.bottom - 0.62))
    ax.bar(range(len(bins)), hist, width=0.66, color=C["blue"], zorder=3)
    for i, v in enumerate(hist):
        ax.text(i, v + max(hist) * 0.02, str(v), ha="center", va="bottom", fontfamily=FONTS["notice"],
                fontweight=600, fontsize=10, color=C["ink"])
    ax.set_xticks(range(len(bins)), [b[2] for b in bins])
    ax.set_xlabel("unique listings returned per recall", fontsize=8.5)
    ax.set_ylabel("recalls", fontsize=8.5)
    ax.set_ylim(0, max(hist) * 1.15)
    style_ax(ax, "y")
    ax2 = fr.axes(rect=(5.55, fr.bottom + 0.42, 1.95, fr.top - fr.bottom - 0.62))
    steps = [("searched", n, C["other"]), ("returned ≥1 listing", ss["recalls_with_results"], C["other"]),
             ("spec has model no./UPC", ss["recalls_with_ids"], C["ink3"]),
             ("≥1 exact identifier in title", ss["recalls_with_exact_id_hit"], C["blue"])]
    for i, (lab, v, col) in enumerate(steps):
        ax2.barh(i, v, height=0.58, color=col, zorder=3)
        ax2.text(v + n * 0.02, i, str(v), va="center", fontfamily=FONTS["notice"], fontweight=700, fontsize=11,
                 color=C["ink"])
    ax2.set_yticks(range(len(steps)), [s[0] for s in steps], fontsize=8.2, color=C["ink"])
    ax2.invert_yaxis()
    ax2.set_xlim(0, n * 1.2)
    ax2.set_xlabel("recalls", fontsize=8.5)
    style_ax(ax2, "x")
    return fr.save("listings-per-recall"), {k: v for k, v in ss.items() if not k.startswith("_")} | {
        "histogram": {b[2]: hv for b, hv in zip(bins, hist)}}


def chart_condition_mix(ss: dict):
    order = ["New", "Open box", "Refurbished", "Pre-Owned", "For parts", "Not stated"]
    cols = {"New": C["other"], "Open box": C["other_l"], "Refurbished": C["blue_xl"], "Pre-Owned": C["blue"],
            "For parts": C["ink3"], "Not stated": "#efebe1", "Other": "#efebe1"}
    rec = ss["_rec"]
    groups = []
    allc = Counter(norm_condition(i["condition"]) for i in ss["_unique"].values())
    groups.append((f"All unique listings ({sum(allc.values()):,})", allc))
    kids_keys = set()
    adult_keys = set()
    for rn, v in ss["_per_recall"].items():
        (kids_keys if rec.get(rn, {}).get("is_childrens") else adult_keys).update(v["keys"])
    kc = Counter(norm_condition(ss["_unique"][k]["condition"]) for k in kids_keys)
    groups.append((f"Listings for children's recalls ({sum(kc.values()):,})", kc))
    hc = Counter(norm_condition(i["condition"]) for i in ss["_hits"].values())
    groups.append((f"Exact identifier in title ({sum(hc.values())})", hc))
    pre = {g: 100 * c["Pre-Owned"] / max(sum(c.values()), 1) for g, c in groups}
    g0, g1, g2 = (g for g, _ in groups)
    fr = Frame(4.3, "Listing condition, as eBay reports it",
               f"{pre[g0]:.0f}% of the listings are pre-owned; {pre[g1]:.0f}% for children's recalls",
               "Most search results are new stock from marketplace sellers. The resale risk sits in the pre-owned "
               "slice, and in new-old stock that names the recalled model number outright (bottom row).",
               SRC_LINE, notes="Condition strings normalized: New = Brand New / New (Other) / New without box or "
                               "tags; Open box includes 'New - Open box'; Refurbished includes Certified/Excellent/"
                               "Very Good. Exact identifier hits: deterministic title match, not a model verdict.")
    present = [o for o in order if any(c[o] for _, c in groups)]
    legend_row(fr, [(cols[o], o) for o in present], fr.top - 0.05)
    ax = fr.axes(left=2.55, right=0.5, top_pad=0.32, bottom_pad=0.38)
    for yi, (lab, c) in enumerate(groups):
        tot = max(sum(c.values()), 1)
        left = 0
        for o in present:
            pct = 100 * c[o] / tot
            if pct <= 0:
                continue
            ax.barh(yi, pct, left=left, height=0.66, color=cols[o], edgecolor=C["bg"], lw=1.6, zorder=3)
            if pct >= 5:
                ax.text(left + pct / 2, yi, f"{pct:.0f}%", ha="center", va="center", fontsize=8.5,
                        fontfamily=FONTS["notice"], fontweight=700,
                        color="white" if o in ("Pre-Owned", "For parts") else C["ink"])
            left += pct
    ax.set_yticks(range(len(groups)), [g for g, _ in groups], fontsize=8.6, color=C["ink"])
    ax.set_ylim(len(groups) - 0.5, -0.5)
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    style_ax(ax, "x")
    ax.xaxis.grid(False)
    return fr.save("condition-mix"), {"all": dict(allc), "childrens": dict(kc), "exact_id_hits": dict(hc),
                                      "pre_owned_pct": {g: round(v, 1) for g, v in pre.items()}}


HAZ_TITLE = ""
HAZARDS = [
    ("Fire / burn", r"\bfire\b|\bburns?\b|overheat|thermal burn|scald"),
    ("Fall / tip-over", r"\bfall\b|falls\b|tip[- ]?over|collapse"),
    ("Entrapment / suffocation / strangulation", r"entrap|suffocat|asphyx|strangulat"),
    ("Choking", r"chok"),
    ("Ingestion (magnets, batteries, beads)", r"ingest|swallow|magnet|button batter|coin batter"),
    ("Laceration / cut", r"lacerat|\bcuts?\b|amputat"),
    ("Impact / projectile / crush", r"impact|projectile|crush|pinch|struck"),
    ("Electric shock", r"shock|electrocut"),
    ("Poisoning / chemical (lead, phthalates)", r"poison|\blead\b|phthalat|chemical|toxic|methanol|child[- ]resistant"),
    ("Drowning", r"drown"),
    ("Carbon monoxide", r"carbon monoxide|\bco poisoning"),
]


def chart_hazard_types(_):
    k_c, o_c = Counter(), Counter()
    for r in D.A:
        title_hz = (r.get("title") or "").split(" Due to ", 1)[-1] if " Due to " in (r.get("title") or "") else ""
        t = " ".join(r.get("hazards") or []) + " " + title_hz
        for name, pat in HAZARDS:
            if re.search(pat, t, re.I):
                (k_c if r.get("is_childrens") else o_c)[name] += 1
    names = sorted([n for n, _ in HAZARDS if k_c[n] + o_c[n]], key=lambda n: -(k_c[n] + o_c[n]))
    n = len(D.A)
    top = names[0] if names else ""
    kid_top = sorted(names, key=lambda x: -k_c[x])[:2]
    global HAZ_TITLE
    HAZ_TITLE = (f"{top.split(' /')[0]} leads ({k_c[top] + o_c[top]} of {n}); children's recalls skew to "
                 f"{kid_top[0].split(' (')[0].lower()} and {kid_top[1].split(' (')[0].lower()}") if names else ""
    fr = Frame(5.8, "What the recalls are for",
               HAZ_TITLE,
               f"Hazard categories across the {n} recalls since {SINCE_A}, by keyword buckets on CPSC's Hazard text "
               f"and the title's 'Due to ...' clause. One recall can carry several hazards.",
               CPSC_LINE, notes="Buckets (regex, case-insensitive): " + "; ".join(
                   f"{nm.split(' (')[0]}" for nm, _ in HAZARDS) + ". Generic 'risk of serious injury' wording is not "
                                                               "counted on its own.")
    legend_row(fr, [(C["blue"], "Children's products"), (C["other"], "Other products")], fr.top - 0.05)
    ax = fr.axes(left=2.85, right=0.6, top_pad=0.3, bottom_pad=0.38)
    y = range(len(names))
    kv = [k_c[x] for x in names]
    ov = [o_c[x] for x in names]
    ax.barh(list(y), kv, height=0.7, color=C["blue"], edgecolor=C["bg"], lw=1.2, zorder=3)
    ax.barh(list(y), ov, left=kv, height=0.7, color=C["other"], edgecolor=C["bg"], lw=1.2, zorder=3)
    for i in y:
        ax.text(kv[i] + ov[i] + 0.8, i, f"{kv[i] + ov[i]}", va="center", fontfamily=FONTS["notice"], fontweight=700,
                fontsize=10, color=C["ink"])
        if kv[i] >= 3:
            ax.text(kv[i] / 2, i, str(kv[i]), va="center", ha="center", fontsize=8, color="white",
                    fontfamily=FONTS["notice"], fontweight=600)
    ax.set_yticks(list(y), names, fontsize=8.6, color=C["ink"])
    ax.invert_yaxis()
    ax.set_xlim(0, max(a + b for a, b in zip(kv, ov)) * 1.12)
    ax.set_xlabel("recalls", fontsize=8.5)
    style_ax(ax, "x")
    return fr.save("hazard-types"), {"n": n, "childrens": dict(k_c), "other": dict(o_c), "top": top}


# ================================================================================================ charts g (results)
def eval_source(P: dict):
    ev = load_json(RES / "eval.json")
    if not ev or ev.get("placeholder") or not any(m.get("acc") is not None and not m.get("pending")
                                                  for m in ev.get("models", [])):
        return {"models": P["models"], "confusion": P["confusion"], "paired": P["paired"], "test_size": 220,
                "training": P["training"], "gold": "placeholder"}, "placeholder"
    st = "provisional" if answer_key(ev) == "teacher" else "real"  # teacher + rule 7 = the final answer key
    ev["models"] = [m for m in ev["models"] if m.get("acc") is not None and not m.get("pending")]
    return ev, st


ROLE_ORDER = ["lora", "teacher", "base_guided", "base", "heuristic"]


def short_name(m: dict) -> str:
    r = m.get("role", "")
    return {"lora": "Qwen3.5-4B + LoRA", "teacher": "Qwen3.5-397B (teacher)", "base_guided": "4B base + rulebook",
            "base": "Qwen3.5-4B base", "heuristic": "Rules (no model)"}.get(
        r, (m.get("name") or r).replace("backboard:", "")[:28])


def ordered_models(ev):
    ms = ev["models"]
    return sorted(ms, key=lambda m: (ROLE_ORDER.index(m["role"]) if m["role"] in ROLE_ORDER else 99, m["role"]))


def frac(s) -> tuple[int, int]:
    try:
        a, b = str(s).split("/")
        return int(a), int(b)
    except Exception:  # noqa: BLE001
        return 0, 0


def answer_key(ev) -> str:
    g = str((ev or {}).get("gold", "")).lower()
    return "human" if g.startswith("human") else "targets" if "rule 7" in g else "teacher" if "teacher" in g else "none"


def res_src(st, files):
    if st == "placeholder":
        return f"Source: {files} (RecallDesk); answer key: none yet"
    key = answer_key(load_json(RES / "eval.json"))
    return f"Source: {files} (RecallDesk); answer key: " + {
        "human": "blind human labels", "targets": "teacher + rule 7 (code), not human",
        "teacher": "raw teacher labels, not human"}.get(key, "n/a")


def chart_results_bars(P):
    ev, st = eval_source(P)
    ms = ordered_models(ev)
    n = ev.get("test_size")
    lora = next((m for m in ms if m["role"] == "lora"), None)
    base = next((m for m in ms if m["role"] == "base"), None)
    title = (f"Fine-tuning moved the 4B from {100 * base['acc']:.0f}% to {100 * lora['acc']:.0f}% accuracy"
             if lora and base else "Decision accuracy on held-out pairs")
    fr = Frame(4.4, f"match / check / no_match on {n} held-out pairs", title,
               "Accuracy with 95% bootstrap CI (10,000 resamples) on recalls never seen in training, one attempt at "
               "temperature 0 per pair. Macro-F1 at right.",
               res_src(st, "ml/results/eval.json"), status=st)
    ax = fr.axes(left=1.95, right=0.95, top_pad=0.05, bottom_pad=0.38)
    for i, m in enumerate(ms):
        col = C["blue"] if m["role"] == "lora" else C["other"]
        ax.barh(i, 100 * m["acc"], height=0.58, color=col, zorder=3)
        lo, hi = (m.get("acc_ci") or [m["acc"], m["acc"]])
        ax.plot([100 * lo, 100 * hi], [i, i], color=C["ink"], lw=1.2, zorder=4)
        for xv in (lo, hi):
            ax.plot([100 * xv] * 2, [i - 0.12, i + 0.12], color=C["ink"], lw=1.2, zorder=4)
        ax.text(100 * hi + 1.2, i, f"{100 * m['acc']:.1f}%", va="center", fontfamily=FONTS["notice"],
                fontweight=700, fontsize=11, color=C["ink"])
        if m.get("macro_f1") is not None:
            ax.text(1.0, i, f"F1 {m['macro_f1']:.2f}", transform=ax.get_yaxis_transform(), va="center", ha="left",
                    fontfamily=FONTS["mono"], fontsize=7.6, color=C["ink2"])
    ax.set_yticks(range(len(ms)), [short_name(m) for m in ms], fontsize=9, color=C["ink"])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    style_ax(ax, "x")
    return fr.save("results-bars"), {"status": st}


def chart_risky_units(P):
    ev, st = eval_source(P)
    conf = ev.get("confusion") or {}
    roles = [r for r in ("base", "base_guided", "lora", "teacher") if (conf.get(r) or {}).get("matrix")]
    if not roles:
        roles = ["base", "lora"]
        conf = P["confusion"]
        st = "placeholder"
    names = {m["role"]: short_name(m) for m in ev["models"]}
    rows = []
    for r in roles:
        m = conf[r]["matrix"]
        rows.append((r, [("match", m[0][0] + m[0][1], m[0][2]), ("check", m[1][0] + m[1][1], m[1][2])]))
    tot = sum(c + x for _, c, x in rows[0][1])
    cols = min(40, max(10, tot // 3 + 1))
    lines = sum(-(-(c + x) // cols) for _, c, x in rows[0][1])
    sq = min(0.155, 6.0 / cols)
    h = 2.15 + len(rows) * (lines * sq + 0.5) + 0.55
    lr = next((x for x in rows if x[0] == "lora"), rows[-1])
    br = next((x for x in rows if x[0] == "base"), rows[0])
    caught = lambda row: sum(c for _, c, _ in row[1])  # noqa: E731
    fr = Frame(h, "Risky = the answer key says match or check",
               f"Risky listings caught: {caught(br)} of {tot} for the base 4B, {caught(lr)} of {tot} after fine-tuning",
               "Each square is one held-out pair the answer key (teacher + rule 7 by code) calls match (red) or "
               "check (amber). Filled = the model "
               "flagged it (match or check); hollow = the model cleared it, the miss that puts stock on a shelf.",
               res_src(st, "ml/results/eval.json confusion"), status=st)
    legend_row(fr, [(C["stop"], "key match, flagged"), (C["amber"], "key check, flagged"),
                    (C["bg"], "hollow = cleared (missed)")], fr.top - 0.05)
    y = fr.top - 0.4
    for role, parts in rows:
        fr.fig.text(0.5 / W, y / fr.h, f"{names.get(role, role)}   {sum(c for _, c, _ in parts)}/{tot}",
                    fontsize=9, fontweight=600, color=C["ink"], va="top")
        y -= 0.26
        ax = fr.fig.add_axes([0.5 / W, 0, 1, 1], frameon=False)
        ax.set_axis_off()
        ax.set_xlim(0, W)
        ax.set_ylim(0, fr.h)
        ax.set_position([0, 0, 1, 1])
        idx = 0
        for lab, c, x in parts:
            col = C["stop"] if lab == "match" else C["amber"]
            for k in range(c + x):
                cx = 0.5 + (idx % cols) * sq
                cy = y - (idx // cols) * sq
                filled = k < c
                ax.add_patch(Rectangle((cx, cy - sq * 0.84), sq * 0.84, sq * 0.84, fc=col if filled else C["bg"],
                                       ec=col, lw=0.9))
                idx += 1
            idx = -(-idx // cols) * cols  # new line per gold class
        y -= (idx // cols) * sq + 0.2
    return fr.save("risky-caught-units"), {"status": st}


def chart_confusion_pair(P):
    ev, st = eval_source(P)
    conf = ev.get("confusion") or {}
    a, b = "base", "lora"
    if not ((conf.get(a) or {}).get("matrix") and (conf.get(b) or {}).get("matrix")):
        conf, st = P["confusion"], "placeholder"
    fr = Frame(4.5, "Confusion matrices, same held-out pairs", "Where the base 4B and the LoRA disagree with the answer key",
               "Rows = answer key (teacher + rule 7 by code), columns = model verdict. The top-right cells (risky listing cleared as no_match) "
               "are the expensive mistake; the bottom-left ones cost a look at a sticker.",
               res_src(st, "ml/results/eval.json confusion"), status=st)
    import numpy as np  # noqa: PLC0415
    names = {m["role"]: short_name(m) for m in ev["models"]}
    for k, role in enumerate((a, b)):
        m = np.array(conf[role]["matrix"])
        ax = fr.axes(rect=(1.3 + k * 3.55, fr.bottom + 0.35, 2.5, fr.top - fr.bottom - 0.75))
        mx = m.max() or 1
        for i in range(3):
            for j in range(3):
                v = m[i, j]
                shade = matplotlib.colors.to_rgb(C["blue"])
                al = 0.08 + 0.85 * v / mx
                fc = tuple(1 - al * (1 - s) for s in shade)
                ax.add_patch(Rectangle((j, 2 - i), 0.96, 0.96, fc=fc, ec=(C["stop"] if j == 2 and i < 2 else "none"),
                                       lw=1.6 if j == 2 and i < 2 else 0))
                ax.text(j + 0.48, 2 - i + 0.48, str(v), ha="center", va="center", fontfamily=FONTS["notice"],
                        fontweight=700, fontsize=14, color="white" if al > 0.55 else C["ink"])
        ax.set_xlim(0, 3)
        ax.set_ylim(0, 3)
        ax.set_xticks([0.48, 1.48, 2.48], LABELS, fontsize=8.5)
        ax.set_yticks([2.48, 1.48, 0.48], LABELS if k == 0 else ["", "", ""], fontsize=8.5)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(names.get(role, role), fontsize=10, fontweight=600, color=C["ink"], loc="left")
        ax.set_xlabel("model verdict", fontsize=8)
        if k == 0:
            ax.set_ylabel("answer key", fontsize=8)
    return fr.save("confusion-pair"), {"status": st}


def chart_cost(P):
    ev, st = eval_source(P)
    ms = [m for m in ordered_models(ev) if m.get("cost_per_1k_usd") is not None]
    fr = Frame(3.9, "Price of reading 1,000 listings", "What one weekly pass costs per 1,000 listings",
               "Tokens x Tinker list price (models.json, 2026-10-17), averaged over the held-out pairs. The rules "
               "baseline costs nothing and catches less.",
               res_src(st, "ml/results/eval.json"), status=st)
    ax = fr.axes(left=1.95, right=0.8, top_pad=0.05, bottom_pad=0.38)
    mx = max([m["cost_per_1k_usd"] for m in ms] + [0.01])
    for i, m in enumerate(ms):
        v = m["cost_per_1k_usd"]
        ax.barh(i, v, height=0.58, color=C["blue"] if m["role"] == "lora" else C["other"], zorder=3)
        ax.text(v + mx * 0.015, i, f"${v:.3f}" if v < 0.1 else f"${v:.2f}", va="center", fontfamily=FONTS["notice"],
                fontweight=700, fontsize=11, color=C["ink"])
    ax.set_yticks(range(len(ms)), [short_name(m) for m in ms], fontsize=9, color=C["ink"])
    ax.invert_yaxis()
    ax.set_xlim(0, mx * 1.18)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:.2f}"))
    style_ax(ax, "x")
    return fr.save("cost-per-1k"), {"status": st}


def chart_loss(P):
    tl = load_json(RES / "training.json")
    st = "real"
    if not tl or tl.get("placeholder") or not tl.get("loss_curve"):
        ev, est = eval_source(P)
        tl = ev.get("training") if est != "placeholder" and (ev.get("training") or {}).get("loss_curve") else None
        st = est if tl else "placeholder"
        if tl is None:
            tl = P["training"]
    lc, tn = tl.get("loss_curve") or [], tl.get("test_nll") or []
    fr = Frame(4.2, f"LoRA rank {tl.get('rank')} on {tl.get('base_model')}",
               f"Training loss over {tl.get('steps') or len(lc)} steps, held-out NLL per epoch",
               "Loss on the JSON verdict tokens only (teacher targets). Held-out NLL is on the test pairs' teacher "
               "targets at step 0 and after each epoch; final-epoch weights are evaluated, not picked by test loss.",
               "Source: ml/results/training.json (RecallDesk, Tinker forward_backward / optim_step)", status=st)
    legend_row(fr, [(C["s1"], "train loss (per step)"), (C["s2"], "held-out NLL (per epoch)")], fr.top - 0.05)
    ax = fr.axes(left=0.8, right=0.5, top_pad=0.3, bottom_pad=0.42)
    if lc:
        ax.plot([p[0] for p in lc], [p[1] for p in lc], color=C["s1"], lw=1.6, zorder=3)
    if tn:
        ax.plot([p[0] for p in tn], [p[1] for p in tn], color=C["s2"], lw=2, marker="o", ms=5,
                markeredgecolor=C["bg"], markeredgewidth=1.5, zorder=4)
        for p in (tn[0], tn[-1]):
            ax.annotate(f"{p[1]:.3f}", (p[0], p[1]), textcoords="offset points", xytext=(4, 6), fontsize=8,
                        fontfamily=FONTS["mono"], color=C["ink"])
    ax.set_xlabel("step", fontsize=8.5)
    ax.set_ylabel("nats / token", fontsize=8.5)
    ax.set_ylim(bottom=0)
    style_ax(ax, "y")
    return fr.save("loss-curve"), {"status": st}


def chart_latency(P):
    ev, st = eval_source(P)
    ms = [m for m in ordered_models(ev) if m.get("p50_latency_ms") is not None and m.get("role") != "heuristic"]
    fr = Frame(3.9, "Per-pair latency through Tinker's hosted sampler", "How long one verdict takes",
               "Dot = median (p50), bar end = p95, per pair, single request at temperature 0. No local serving was "
               "timed; the exported PEFT adapter would change these numbers.",
               res_src(st, "ml/results/eval.json"), status=st)
    ax = fr.axes(left=1.95, right=0.8, top_pad=0.05, bottom_pad=0.4)
    mx = 1
    for i, m in enumerate(ms):
        p50 = m["p50_latency_ms"] / 1000
        p95 = (m.get("p95_latency_ms") or m["p50_latency_ms"]) / 1000
        mx = max(mx, p95)
        col = C["blue"] if m["role"] == "lora" else C["ink3"]
        ax.plot([0, p95], [i, i], color=C["grid"], lw=4, solid_capstyle="round", zorder=2)
        ax.plot([p50, p95], [i, i], color=col, lw=2, zorder=3, alpha=0.5)
        ax.plot([p50], [i], "o", color=col, ms=8, markeredgecolor=C["bg"], markeredgewidth=1.5, zorder=4)
        ax.text(p95 + 0.05, i, f"p50 {p50:.2f}s · p95 {p95:.2f}s", va="center", fontsize=7.8,
                fontfamily=FONTS["mono"], color=C["ink"])
    ax.set_yticks(range(len(ms)), [short_name(m) for m in ms], fontsize=9, color=C["ink"])
    ax.invert_yaxis()
    ax.set_xlim(0, mx * 1.45)
    ax.set_xlabel("seconds per pair", fontsize=8.5)
    style_ax(ax, "x")
    return fr.save("latency"), {"status": st}


def chart_flagged_by_recall(P):
    sc = load_json(RES / "scan_summary.json")
    st = "real"
    if not sc or sc.get("placeholder") or not sc.get("by_recall"):
        sc, st = P["scan"], "placeholder"
    top = sorted([b for b in sc["by_recall"] if b.get("match", 0) + b.get("check", 0) > 0],
                 key=lambda b: (-b.get("match", 0), -b.get("check", 0)))[:12]
    rec = {r["recall_number"]: r for r in D.recalls}

    def label(b):
        t = b.get("title") or ""
        t = re.sub(r"\s+(?:Due to|Recalled Due|Because).*$", "", t)
        t = re.sub(r"^.*?\bRecalls?\s+", "", t)
        return (t[:46] + "…") if len(t) > 47 else t

    fr = Frame(1.9 + 0.29 * max(len(top), 4) + 0.9, "Model verdicts on live eBay listings",
               f"{sc.get('flagged_match', 0)} DO NOT SELL and {sc.get('flagged_check', 0)} CHECK LABEL flags across "
               f"{sc.get('listings_seen', 0):,} listings",
               f"Top recalls by flagged listings (classifier: {(sc.get('classifier') or {}).get('model', 'n/a')}). "
               "Flags are model verdicts, not confirmed recalls; " + (
                   f"{sc.get('human_verified_match', 0)} of {sc['human_reviewed_flags']} reviewed were confirmed by a "
                   "human." if sc.get("human_reviewed_flags") else "no human review yet (human_verified = 0)."),
               "Source: ml/results/scan_summary.json (RecallDesk) over SerpApi eBay results, fetched 2026-10-17",
               status=st, notes="● = children's product recall.")
    legend_row(fr, [(C["stop"], "DO NOT SELL (match)"), (C["amber"], "CHECK LABEL (check)")], fr.top - 0.05)
    ax = fr.axes(left=3.4, right=0.6, top_pad=0.3, bottom_pad=0.38)
    for i, b in enumerate(top):
        m, c = b.get("match", 0), b.get("check", 0)
        ax.barh(i, m, height=0.6, color=C["stop"], edgecolor=C["bg"], lw=1.2, zorder=3)
        ax.barh(i, c, left=m, height=0.6, color=C["amber"], edgecolor=C["bg"], lw=1.2, zorder=3)
        ax.text(m + c + 0.3, i, f"{m} / {c}", va="center", fontsize=8, fontfamily=FONTS["mono"], color=C["ink"])
    kids = [bool(b.get("is_childrens", rec.get(b.get("recall_number"), {}).get("is_childrens"))) for b in top]
    ax.set_yticks(range(len(top)), [("● " if k else "") + label(b) for b, k in zip(top, kids)], fontsize=8.2,
                  color=C["ink"])
    ax.invert_yaxis()
    ax.set_xlim(0, max([b.get("match", 0) + b.get("check", 0) for b in top] + [1]) * 1.15)
    ax.set_xlabel("flagged listings", fontsize=8.5)
    style_ax(ax, "x")
    return fr.save("flagged-by-recall"), {"status": st}


def chart_label_distribution(P):
    # The answer key the reported numbers use: eval.json gold_dist (teacher + rule 7 by code on the test pairs).
    # Human labels from ml.label_ui (data/gold/labels.jsonl) are only used if eval.json was graded against them.
    ev = load_json(RES / "eval.json") or {}
    key = answer_key(ev)
    cnt, st = Counter(), "placeholder"
    if key == "human":
        last = {}
        for g in read_jsonl(DATA / "gold" / "labels.jsonl"):  # last label per pair wins (undo/relabel)
            if g.get("label") in LABELS:
                last[g["pair_id"]] = g
        cnt = Counter(g["label"] for g in last.values())
    elif ev.get("gold_dist") and not ev.get("placeholder"):
        cnt = Counter({k: int(v) for k, v in ev["gold_dist"].items()})
    if sum(cnt.values()):
        st = "real" if key in ("human", "targets") else "provisional"
    else:
        cnt = Counter({"match": 40, "check": 60, "no_match": 120})
    title, how, src = {
        "human": ("The answer key: blind human labels on held-out pairs",
                  "Labelled one at a time with keys 1/2/3 in ml.label_ui, no model output on screen.",
                  "Source: data/gold/labels.jsonl (RecallDesk label UI)"),
        "teacher": ("The answer key: raw teacher labels on held-out pairs",
                    "Qwen3.5-397B-A17B teacher labels, before rule 7 is enforced. Not human labels.",
                    "Source: ml/results/eval.json gold_dist (RecallDesk)"),
    }.get(key, ("The answer key: teacher + rule 7 (code) on held-out pairs",
                "Qwen3.5-397B-A17B teacher labels with LABELING.md rule 7 enforced by code (ml/enforce_rules.py), "
                "the same definition as the training targets. No human labels were collected.",
                "Source: ml/results/eval.json gold_dist <- data/labeled/targets.jsonl (RecallDesk)"))
    note = ("Illustrative counts until ml/results/eval.json exists." if st == "placeholder" else
            "Not human: the blind label UI (ml.label_ui) exists for an audit but was not used." if key != "human" else "")
    n = sum(cnt.values())
    fr = Frame(3.6, title,
               f"{n} test pairs: {cnt['match']} match, {cnt['check']} check, {cnt['no_match']} no_match",
               how + " Card action: match = DO NOT SELL, check = CHECK LABEL, no_match = not shown.",
               src, status=st, notes=note)
    ax = fr.axes(left=1.5, right=0.8, top_pad=0.05, bottom_pad=0.38)
    rows = [("match", "DO NOT SELL", C["stop"]), ("check", "CHECK LABEL", C["amber"]), ("no_match", "clear", C["clear"])]
    for i, (lab, act, col) in enumerate(rows):
        v = cnt[lab]
        ax.barh(i, v, height=0.58, color=col, zorder=3)
        ax.text(v + n * 0.01, i, f"{v}  ({100 * v / max(n, 1):.0f}%)", va="center", fontfamily=FONTS["notice"],
                fontweight=700, fontsize=11, color=C["ink"])
    ax.set_yticks(range(3), [f"{lab}  → {act}" for lab, act, _ in rows], fontsize=8.8, color=C["ink"])
    ax.invert_yaxis()
    ax.set_xlim(0, max(cnt.values()) * 1.25)
    ax.set_xlabel("test pairs", fontsize=8.5)
    style_ax(ax, "x")
    return fr.save("label-distribution"), {"status": st, "counts": dict(cnt)}


# ================================================================================================ main
def main(argv: list[str]) -> None:
    load_fonts()
    load_data()
    P = placeholder_values()
    ss = scan_stats()
    stats = load_json(DATA / "recalls" / "stats.json") or {}
    charts = {
        "recalls-per-thursday": lambda: chart_recalls_per_thursday(stats),
        "ids-buried": lambda: chart_ids_buried(None),
        "where-sold": lambda: chart_where_sold(stats),
        "listings-per-recall": lambda: chart_listings_per_recall(ss),
        "condition-mix": lambda: chart_condition_mix(ss),
        "hazard-types": lambda: chart_hazard_types(None),
        "results-bars": lambda: chart_results_bars(P),
        "risky-caught-units": lambda: chart_risky_units(P),
        "confusion-pair": lambda: chart_confusion_pair(P),
        "cost-per-1k": lambda: chart_cost(P),
        "loss-curve": lambda: chart_loss(P),
        "latency": lambda: chart_latency(P),
        "flagged-by-recall": lambda: chart_flagged_by_recall(P),
        "label-distribution": lambda: chart_label_distribution(P),
    }
    names = argv or list(charts)
    data_p = OUT / "chart_data.json"
    summary = load_json(data_p) or {}
    summary["fonts"] = FONTS
    for name in names:
        p, info = charts[name]()
        st = (info or {}).get("status", "real")
        summary[name] = {"status": st, **(info or {})}
        print(f"{p.name}" + ("" if st == "real" else f"  [{st.upper()}]"))
    summary["generated_from"] = {"recalls": len(D.recalls), "specs": len(D.specs), "searches": len(D.searches)}
    data_p.write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"wrote {data_p.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main(sys.argv[1:])
