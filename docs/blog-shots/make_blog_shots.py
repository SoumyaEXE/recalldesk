"""RecallDesk blog figures that stand in for dashboard screenshots -> docs/blog-shots/*.png (Pillow).

    python docs/blog-shots/make_blog_shots.py            # all eight
    python docs/blog-shots/make_blog_shots.py ebay-1440  # one

Only the file names the blog links to are written:
    home-card-1440  overview-1440  inventory-drawer-1440  recalls-expanded-1440  ebay-1440  billing-1440
    temporal-crash-timeline-chart  runs-crash-1440

Every value is read from the repo, never typed in: the published card and run records (shared/fixtures/), the inventory
CSV (agent/fixtures_src/), CPSC recalls and teacher specs (data/), the eBay listings (data/listings/), the chart numbers
(docs/charts/chart_data.json) and the crash rehearsal log (agent/demo_logs/heuristic/04_crash_resume.txt).

Look: a federal consumer-safety report, not a product dashboard. Colors are U.S. Web Design System (USWDS) system
tokens; type is the USWDS set: Merriweather for titles, Public Sans for text, Roboto Mono for identifiers. Figures
follow editorial chart practice: the title states the finding, a subtitle gives the scope, a source line closes it.
The printable card follows CPSC's recall-poster guidance: the hazard, what to do, and the identifiers called out.
Fonts: docs/blog-shots/fonts (Merriweather, OFL; Roboto Mono, Apache 2.0; from Fontsource) and
docs/charts/fonts (Public Sans, OFL). No product photos and no seller names: listings show only the hashed seller id.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from ml.regex_ids import find_ids_in_text  # noqa: E402

FIX = ROOT / "shared" / "fixtures"
DATA = ROOT / "data"
CRASH_LOG = ROOT / "agent" / "demo_logs" / "heuristic" / "04_crash_resume.txt"

# ------------------------------------------------------------------------------------------------ tokens (USWDS)
C = dict(
    bg="#ffffff", ink="#1b1b1b", ink2="#565c65", ink3="#71767a", rule="#dfe1e2", rule2="#a9aeb1", wash="#f1f3f6",
    navy="#162e51", navy2="#1a4480", link="#005ea2", teal="#00687d", teal_xl="#e7f6f8",
    red="#b50909", red_xl="#f8e1de", gold="#e5a000", gold_xl="#faf3d1", gold_ink="#5c410a",
    green="#216e1f", green_xl="#e3f5e1", id_bg="#faf3d1", id_line="#c2850c",
)
W = 1600  # 2x of an 800 css-px blog column, same as docs/charts
M = 96    # side margin
CW = W - 2 * M

_FONTS: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_FILES = {
    "sans": ROOT / "docs/charts/fonts/PublicSans-400.ttf", "sans6": ROOT / "docs/charts/fonts/PublicSans-600.ttf",
    "sans7": ROOT / "docs/charts/fonts/PublicSans-700.ttf",
    "serif": HERE / "fonts/Merriweather-400.ttf",
    "serif7": HERE / "fonts/Merriweather-700.ttf",
    "mono": HERE / "fonts/RobotoMono-400.ttf", "mono5": HERE / "fonts/RobotoMono-500.ttf",
}


def F(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key not in _FONTS:
        try:
            _FONTS[key] = ImageFont.truetype(str(_FILES[kind]), size)
        except OSError:
            _FONTS[key] = ImageFont.truetype("DejaVuSansMono.ttf" if kind.startswith("mono") else "DejaVuSans.ttf",
                                             size)
    return _FONTS[key]


# ------------------------------------------------------------------------------------------------ io
def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


class D:
    card: dict = {}
    runs: list[dict] = []
    recalls: dict[str, dict] = {}
    specs: dict[str, dict] = {}
    inventory: list[dict] = []
    charts: dict = {}


def load() -> None:
    D.card = load_json(FIX / "card_little-loop.json")
    D.runs = load_json(FIX / "runs.json")
    D.recalls = {r["recall_number"]: r for r in read_jsonl(DATA / "recalls" / "recalls.jsonl")}
    D.specs = {s["recall_number"]: s for s in read_jsonl(DATA / "specs" / "specs.jsonl")}
    with open(ROOT / "agent" / "fixtures_src" / "little_loop_inventory.csv", encoding="utf-8") as f:
        D.inventory = list(csv.DictReader(f))
    D.charts = load_json(ROOT / "docs" / "charts" / "chart_data.json")


def product_name(rn: str) -> str:
    r = D.recalls.get(rn, {})
    return (r.get("product_names") or [r.get("title", "")])[0].replace("™", "")


def spec_ids(rn: str) -> list[str]:
    s = D.specs.get(rn, {})
    other = [t for o in s.get("other_identifiers", []) for t in re.findall(r"[A-Za-z0-9/-]*\d[A-Za-z0-9/-]*", o)
             if len(t) >= 4]
    return [*s.get("model_numbers", []), *s.get("upcs", []), *other]


def fmt_date(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}, {d.year}"


def fmt_month(ym: str) -> str:
    return datetime.strptime(ym, "%Y-%m").strftime("%b %Y")


# ------------------------------------------------------------------------------------------------ drawing
def tw(text: str, font) -> int:
    return int(font.getlength(text))


def wrap(text: str, font, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if tw(trial, font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def clip(text: str, font, width: int) -> str:
    if tw(text, font) <= width:
        return text
    while text and tw(text + "…", font) > width:
        text = text[:-1]
    return text.rstrip(" ,;·-") + "…"


def wrap_clip(text: str, font, width: int, max_lines: int) -> list[str]:
    lines = wrap(text, font, width)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [clip(" ".join(lines[max_lines - 1:]), font, width)]
    return lines


def spaced(d, xy, text, font, fill, track=1.5, anchor="la") -> int:
    """Letter-spaced caps (Pillow has no tracking); returns the width drawn."""
    x, y = xy
    total = sum(tw(ch, font) for ch in text) + track * (len(text) - 1)
    if anchor == "ra":
        x -= total
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += tw(ch, font) + track
    return int(total)


def caps(d, x, y, text, color=None, size=14, anchor="la") -> int:
    return spaced(d, (x, y), text.upper(), F("sans6", size), color or C["ink2"], track=1.4, anchor=anchor)


class Page:
    """Editorial figure: kicker, title (the finding), subtitle (the scope), content, notes, source line."""

    def __init__(self, kicker: str, title: str, sub: str, source: str, height: int = 7000):
        self.im = Image.new("RGB", (W, height), C["bg"])
        self.d = ImageDraw.Draw(self.im)
        self.source = source
        d = self.d
        d.rectangle([0, 0, W, 8], fill=C["navy"])
        y = 56
        caps(d, M, y, kicker, C["navy2"], 16)
        y += 40
        title = title.replace("'", "’")  # Merriweather's straight quote reads as a prime at display size
        size = 42
        lines = wrap(title, F("serif7", size), CW)
        while len(lines) > 1 and size > 34:
            size -= 2
            lines = wrap(title, F("serif7", size), CW)
        for line in lines:
            d.text((M, y), line, font=F("serif7", size), fill=C["ink"])
            y += int(size * 1.4)
        y += 10
        for line in wrap(sub, F("sans", 21), CW - 120):
            d.text((M, y), line, font=F("sans", 21), fill=C["ink2"])
            y += 34
        self.y = y + 34

    def finish(self, name: str, notes: str = "") -> Path:
        d = self.d
        y = self.y + 40
        for line in wrap(notes, F("sans", 16), CW):
            d.text((M, y), line, font=F("sans", 16), fill=C["ink2"])
            y += 26
        y += 14
        d.line([(M, y), (W - M, y)], fill=C["rule2"], width=1)
        y += 18
        d.text((M, y), self.source, font=F("sans", 15), fill=C["ink3"])
        d.text((W - M, y), "RecallDesk", font=F("sans7", 15), fill=C["navy"], anchor="ra")
        y += 54
        p = HERE / f"{name}.png"
        self.im.crop((0, 0, W, y)).save(p, optimize=True)
        print(f"wrote {p.relative_to(ROOT)}  ({W}x{y})")
        return p


def box(d, x, y, w, h, fill=None, outline=None, width=1, dash=False):
    if dash:
        if fill:
            d.rectangle([x, y, x + w, y + h], fill=fill)
        col = outline or C["rule2"]
        for xx in range(x, x + w, 14):
            d.line([(xx, y), (min(xx + 7, x + w), y)], fill=col, width=width)
            d.line([(xx, y + h), (min(xx + 7, x + w), y + h)], fill=col, width=width)
        for yy in range(y, y + h, 14):
            d.line([(x, yy), (x, min(yy + 7, y + h))], fill=col, width=width)
            d.line([(x + w, yy), (x + w, min(yy + 7, y + h))], fill=col, width=width)
        return
    d.rectangle([x, y, x + w, y + h], fill=fill or C["bg"], outline=outline or C["rule"], width=width)


TAG = {  # (text, fill, outline)
    "stop": ("white", C["red"], C["red"]), "check": (C["ink"], C["gold"], C["gold"]),
    "clear": ("white", C["green"], C["green"]), "teal": ("white", C["teal"], C["teal"]),
    "kids": (C["navy2"], C["bg"], C["navy2"]), "grey": (C["ink2"], C["wash"], C["rule"]),
    "fine": (C["gold_ink"], C["gold_xl"], C["id_line"]),
}


def tag(d, x, y, text, kind="grey", size=13, anchor="la") -> int:
    """Square-cornered label in letter-spaced caps; returns its width."""
    fg, bg, ol = TAG[kind]
    f = F("sans7", size)
    text = text.upper()
    inner = sum(tw(ch, f) for ch in text) + 1.2 * (len(text) - 1)
    w = int(inner) + 20
    h = size + 14
    if anchor == "ra":
        x -= w
    d.rectangle([x, y, x + w, y + h], fill=bg, outline=ol, width=1)
    spaced(d, (x + 10, y + 6), text, f, fg, track=1.2)
    return w


def chip(d, x, y, code, size=17) -> int:
    """An identifier as it would be read off a label: mono on pale gold, gold underline."""
    f = F("mono5", size)
    w = tw(code, f) + 14
    d.rectangle([x, y, x + w, y + size + 12], fill=C["id_bg"])
    d.line([(x, y + size + 12), (x + w, y + size + 12)], fill=C["id_line"], width=2)
    d.text((x + 7, y + 4), code, font=f, fill=C["ink"])
    return w


def rich(d, x, y, text, width, ids=(), size=19, color=None, line_h=None, mark=None, font="sans") -> int:
    """Paragraph with identifiers (and an optional sentence `mark`) highlighted; returns the new y."""
    line_h = line_h or int(size * 1.6)
    body, mono = F(font, size), F("mono5", size - 2)
    tokens: list[tuple[str, str]] = []  # (word, style)
    mark_span = None
    if mark and mark in text:
        i = text.index(mark)
        mark_span = (i, i + len(mark))
    for m in re.finditer(r"\S+", text):
        word = m.group(0)
        core = word.strip('.,;:"“”()')
        style = "body"
        if core and ids and find_ids_in_text(list(ids), core) and len(core) <= 24:
            style = "id"
        elif mark_span and mark_span[0] <= m.start() < mark_span[1]:
            style = "mark"
        tokens.append((word, style))
    cx, cy = x, y
    space = tw(" ", body)
    for k, (word, style) in enumerate(tokens):
        if style == "id":
            core = word.strip('.,;:"“”()')
            pre, post = word[: word.index(core)], word[word.index(core) + len(core):]
            wlen = tw(pre, body) + tw(core, mono) + 10 + tw(post, body)
        else:
            wlen = tw(word, body)
        if cx + wlen > x + width and cx > x:
            cx, cy = x, cy + line_h
        if style == "id":
            if pre:
                d.text((cx, cy), pre, font=body, fill=color or C["ink"])
                cx += tw(pre, body)
            bw = tw(core, mono) + 10
            d.rectangle([cx, cy, cx + bw, cy + size + 8], fill=C["id_bg"])
            d.line([(cx, cy + size + 8), (cx + bw, cy + size + 8)], fill=C["id_line"], width=2)
            d.text((cx + 5, cy + 3), core, font=mono, fill=C["ink"])
            cx += bw
            if post:
                d.text((cx, cy), post, font=body, fill=color or C["ink"])
                cx += tw(post, body)
        else:
            if style == "mark":
                more = k + 1 < len(tokens) and tokens[k + 1][1] == "mark"
                d.rectangle([cx - 2, cy - 1, cx + wlen + (space if more else 2), cy + size + 9], fill=C["gold_xl"])
            d.text((cx, cy), word, font=body, fill=color or C["ink"])
            cx += wlen
        cx += space
    return cy + line_h


def para(d, x, y, text, width, size=19, color=None, font="sans", line_h=None) -> int:
    line_h = line_h or int(size * 1.55)
    for line in wrap(text, F(font, size), width):
        d.text((x, y), line, font=F(font, size), fill=color or C["ink"])
        y += line_h
    return y


def stat_strip(d, y, cells: list[tuple[str, str, str, str]], x=M, w=CW) -> int:
    """One ruled strip of figures: (label, value, note, value color). Returns the y under it."""
    h = 150
    n = len(cells)
    cw = w / n
    d.line([(x, y), (x + w, y)], fill=C["ink"], width=2)
    d.line([(x, y + h), (x + w, y + h)], fill=C["rule"], width=1)
    for i, (lab, val, note, col) in enumerate(cells):
        cx = int(x + i * cw)
        if i:
            d.line([(cx, y + 18), (cx, y + h - 18)], fill=C["rule"], width=1)
        px = cx + (0 if i == 0 else 24)
        d.text((px, y + 20), lab, font=F("sans6", 17), fill=C["ink2"])
        d.text((px, y + 46), val, font=F("sans7", 48), fill=col)
        d.text((px, y + 112), clip(note, F("sans", 15), int(cw) - 40), font=F("sans", 15), fill=C["ink3"])
    return y + h


def section(d, x, y, title, w=None, right: str | None = None) -> int:
    """Section head: title over a 2px ink rule (report style). Returns y under the rule."""
    d.text((x, y), title, font=F("sans7", 21), fill=C["ink"])
    if right:
        d.text((x + w, y + 3), right, font=F("sans", 16), fill=C["ink3"], anchor="ra")
    d.line([(x, y + 36), (x + (w or CW), y + 36)], fill=C["ink"], width=2)
    return y + 36


def checkmark(d, x, y, col, s=14):
    d.line([(x, y + s * 0.55), (x + s * 0.38, y + s), (x + s, y)], fill=col, width=3)


# ------------------------------------------------------------------------------------------------ 1. the card
def complete_from_notice(text: str, rn: str) -> str:
    """Card text is cut at a fixed length; finish the last sentence from the CPSC notice it was quoted from."""
    if re.search(r'[.”")\]]$', text.strip()) or "…" in text:
        return text
    desc = D.recalls.get(rn, {}).get("description", "")
    tail = re.split(r"(?<=[.”\"])\s+", text)[-1]
    i = desc.find(tail)
    if i >= 0:
        end = desc.find(". ", i + len(tail))
        end = len(desc) if end < 0 else end + 1
        return text[: len(text) - len(tail)] + desc[i:end]
    return text.rsplit(". ", 1)[0] + "."


def fig_card() -> None:
    """The printable card: a one-page intake-desk notice, black on white, two action bands."""
    card = D.card
    im = Image.new("RGB", (W, 9000), C["bg"])
    d = ImageDraw.Draw(im)
    X, R = 80, W - 80
    d.rectangle([0, 0, W, 8], fill=C["navy"])
    y = 52
    caps(d, X, y, "Recall check · intake desk notice", C["navy2"], 16)
    d.text((X, y + 34), card["shop_name"], font=F("serif7", 46), fill=C["ink"])
    wk = date.fromisoformat(card["week_of"])
    d.text((X, y + 104), f"Week of Thursday, {wk:%B} {wk.day}, {wk.year}", font=F("sans", 22), fill=C["ink2"])
    for i, (lab, val) in enumerate([("Items checked", card["items_checked"]), ("New CPSC recalls", card["new_recalls"])]):
        rx = R - i * 220
        d.text((rx, y + 22), lab, font=F("sans6", 17), fill=C["ink2"], anchor="ra")
        d.text((rx, y + 46), str(val), font=F("sans7", 54), fill=C["ink"], anchor="ra")
    y += 160
    d.line([(X, y), (R, y)], fill=C["ink"], width=3)
    y += 34

    def band(y, title, n, note, fill, fg):
        h = 66
        d.rectangle([X, y, R, y + h], fill=fill)
        wt = spaced(d, (X + 24, y + 18), title, F("sans7", 26), fg, track=2.2)
        d.text((X + 24 + wt + 18, y + 20), f"{n} items", font=F("sans6", 22), fill=fg)
        d.text((R - 24, y + 22), note, font=F("sans6", 18), fill=fg, anchor="ra")
        return y + h

    col2 = 850
    w1, w2 = col2 - X - 70, R - col2 - 130

    def row(y, it, field, field_label, extra=None):
        y0 = y + 26
        d.rectangle([X + 4, y0 + 4, X + 26, y0 + 26], outline=C["ink"], width=2)
        yy = y0
        for line in wrap(it["item"], F("sans6", 22), w1):
            d.text((X + 46, yy), line, font=F("sans6", 22), fill=C["ink"])
            yy += 33
        yy += 4
        num = f"CPSC {it['recall_number']}"
        d.text((X + 46, yy), num, font=F("mono5", 17), fill=C["ink"])
        d.text((X + 46 + tw(num, F("mono5", 17)) + 14, yy), clip(product_name(it["recall_number"]), F("sans", 18),
               w1 - 160), font=F("sans", 18), fill=C["ink3"])
        yl = y0
        ids = spec_ids(it["recall_number"])
        caps(d, col2, yl + 3, field_label, C["ink2"], 14)
        yl = rich(d, col2 + 130, yl - 1, field, w2, ids=ids, size=19, line_h=30)
        if extra:
            yl += 8
            caps(d, col2, yl + 3, extra[0], C["ink2"], 14)
            yl = rich(d, col2 + 130, yl - 1, extra[1], w2, size=19, line_h=30)
        y = max(yy + 30, yl) + 20
        d.line([(X, y), (R, y)], fill=C["rule"], width=1)
        return y

    y = band(y, "DO NOT SELL", len(card["do_not_sell"]),
             "Pull from the floor. Do not list, donate or return to the consignor.", C["red"], "white")
    for it in card["do_not_sell"]:
        y = row(y, it, it["why"], "Why", ("Remedy", it["remedy"]))
    y += 40
    y = band(y, "CHECK THE LABEL", len(card["check_label"]),
             "Look before you list. Clear it only if the label does not match.", C["gold"], C["ink"])
    for it in card["check_label"]:
        y = row(y, it, complete_from_notice(it["look_for"], it["recall_number"]), "Look for")

    y += 48
    mems = card["applied_memories"]
    y = section(d, X, y, f"Shop corrections applied this week ({len(mems)})", R - X,
                right="Stored as Backboard memories; applied by code, not the model") + 18
    for m in mems:
        note = m["text"].split(f"recall {m['recall_number']}.", 1)[-1].split("[recall=")[0].strip()
        d.text((X, y), m["item"], font=F("sans6", 20), fill=C["ink"])
        d.text((R, y + 2), f"memory {m['memory_id'][:8]}", font=F("mono", 15), fill=C["ink3"], anchor="ra")
        d.text((X, y + 32), f"CPSC {m['recall_number']} · the model said check the label · the shop's note "
               f"clears it", font=F("sans", 17), fill=C["ink2"])
        yy = para(d, X, y + 64, note, R - X - 200, size=18, color=C["ink"], line_h=28)
        y = yy + 14
        d.line([(X, y), (R, y)], fill=C["rule"], width=1)
        y += 20

    y += 40
    seg = (R - X) // 3
    for i, lab in enumerate(["Pulled by", "Date", "Initials"]):
        x = X + i * seg
        d.text((x, y), lab, font=F("sans6", 19), fill=C["ink2"])
        d.line([(x + tw(lab, F("sans6", 19)) + 14, y + 22), (x + seg - 40, y + 22)], fill=C["ink"], width=1)
    y += 70
    d.line([(X, y), (R, y)], fill=C["rule2"], width=1)
    y += 18
    d.text((X, y), f"RecallDesk · {card['model']} · {card['workflow_id']}", font=F("mono", 15), fill=C["ink3"])
    d.text((R, y), "Not legal advice. We read the notice text, not your labels. Source: cpsc.gov/Recalls",
           font=F("sans", 15), fill=C["ink3"], anchor="ra")
    y += 52
    im = im.crop((0, 0, W, y))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W - 1, y - 1], outline=C["rule2"], width=1)
    p = HERE / "home-card-1440.png"
    im.save(p, optimize=True)
    print(f"wrote {p.relative_to(ROOT)}  ({W}x{y})")


# ------------------------------------------------------------------------------------------------ 2. overview
def where_part(look_for: str) -> str:
    """'model no. X; sold A to B. The model number is ...' -> 'The model number is ...' (the codes if no sentence)."""
    rest = re.split(r"(?<=[\d…])\.\s+(?=[A-Z“\"])", look_for, maxsplit=1)
    return rest[1] if len(rest) > 1 and rest[1].strip() else look_for


def fig_overview() -> None:
    card = D.card
    rec = [r for r in D.recalls.values() if r.get("recall_date") == card["week_of"]]
    a = [r for r in D.recalls.values() if "A" in (r.get("corpus") or [])]
    lp = D.charts["listings-per-recall"]
    pg = Page("Dashboard: overview",
              f"Week of Oct 15: {len(card['do_not_sell'])} items to pull, {len(card['check_label'])} labels to check",
              f"CPSC posted {card['new_recalls']} recalls on Thursday. RecallDesk re-checked all {card['items_checked']} "
              f"items in Little Loop's inventory against them and published this week's card.",
              f"Source: {card['id']} ({card['workflow_id']}); CPSC Recalls API; SerpApi eBay engine")
    d = pg.d
    kids = sum(1 for r in rec if r.get("is_childrens"))
    y = stat_strip(d, pg.y, [
        ("New recalls this Thursday", str(len(rec)), f"{kids} for children · {len(a)} since Jul 18", C["ink"]),
        ("Items checked", str(card["items_checked"]), f"{card['usage']['model_calls']} model calls, "
         f"${card['usage']['cost_usd']:.3f}", C["ink"]),
        ("Do not sell", str(len(card["do_not_sell"])), "pull from the floor and listings", C["red"]),
        ("Check the label", str(len(card["check_label"])), "the label decides it", C["gold_ink"]),
    ]) + 48

    LW = 920
    rows = [(it, "Do not sell", "stop", "Hazard: " + D.specs[it["recall_number"]]["hazard_short"])
            for it in card["do_not_sell"]] + \
           [(it, "Check label", "check", where_part(complete_from_notice(it["look_for"], it["recall_number"])))
            for it in card["check_label"]]
    ty = section(d, M, y, "This week's card", LW, right=card["id"])
    cols = [M, M + 320, M + 480, M + 570]
    ty += 14
    for cx, lab in zip(cols, ["Item", "Action", "Recall", "Hazard, or where to look"]):
        caps(d, cx, ty, lab, C["ink2"], 13)
    ty += 30
    rh = 72
    for it, st, kind, why in rows:
        d.line([(M, ty), (M + LW, ty)], fill=C["rule"], width=1)
        name = re.sub(r"\s*\(model [^)]*\)", "", it["item"])
        d.text((cols[0], ty + 14), clip(name, F("sans6", 17), 300), font=F("sans6", 17), fill=C["ink"])
        d.text((cols[0], ty + 40), clip(product_name(it["recall_number"]), F("sans", 15), 300), font=F("sans", 15),
               fill=C["ink3"])
        tag(d, cols[1], ty + 21, st, kind, 12)
        d.text((cols[2], ty + 24), it["recall_number"], font=F("mono5", 17), fill=C["ink"])
        for i, line in enumerate(wrap_clip(why, F("sans", 15), M + LW - cols[3], 2)):
            d.text((cols[3], ty + 14 + i * 24), line, font=F("sans", 15), fill=C["ink2"])
        ty += rh
    d.line([(M, ty), (M + LW, ty)], fill=C["rule"], width=1)
    left_bottom = ty

    x, rw = M + LW + 48, CW - LW - 48
    yy = section(d, x, y, "Next sweep", rw, right="Scheduled") + 16
    d.text((x, yy), "Thursday, Oct 22, 2:00 PM Eastern", font=F("sans6", 19), fill=C["ink"])
    d.text((x, yy + 30), "Temporal schedule recalldesk-weekly-sweep", font=F("sans", 15), fill=C["ink3"])
    yy += 72
    steps = ["fetch_new_recalls", "extract_spec", "load_shop_memories", "check_item, per item", "scan_ebay_store",
             "compose_card", "publish_card"]
    for i, s in enumerate(steps, 1):
        d.text((x, yy), f"{i}", font=F("sans6", 16), fill=C["ink3"])
        d.text((x + 28, yy - 1), s, font=F("mono", 17), fill=C["ink"])
        yy += 30
    yy += 34

    yy = section(d, x, yy, "Posted this Thursday", rw, right=fmt_date(card["week_of"])) + 4
    for r in sorted(rec, key=lambda r: r["recall_number"], reverse=True):
        d.text((x, yy + 12), r["recall_number"], font=F("mono5", 16), fill=C["ink2"])
        if r.get("is_childrens"):
            tag(d, x + rw, yy + 10, "Children's", "kids", 11, anchor="ra")
        d.text((x, yy + 38), clip(product_name(r["recall_number"]), F("sans6", 17), rw), font=F("sans6", 17),
               fill=C["ink"])
        yy += 70
        d.line([(x, yy), (x + rw, yy)], fill=C["rule"], width=1)
    yy += 34

    yy = section(d, x, yy, "eBay, recalls since Jul 18", rw) + 16
    stats = [(f"{lp['unique_listings']:,}", "unique listings"), (str(lp["recalls_searched"]), "recalls searched"),
             (str(lp["exact_id_hit_listings"]), "name a recalled ID")]
    sw = rw // 3
    for i, (v, lab) in enumerate(stats):
        d.text((x + i * sw, yy), v, font=F("sans7", 34), fill=C["red"] if i == 2 else C["ink"])
        d.text((x + i * sw, yy + 46), lab, font=F("sans", 15), fill=C["ink3"])
    yy += 82
    d.text((x, yy), "An exact identifier in the title; a string match.", font=F("sans", 15), fill=C["ink3"])
    yy += 50

    runs = sorted(D.runs, key=lambda r: r["started_at"], reverse=True)
    yy = section(d, x, yy, "Recent runs", rw) + 4
    for r in runs:
        s = r["summary"]
        t = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
        d.text((x, yy + 12), clip(r["workflow_id"], F("mono", 15), rw), font=F("mono", 15), fill=C["ink"])
        extra = " · resumed after a crash" if r.get("resumed_after_crash") else ""
        line = f"{t:%H:%M} UTC · {s['items_checked']} items · {s['do_not_sell']} pull · {s['check_label']} check{extra}"
        d.text((x, yy + 38), clip(line, F("sans", 15), rw), font=F("sans", 15), fill=C["ink2"])
        yy += 70
        d.line([(x, yy), (x + rw, yy)], fill=C["rule"], width=1)
    pg.y = max(left_bottom, yy)
    pg.finish("overview-1440")


# ------------------------------------------------------------------------------------------------ 3. inventory item
def where_sentence(rn: str) -> str:
    desc = D.recalls[rn]["description"]
    sents = re.split(r"(?<=\.)\s+", desc)
    loc = [s for s in sents if re.search(r"\b(printed|engraved|located|found|stamped|label|tag)\b", s, re.I)]
    named = [s for s in loc if find_ids_in_text(spec_ids(rn), s)]
    return (named or loc or [""])[-1]


def kv_table(d, x, y, w, rows, key_w=170) -> int:
    """Key/value rows with hairlines; values may be a list of identifier chips. Returns the y under it."""
    for k, v, is_id in rows:
        d.line([(x, y), (x + w, y)], fill=C["rule"], width=1)
        d.text((x, y + 16), k, font=F("sans", 18), fill=C["ink2"])
        if is_id:
            bx = x + key_w
            for code in v:
                bx += chip(d, bx, y + 12, code) + 8
            y += 60
        else:
            ly = y + 16
            for line in wrap(v, F("sans", 18), w - key_w):
                d.text((x + key_w, ly), line, font=F("sans", 18), fill=C["ink"])
                ly += 28
            y = ly + 16
    d.line([(x, y), (x + w, y)], fill=C["rule"], width=1)
    return y


def fig_inventory() -> None:
    item = next(i for i in D.inventory if i["sku"] == "LL-001")
    hit = next(i for i in D.card["do_not_sell"] if i["recall_number"] == "27027")
    rn = hit["recall_number"]
    r, s = D.recalls[rn], D.specs[rn]
    pg = Page("Dashboard: inventory item",
              f"The shop's bedside sleeper carries the recalled model number",
              "Any inventory row opens beside the recall it was compared with: the shop's record on the left, the "
              "CPSC recall and its extracted spec on the right, and the reason for the call.",
              f"Source: agent/fixtures_src/little_loop_inventory.csv; {D.card['id']}; CPSC recall {rn}")
    d = pg.d
    y = pg.y
    x = M
    x += tag(d, x, y, "Do not sell", "stop", 14) + 12
    x += tag(d, x, y, "Children's product", "kids", 14) + 16
    d.text((x, y + 2), f"Model: {D.card['model']}", font=F("mono", 16), fill=C["ink3"])
    y += 60

    pw = (CW - 64) // 2
    rx = M + pw + 64
    for px, head, title, sub in [(M, "Your item", item["name"], f"SKU {item['sku']} · {item['brand']} · "
                                  f"{item['category']}"),
                                 (rx, f"Recalled product · CPSC {rn}", s["product_name"],
                                  f"{s['brand']} · recalled {fmt_date(r['recall_date'])}")]:
        caps(d, px, y, head, C["navy2"], 14)
        ty = y + 30
        for line in wrap(title, F("sans7", 23), pw):
            d.text((px, ty), line, font=F("sans7", 23), fill=C["ink"])
            ty += 34
        d.text((px, ty + 2), sub, font=F("sans", 17), fill=C["ink3"])
    y += 30 + 34 * max(len(wrap(item["name"], F("sans7", 23), pw)), len(wrap(s["product_name"], F("sans7", 23), pw))) + 44
    yl = kv_table(d, M, y, pw, [("Model", [item["model"]], True), ("Price", item["price"], False),
                                ("Notes", item["notes"], False)])
    yr = kv_table(d, rx, y, pw, [("Model nos.", s["model_numbers"], True),
                                 ("Sold", f"{fmt_month(s['sold_from'])} – {fmt_month(s['sold_to'])}", False),
                                 ("Units", r["units"], False), ("Colors", ", ".join(s["colors"]), False)])
    d.line([(M + pw + 32, y), (M + pw + 32, max(yl, yr))], fill=C["rule"], width=1)
    y = max(yl, yr) + 52

    def block(y, title, text, ids=(), small=None):
        y = section(d, M, y, title) + 16
        y = rich(d, M, y, text, CW, ids=ids, size=20, line_h=33)
        if small:
            y = para(d, M, y + 2, small, CW, size=17, color=C["ink3"])
        return y + 36

    y = block(y, "Why it is a match", hit["why"])
    y = block(y, "Where to look", where_sentence(rn), ids=s["model_numbers"])
    y = block(y, "Remedy", hit["remedy"], small=f"Hazard: {s['hazard_short']}.")

    ph = 150
    box(d, M, y, CW, ph, fill=C["wash"], outline=C["rule2"], dash=True)
    d.text((M + 28, y + 24), "Not a match?", font=F("sans7", 21), fill=C["ink"])
    d.text((M + 28, y + 58), "Correct it once. RecallDesk stores the note as a Backboard memory for this shop and "
           "applies it every Thursday after.", font=F("sans", 18), fill=C["ink2"])
    bt = "Not a match? Correct this"
    bw = tw(bt, F("sans6", 18)) + 40
    d.rectangle([M + 28, y + 94, M + 28 + bw, y + 134], fill=C["bg"], outline=C["link"], width=2)
    d.text((M + 28 + bw // 2, y + 114), bt, font=F("sans6", 18), fill=C["link"], anchor="mm")
    pg.y = y + ph
    pg.finish("inventory-drawer-1440")


# ------------------------------------------------------------------------------------------------ 4. recall detail
def fig_recall() -> None:
    rn = "26658"
    r, s = D.recalls[rn], D.specs[rn]
    where = where_sentence(rn)
    pg = Page("Dashboard: recall detail",
              "CPSC 26658 puts the model number under the bottom step",
              "The recalls page sets CPSC's own text, identifiers highlighted, beside the structured spec the "
              "teacher model extracted from it. Every item and listing is compared against that spec.",
              f"Source: CPSC Recalls API, recall {rn} posted {r['recall_date']}; spec from data/specs/specs.jsonl")
    d = pg.d
    y = pg.y
    d.text((M, y), product_name(rn), font=F("sans7", 28), fill=C["ink"])
    y += 48
    x = M
    meta = f"CPSC {rn} · posted {fmt_date(r['recall_date'])} · {r['units']} units"
    d.text((x, y + 2), meta, font=F("sans", 19), fill=C["ink2"])
    x += tw(meta, F("sans", 19)) + 20
    x += tag(d, x, y, "Children's product", "kids", 13) + 10
    tag(d, x, y, "ID only in the description", "fine", 13)
    y += 62

    d.rectangle([M, y, M + 6, y + 82], fill=C["navy2"])
    caps(d, M + 30, y + 6, "Where to look", C["navy2"], 14)
    d.text((M + 30, y + 36), where, font=F("serif", 24), fill=C["ink"])
    y += 82 + 52

    lw = 640
    rx, rw = M + lw + 64, CW - lw - 64
    ly = section(d, M, y, "Original CPSC text", lw) + 20
    ly = rich(d, M, ly, r["description"], lw, ids=s["model_numbers"], size=21, line_h=38, mark=where)
    ly = para(d, M, ly + 14, r["retailers"][0], lw, size=18, color=C["ink3"])
    ly = para(d, M, ly + 6, f"Importer: {r['importers'][0]}", lw, size=18, color=C["ink3"])

    ry = section(d, rx, y, "Extracted spec", rw, right="Teacher: Qwen3.5-397B") + 4
    rows = [("Brand", s["brand"]), ("Product", f"{s['product_name']} ({s['product_type']})"),
            ("Model nos.", s["model_numbers"]), ("Sold", f"{fmt_month(s['sold_from'])} – {fmt_month(s['sold_to'])}"),
            ("Colors", ", ".join(s["colors"])), ("Features", s["key_features"]), ("Units", r["units"]),
            ("Hazard", s["hazard_short"]), ("Remedy", s["remedy_short"]), ("eBay queries", s["search_queries"])]
    vx, vw = rx + 180, rw - 180
    for i, (k, v) in enumerate(rows):
        if i:
            d.line([(rx, ry), (rx + rw, ry)], fill=C["rule"], width=1)
        d.text((rx, ry + 14), k, font=F("sans", 18), fill=C["ink2"])
        vy = ry + 14
        if k == "Model nos.":
            bx = vx
            for code in v:
                bx += chip(d, bx, vy - 4, code) + 8
            vy += 42
        elif k == "Features":
            for f in v:
                d.text((vx, vy), "–", font=F("sans", 18), fill=C["ink3"])
                vy = para(d, vx + 20, vy, f, vw - 20, size=18, line_h=28)
            vy += 4
        elif k == "eBay queries":
            for q in v:
                vy = para(d, vx, vy, q, vw, size=16, font="mono", line_h=26)
            vy += 4
        else:
            vy = para(d, vx, vy, v, vw, size=18, line_h=28) + 4
        ry = vy + 10
    d.line([(rx, ry), (rx + rw, ry)], fill=C["rule"], width=1)
    pg.y = max(ly, ry)
    pg.finish("recalls-expanded-1440",
              notes="Highlighted codes are the spec's model numbers as they appear in the notice. The shaded sentence "
                    "is the one the weekly card quotes under 'look for'.")


# ------------------------------------------------------------------------------------------------ 5. eBay monitor
def fig_ebay() -> None:
    lp = D.charts["listings-per-recall"]
    cm = D.charts["condition-mix"]
    kids_n = sum(cm["childrens"].values())
    kid_hits = sum(h["hits"] for h in lp["exact_id_hits_by_recall"] if h["is_childrens"])
    pg = Page("Dashboard: eBay monitor",
              f"Of {lp['unique_listings']:,} eBay listings, {lp['exact_id_hit_listings']} name a recalled identifier",
              f"SerpApi's eBay engine ran each spec's search query for {lp['recalls_searched']} recalls: every recall "
              f"since July 18 plus older children's recalls, {lp['results_total']:,} results in all. A listing counts "
              f"below only if its title contains a recalled model number or UPC, ignoring case and dashes.",
              "Source: SerpApi eBay engine (engine=ebay, _ipg=50), fetched 2026-10-17; CPSC Recalls API")
    d = pg.d
    y = stat_strip(d, pg.y, [
        ("Recalls searched", str(lp["recalls_searched"]), f"{lp['searched_A']} since Jul 18, "
         f"{lp['searched_B_only']} older children's", C["ink"]),
        ("Unique listings", f"{lp['unique_listings']:,}", f"from {lp['results_total']:,} search results", C["ink"]),
        ("Title names a recalled ID", str(lp["exact_id_hit_listings"]),
         f"across {lp['recalls_with_exact_id_hit']} recalls", C["red"]),
        ("For children's recalls", str(kid_hits), f"of {kids_n:,} listings", C["ink"]),
    ]) + 48

    hits = sorted(lp["exact_id_hits_by_recall"], key=lambda h: (-h["hits"], h["recall_number"]))
    open_rn = "26637"
    ex = [o for o in read_jsonl(DATA / "listings" / "listings.jsonl")
          if o["recall_number"] == open_rn and find_ids_in_text(spec_ids(open_rn), o["title"])]
    ty = section(d, M, y, f"The {len(hits)} recalls with a listing that names a recalled identifier") + 14
    cx = [M, M + 820, CW + M]
    caps(d, cx[0], ty, "Recall", C["ink2"], 13)
    caps(d, cx[1], ty, "Recalled identifiers", C["ink2"], 13)
    caps(d, cx[2], ty, "Listings", C["ink2"], 13, anchor="ra")
    ty += 30
    rh = 70
    for hrow in hits:
        rn = hrow["recall_number"]
        d.line([(M, ty), (M + CW, ty)], fill=C["rule"], width=1)
        d.text((cx[0], ty + 12), clip(product_name(rn), F("sans6", 19), 620), font=F("sans6", 19), fill=C["ink"])
        rd = D.recalls.get(rn, {}).get("recall_date", "")
        meta = f"CPSC {rn} · {fmt_date(rd)}"
        d.text((cx[0], ty + 40), meta, font=F("sans", 15), fill=C["ink3"])
        if hrow["is_childrens"]:
            tag(d, cx[0] + tw(meta, F("sans", 15)) + 14, ty + 37, "Children's", "kids", 10)
        d.text((cx[1], ty + 24), clip(", ".join(hrow["ids"]), F("mono", 16), 420), font=F("mono", 16), fill=C["ink2"])
        d.text((cx[2], ty + 18), str(hrow["hits"]), font=F("sans7", 26), fill=C["ink"], anchor="ra")
        ty += rh
        if rn == open_rn:
            card_h = 128
            shown = ex[:4]
            open_h = 64 + ((len(shown) + 1) // 2) * (card_h + 14) + 16
            d.rectangle([M, ty, M + CW, ty + open_h], fill=C["wash"])
            caps(d, M + 24, ty + 22, f"CPSC {rn}, expanded: {len(shown)} of {len(ex)} listings", C["navy2"], 13)
            cw = (CW - 48 - 14) // 2
            for i, o in enumerate(shown):
                bx = M + 24 + (i % 2) * (cw + 14)
                by = ty + 58 + (i // 2) * (card_h + 14)
                box(d, bx, by, cw, card_h)
                yy = by + 18
                for line in wrap_clip(o["title"], F("sans6", 17), cw - 40, 2):
                    rich(d, bx + 20, yy, line, cw - 40, ids=spec_ids(rn), size=17, line_h=28, font="sans6")
                    yy += 30
                meta = f"{o['condition']} · {o['price']} · seller {o['seller_hash']}"
                d.text((bx + 20, by + card_h - 40), meta, font=F("sans", 16), fill=C["ink2"])
                tag(d, bx + cw - 20, by + card_h - 44, "ID in title", "stop", 11, anchor="ra")
            ty += open_h
    d.line([(M, ty), (M + CW, ty)], fill=C["rule"], width=1)
    pg.y = ty
    pg.finish("ebay-1440",
              notes="An identifier in a title is a deterministic string match, not a model verdict and not a "
                    "confirmed recalled unit; a person still opens the listing. Sellers appear only as a hashed id.")


# ------------------------------------------------------------------------------------------------ 6. pricing
def fig_pricing() -> None:
    u = D.card["usage"]
    pg = Page("Pricing",
              "$15 a month per shop, or $49 per consignment event",
              "Two plans, one for kids' consignment shops with a steady intake desk and one for the seasonal sales "
              "they run. Checking costs cents, so the price follows the buyer, not the compute.",
              f"Source: RecallDesk pricing; usage from {D.card['id']} ({D.card['workflow_id']})")
    d = pg.d
    y = pg.y
    plans = [
        ("Shop", "$15", "per month, per shop", "For a shop that takes in second-hand goods every day.",
         ["A card every Thursday, after CPSC posts", "Unlimited inventory checks", "eBay store re-check",
          "Shop memory: a correction applies every week after"]),
        ("Consignment event", "$49", "per event", "For a seasonal sale with thousands of items in one weekend.",
         ["Every consignor's intake list checked", "One card per drop-off batch", "A printable pull list",
          "Recalls back to 2023"]),
    ]
    pw = (CW - 64) // 2
    for i, (name, price, per, blurb, feats) in enumerate(plans):
        x = M + i * (pw + 64)
        d.line([(x, y), (x + pw, y)], fill=C["ink"], width=2)
        caps(d, x, y + 22, "Plan", C["ink3"], 13)
        d.text((x, y + 48), name, font=F("serif7", 32), fill=C["ink"])
        d.text((x, y + 108), price, font=F("sans7", 76), fill=C["ink"])
        d.text((x + tw(price, F("sans7", 76)) + 14, y + 152), per, font=F("sans", 21), fill=C["ink2"])
        d.text((x, y + 208), blurb, font=F("sans", 19), fill=C["ink2"])
        fy = y + 262
        for f in feats:
            d.line([(x, fy), (x + pw, fy)], fill=C["rule"], width=1)
            checkmark(d, x + 2, fy + 18, C["green"])
            d.text((x + 34, fy + 13), f, font=F("sans", 20), fill=C["ink"])
            fy += 54
        d.line([(x, fy), (x + pw, fy)], fill=C["rule"], width=1)
    y += 262 + 4 * 54 + 56
    y = section(d, M, y, "What a full check costs to run") + 18
    d.text((M, y), f"Re-checking the {u['items']}-item demo shop took {u['model_calls']} model calls "
           f"({u['tokens_in']:,} tokens in, {u['tokens_out']:,} out): ${u['cost_usd']:.3f} at Tinker list price.",
           font=F("sans", 20), fill=C["ink"])
    pg.y = y + 30
    pg.finish("billing-1440", notes="Not legal advice and not a substitute for cpsc.gov/Recalls. U.S. CPSC recalls only.")


# ------------------------------------------------------------------------------------------------ 7-8. crash rehearsal
def crash_facts() -> dict:
    """Every number on the two crash figures, parsed from the rehearsal log."""
    t = CRASH_LOG.read_text(encoding="utf-8")

    def g(pat, cast=str):
        m = re.search(pat, t)
        if not m:
            raise SystemExit(f"crash log: no match for {pat!r}")
        return cast(m.group(1))

    f = dict(
        wf=g(r"id=(check-\S+crashdemo)"), t_start=g(r"t\+\s*([\d.]+)s\] 2\) started", float),
        t_kill=g(r"t\+\s*([\d.]+)s\] 4\) \[CRASH\]", float), t_w2=g(r"t\+\s*([\d.]+)s\] 5\) starting worker #2", float),
        t_done=g(r"t\+\s*([\d.]+)s\] 6\) workflow COMPLETED", float),
        pid1=g(r"worker pid=(\d+) up"), pid2=g(r"worker#2 \| \S+ \[worker\] worker pid=(\d+)"),
        hist_at_kill=g(r"history length=(\d+)", int), in_flight=g(r"(\d+) check_item activities in flight", int),
        scheduled=g(r"activities scheduled\s*: (\d+)", int), before=g(r"completed before the crash\s*: (\d+)", int),
        after=g(r"completed after restart\s*: (\d+)", int), twice=g(r"completed twice\s*: (\d+)", int),
        retried=g(r"\(retried\)\s*: (\d+)", int), events=g(r"total history events\s*: (\d+)", int),
        delay=g(r"\+ ([\d.]+)s simulated latency", float), pairs=g(r"60/60 items, (\d+) pairs", int),
        dns=g(r"compose_card\s+completed attempt=1\s+(\d+) DO NOT SELL", int),
        chk=g(r"DO NOT SELL, (\d+) CHECK LABEL\n", int),
        mem=g(r"(\d+) memories applied", int),
    )
    f["steps"] = re.findall(r"\[(OK|--)\] (\w+)\s+(\w+)\s+attempt=(\d)\s+(.+)", t.split("6) workflow COMPLETED")[1])
    return f


def fig_timeline() -> None:
    f = crash_facts()
    pg = Page("Temporal: crash rehearsal",
              f"The worker was killed {f['t_kill']} s in; a new one finished the run",
              f"Rehearsal {f['wf']}, using the rules classifier plus {f['delay']} s of artificial latency per item so "
              f"that the kill lands mid-run. The state lives in Temporal's event history, not in the worker.",
              "Source: agent/demo_logs/heuristic/04_crash_resume.txt (python -m agent.demo_crash); Temporal event "
              "history")
    d = pg.d
    y = pg.y + 10
    t0, t1 = 0.0, 36.0
    ax0, ax1 = M + 250, W - M

    def X(t):
        return ax0 + (ax1 - ax0) * (t - t0) / (t1 - t0)

    lanes = [
        ("Workflow", f["t_start"], f["t_done"], C["ink2"], "Running throughout"),
        (f"Worker 1, pid {f['pid1']}", 0.4, f["t_kill"], C["navy2"], ""),
        ("No worker", f["t_kill"], f["t_w2"], None, f"{f['t_w2'] - f['t_kill']:.1f} s"),
        (f"Worker 2, pid {f['pid2']}", f["t_w2"], f["t_done"], C["teal"], "Replays the history, carries on"),
    ]
    lane_h = 62
    top = y
    bot = top + lane_h * len(lanes)
    for i in range(0, 37, 4):
        d.line([(X(i), top), (X(i), bot)], fill=C["rule"], width=1)
    d.line([(ax0, bot), (ax1, bot)], fill=C["ink"], width=1)
    for li, (name, a, b, col, txt) in enumerate(lanes):
        ly = top + li * lane_h
        d.text((M, ly + 20), name, font=F("sans6", 18), fill=C["ink"])
        if col is None:
            d.rectangle([X(a), ly + 14, X(b), ly + 42], fill=C["red_xl"], outline=C["red"], width=1)
            d.text((X(b) + 10, ly + 28), txt, font=F("sans6", 16), fill=C["red"], anchor="lm")
        else:
            d.rectangle([X(a), ly + 14, X(b), ly + 42], fill=col)
            if txt:
                d.text((X(a) + 12, ly + 28), txt, font=F("sans6", 15), fill="white", anchor="lm")
    for i in range(0, 37, 4):
        d.line([(X(i), bot), (X(i), bot + 6)], fill=C["ink"], width=1)
        d.text((X(i), bot + 12), f"{i} s", font=F("sans", 15), fill=C["ink3"], anchor="ma")
    marks = [(f["t_start"], "workflow started", C["ink2"]), (f["t_kill"], f"worker 1 killed (pid {f['pid1']})",
             C["red"]), (f["t_w2"], "worker 2 starts", C["teal"]), (f["t_done"], "card published", C["ink"])]
    my = bot + 70
    for i, (t, txt, col) in enumerate(marks):
        d.line([(X(t), top), (X(t), my + i * 32 + 4)], fill=col, width=1)
        lab = f"t+{t} s  {txt}"
        crossed = any(X(t) < X(t2) < X(t) + 8 + tw(lab, F("sans6", 16)) for t2, _, _ in marks[i + 1:])
        if crossed or X(t) + 8 + tw(lab, F("sans6", 16)) > W - M:
            d.text((X(t) - 8, my + i * 32 - 6), lab, font=F("sans6", 16), fill=col, anchor="ra")
        else:
            d.text((X(t) + 8, my + i * 32 - 6), lab, font=F("sans6", 16), fill=col)
    for i in range(0, 37, 4):  # keep the axis labels clear of the marker lines
        lab = f"{i} s"
        lx = X(i)
        d.rectangle([lx - tw(lab, F("sans", 15)) // 2 - 5, bot + 10, lx + tw(lab, F("sans", 15)) // 2 + 5, bot + 32],
                    fill=C["bg"])
        d.text((lx, bot + 12), lab, font=F("sans", 15), fill=C["ink3"], anchor="ma")
    y = my + len(marks) * 32 + 50

    y = section(d, M, y, f"The {f['scheduled']} check_item activities, one square each") + 24
    kept, retried = f["before"], f["retried"]
    fresh = f["after"] - retried
    cells = [C["navy2"]] * kept + [C["gold"]] * retried + [C["teal"]] * fresh
    per_row, cs, gap = 30, 38, 8
    for i, col in enumerate(cells):
        cx = M + (i % per_row) * (cs + gap)
        cy = y + (i // per_row) * (cs + gap)
        d.rectangle([cx, cy, cx + cs, cy + cs], fill=col)
    y += ((len(cells) + per_row - 1) // per_row) * (cs + gap) + 16
    for col, txt in [(C["navy2"], f"{kept} completed on worker 1 and kept from the history; not run again"),
                     (C["gold"], f"{retried} were in flight at the kill; retried on worker 2, attempt 2"),
                     (C["teal"], f"{fresh} ran for the first time on worker 2")]:
        d.rectangle([M, y + 4, M + 18, y + 22], fill=col)
        d.text((M + 30, y), txt, font=F("sans", 18), fill=C["ink"])
        y += 34
    y += 36
    y = stat_strip(d, y, [
        ("Activities scheduled", str(f["scheduled"]), "one per item, none twice", C["ink"]),
        ("Completed twice", str(f["twice"]), "no item was checked twice", C["green"]),
        ("History events", str(f["events"]), f"{f['hist_at_kill']} when worker 1 died", C["ink"]),
        ("In flight at the kill", str(f["in_flight"]), "retried after the heartbeat timeout", C["gold_ink"]),
    ])
    pg.y = y
    pg.finish("temporal-crash-timeline-chart",
              notes="Times are seconds on the demo script's clock. Counts come from the workflow's Temporal event "
                    "history. The crash run on the fine-tuned LoRA (…-1a16-crashdemo, 344 events) is charted "
                    "separately.")


def fig_runs() -> None:
    f = crash_facts()
    pg = Page("Dashboard: workflow runs",
              "The crash rehearsal completed, resumed on a second worker",
              "The runs page reads each workflow from Temporal. This run shows as completed, with the check_items "
              "step marked as resumed after the first worker was killed.",
              "Source: agent/demo_logs/heuristic/04_crash_resume.txt; Temporal event history")
    d = pg.d
    y = pg.y
    d.text((M, y), f["wf"], font=F("mono5", 23), fill=C["ink"])
    y += 46
    x = M
    x += tag(d, x, y, "Completed", "clear", 13) + 10
    x += tag(d, x, y, f"{f['retried']} activities retried", "check", 13) + 10
    tag(d, x, y, "Resumed after a crash", "teal", 13)
    y += 64

    d.rectangle([M, y, M + 6, y + 96], fill=C["teal"])
    d.text((M + 30, y + 2), "Worker killed mid-run, resumed on a new worker", font=F("sans7", 21), fill=C["ink"])
    d.text((M + 30, y + 36), "Temporal replayed the event history on the new worker. Finished activities were kept "
           "and did not run again.", font=F("sans", 18), fill=C["ink2"])
    d.text((M + 30, y + 68), f"Worker {f['pid1']}@MAVERICK, then worker {f['pid2']}@MAVERICK", font=F("sans6", 17),
           fill=C["ink"])
    y += 96 + 48

    y = stat_strip(d, y, [("Activities", str(len(f["steps"])), "InventoryCheckWorkflow", C["ink"]),
                          ("History events", str(f["events"]), "in Temporal", C["ink"]),
                          ("Run time", f"{f['t_done'] - f['t_start']:.1f} s", "start to card published", C["ink"]),
                          ("Items checked", "60", f"{f['pairs']} item and recall pairs", C["ink"])])
    y += 14
    d.text((M, y), f"Card card_2026-10-15_little-loop: {f['dns']} do not sell, {f['chk']} check the label, "
           f"{f['mem']} shop correction applied (rules classifier, not the LoRA).", font=F("sans", 17),
           fill=C["ink2"])
    y += 64

    y = section(d, M, y, "Activities, in order") + 6
    for i, (ok, name, status, attempt, note) in enumerate(f["steps"]):
        resumed = name == "check_items"
        d.text((M, y + 18), f"{i + 1}", font=F("sans6", 17), fill=C["ink3"])
        d.text((M + 36, y + 16), name, font=F("mono5", 19), fill=C["ink"])
        if resumed:
            tag(d, M + 36 + tw(name, F("mono5", 19)) + 16, y + 16, "Resumed after worker crash", "teal", 11)
        st = f"{status}, attempt {attempt}"
        d.text((W - M, y + 18), st, font=F("sans6" if resumed else "sans", 17),
               fill=C["teal"] if resumed else (C["ink3"] if ok == "--" else C["ink2"]), anchor="ra")
        d.text((M + 36, y + 48), clip(note.strip(), F("sans", 16), CW - 60), font=F("sans", 16), fill=C["ink3"])
        y += 86
        d.line([(M, y), (W - M, y)], fill=C["rule"], width=1)
    pg.y = y
    pg.finish("runs-crash-1440",
              notes="Rehearsal run: rules classifier with simulated latency. The same test on the fine-tuned LoRA on "
                    "Tinker (…-1a16-crashdemo, 344 events) kept 18 finished activities and retried 6.")


FIGS = {
    "home-card-1440": fig_card, "overview-1440": fig_overview, "inventory-drawer-1440": fig_inventory,
    "recalls-expanded-1440": fig_recall, "ebay-1440": fig_ebay, "billing-1440": fig_pricing,
    "temporal-crash-timeline-chart": fig_timeline, "runs-crash-1440": fig_runs,
}

if __name__ == "__main__":
    load()
    for name in sys.argv[1:] or FIGS:
        FIGS[name]()
