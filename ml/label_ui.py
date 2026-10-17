"""Blind human labeling UI for an optional audit of the test set (not used for the reported eval numbers,
which are graded against teacher + rule 7 by code; see ml/eval.py --gold).

    python -m ml.label_ui                # http://localhost:8765  (test split)
    python -m ml.label_ui --port 8765 --split test

Shows ONE (recall, listing) pair at a time, grouped by recall (read the recall once, then label its listings).
Keys: 1 = match, 2 = check, 3 = no_match, s = skip, u = undo, n = note, g = guide. Appends to data/gold/labels.jsonl
({"pair_id","label","note","labeled_at"}). It NEVER shows any model / teacher / heuristic output: the only
highlighting is the deterministic regex identifiers from the CPSC text.
"""
from __future__ import annotations

import argparse
import html
import json
import random
import threading
import time
from pathlib import Path

from ml.common import GOLD, ROOT, SPLITS, load_listings, load_recalls, now_iso, read_jsonl, utf8_stdout

LABELS_P = GOLD / "labels.jsonl"
SKIPS_P = GOLD / "skips.jsonl"
_lock = threading.Lock()


class Store:
    def __init__(self, split: str, seed: int = 0):
        rows = read_jsonl(SPLITS / f"{split}.jsonl") if split != "all" else (
            read_jsonl(SPLITS / "test.jsonl") + read_jsonl(SPLITS / "train.jsonl"))
        if not rows:
            raise SystemExit(f"data/splits/{split}.jsonl is empty/missing - run: python -m ml.make_pairs")
        self.recalls = {r["recall_number"]: r for r in load_recalls("AB")}
        self.listings = load_listings()
        rows = [r for r in rows if r["recall_number"] in self.recalls and r["listing_id"] in self.listings]
        by_recall: dict[str, list[dict]] = {}
        for r in rows:
            by_recall.setdefault(r["recall_number"], []).append(r)
        rng = random.Random(seed)
        order = sorted(by_recall)
        rng.shuffle(order)
        self.queue: list[dict] = []
        for rn in order:
            items = sorted(by_recall[rn], key=lambda x: x["pair_id"])
            rng.shuffle(items)
            self.queue.extend(items)
        self.by_pair = {r["pair_id"]: r for r in self.queue}
        self.session_times: list[float] = []
        self.last_t: float | None = None

    # -- persistence
    def labels(self) -> dict[str, dict]:
        out = {}
        for r in read_jsonl(LABELS_P):
            if r.get("pair_id") in self.by_pair:
                out[r["pair_id"]] = r
        return out

    def skips(self) -> set[str]:
        lab = self.labels()
        return {r["pair_id"] for r in read_jsonl(SKIPS_P) if r["pair_id"] not in lab}

    def next_item(self) -> dict | None:
        lab, sk = self.labels(), self.skips()
        for r in self.queue:
            if r["pair_id"] not in lab and r["pair_id"] not in sk:
                return r
        for r in self.queue:  # skipped ones come back at the end
            if r["pair_id"] not in lab:
                return r
        return None

    def state(self) -> dict:
        lab = self.labels()
        counts = {"match": 0, "check": 0, "no_match": 0}
        for r in lab.values():
            counts[r["label"]] = counts.get(r["label"], 0) + 1
        total, done = len(self.queue), len(lab)
        ts = self.session_times[-30:]
        per = (sum(ts) / len(ts)) if ts else None
        nxt = self.next_item()
        payload = None
        if nxt:
            rec = self.recalls[nxt["recall_number"]]
            lst = self.listings[nxt["listing_id"]]
            same = [r for r in self.queue if r["recall_number"] == nxt["recall_number"]]
            payload = {
                "pair_id": nxt["pair_id"], "skipped": nxt["pair_id"] in self.skips(),
                "recall_pos": [sum(1 for r in same if r["pair_id"] in lab) + 1, len(same)],
                "recall": {k: rec.get(k) for k in ("recall_number", "recall_date", "title", "description", "url",
                                                   "product_names", "units", "hazards", "remedies", "remedy_options",
                                                   "retailers", "manufacturers", "importers", "images", "upcs",
                                                   "regex_ids", "is_childrens")},
                "listing": {k: lst.get(k) for k in ("listing_id", "title", "subtitle", "condition", "price", "link",
                                                    "thumbnail", "item_specifics", "source")},
            }
        return {"total": total, "done": done, "counts": counts, "skipped": len(self.skips()),
                "sec_per_label": round(per, 1) if per else None,
                "eta_min": round(per * (total - done) / 60, 1) if per else None, "item": payload}

    def label(self, pair_id: str, label: str, note: str | None) -> None:
        if pair_id not in self.by_pair or label not in ("match", "check", "no_match"):
            raise ValueError("bad pair or label")
        now = time.time()
        if self.last_t and now - self.last_t < 600:
            self.session_times.append(now - self.last_t)
        self.last_t = now
        with _lock:
            GOLD.mkdir(parents=True, exist_ok=True)
            with LABELS_P.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"pair_id": pair_id, "label": label, "note": note or None,
                                    "labeled_at": now_iso()}, ensure_ascii=False) + "\n")

    def skip(self, pair_id: str) -> None:
        with _lock:
            GOLD.mkdir(parents=True, exist_ok=True)
            with SKIPS_P.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"pair_id": pair_id, "skipped_at": now_iso()}) + "\n")

    def undo(self) -> str | None:
        with _lock:
            rows = read_jsonl(LABELS_P)
            if not rows:
                return None
            last = rows.pop()
            tmp = LABELS_P.with_suffix(".jsonl.tmp")
            tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            tmp.replace(LABELS_P)
            # un-skip it too so it comes back right now
            sk = [r for r in read_jsonl(SKIPS_P) if r["pair_id"] != last["pair_id"]]
            if SKIPS_P.exists():
                SKIPS_P.write_text("".join(json.dumps(r) + "\n" for r in sk), encoding="utf-8")
            if self.session_times:
                self.session_times.pop()
            return last["pair_id"]


def guide_html() -> str:
    p = ROOT / "ml" / "LABELING.md"
    if not p.exists():
        from ml.prompts import DEFINITIONS

        return "<pre>" + html.escape(DEFINITIONS) + "</pre>"
    out: list[str] = []
    mode = None  # None | "ul" | "table" | "p"

    def close() -> None:
        nonlocal mode
        if mode == "ul":
            out.append("</ul>")
        elif mode == "table":
            out.append("</table>")
        mode = None

    for line in p.read_text(encoding="utf-8").splitlines():
        s = html.escape(line.strip())
        s = "".join(f"<b>{x}</b>" if i % 2 else x for i, x in enumerate(s.split("**")))
        s = "".join(f"<code>{x}</code>" if i % 2 else x for i, x in enumerate(s.split("`")))
        st = line.strip()
        if not st:
            close()
        elif st.startswith("|"):
            if set(st) <= set("|-: "):
                continue
            if mode != "table":
                close()
                out.append('<table class="spec">')
                mode = "table"
            out.append("<tr>" + "".join(f"<td>{c.strip()}</td>" for c in s.strip("|").split("|")) + "</tr>")
        elif st.startswith("#"):
            close()
            lvl = min(4, len(st) - len(st.lstrip("#")) + 1)
            out.append(f"<h{lvl}>{s.lstrip('#').strip()}</h{lvl}>")
        elif st.startswith(("- ", "* ")) or (st[:1].isdigit() and st[1:3] in (". ", ") ")):
            if mode != "ul":
                close()
                out.append("<ul>")
                mode = "ul"
            out.append(f"<li>{s.lstrip('-* ')}</li>")
        elif mode in ("ul", "p") and out:
            end = "</li>" if mode == "ul" else "</p>"
            out[-1] = out[-1][: -len(end)] + " " + s + end  # continuation line
        else:
            close()
            out.append(f"<p>{s}</p>")
            mode = "p"
    close()
    return "\n".join(out)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RecallDesk gold labels</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--mute:#6b6a65;--line:#e3e1db;--hl:#ffe58a;--m:#c62828;--c:#b26a00;--n:#2e7d32;--acc:#1f4e8c}
@media (prefers-color-scheme: dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe7;--mute:#9b9a94;--line:#33322f;--hl:#6b5a00;--acc:#8fb4ff}}
a{color:var(--acc)}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header b{font-size:16px}.bar{flex:1;min-width:180px;height:8px;background:var(--line);border-radius:4px;overflow:hidden}.bar>i{display:block;height:100%;background:var(--acc);width:0}
.pill{padding:2px 8px;border-radius:10px;font-size:13px;border:1px solid var(--line)}.pm{color:var(--m)}.pc{color:var(--c)}.pn{color:var(--n)}
details.guide{margin:10px 16px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 14px}details.guide summary{cursor:pointer;font-weight:600}
details.guide h2,details.guide h3,details.guide h4{margin:12px 0 4px}details.guide p,details.guide li{margin:3px 0;font-size:14px}
main{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:12px 16px 110px}@media(max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:0}
.card h2{margin:0 0 6px;font-size:18px;line-height:1.3}.k{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-top:10px}
.desc{white-space:pre-wrap;max-height:42vh;overflow:auto;border-left:3px solid var(--line);padding-left:10px}
mark{background:var(--hl);color:inherit;padding:0 2px;border-radius:2px}
.ids code{display:inline-block;margin:2px 4px 2px 0;padding:1px 6px;background:var(--bg);border:1px solid var(--line);border-radius:4px;font-size:13px}
.imgs{display:flex;gap:8px;flex-wrap:wrap}.imgs img{max-height:150px;max-width:48%;border-radius:6px;border:1px solid var(--line);background:#fff}
.lt{font-size:20px;font-weight:600;line-height:1.3;margin:4px 0 8px}.lt a{color:inherit;text-decoration:none}.lt a:hover{text-decoration:underline}
.limg{max-width:100%;max-height:300px;border-radius:8px;border:1px solid var(--line);background:#fff;display:block;margin:8px 0}
table.spec{border-collapse:collapse;font-size:13px}table.spec td{border-top:1px solid var(--line);padding:3px 8px 3px 0;vertical-align:top}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{font:inherit;padding:10px 16px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
button.m{border-color:var(--m);color:var(--m)}button.c{border-color:var(--c);color:var(--c)}button.n{border-color:var(--n);color:var(--n)}
button:hover{filter:brightness(.95)}kbd{font-size:11px;border:1px solid var(--line);border-radius:3px;padding:0 4px;margin-left:6px;color:var(--mute)}
#note{flex:1;min-width:160px;padding:9px 10px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font:inherit}
.flash{animation:fl .35s}@keyframes fl{from{background:var(--hl)}to{background:var(--card)}}
.done{padding:60px;text-align:center;font-size:20px}.newrec{outline:3px solid var(--acc)}
.tag{font-size:12px;padding:1px 6px;border-radius:4px;background:var(--bg);border:1px solid var(--line);margin-right:4px}
</style></head><body>
<header><b>RecallDesk &middot; gold labels</b><div class="bar"><i id="bar"></i></div>
<span id="prog"></span><span class="pill pm" id="cm"></span><span class="pill pc" id="cc"></span><span class="pill pn" id="cn"></span>
<span class="pill" id="eta"></span></header>
<details class="guide" id="guide"><summary>Labeling guide (press g)</summary>__GUIDE__</details>
<div id="app"></div>
<footer>
<button class="m" onclick="lab('match')">match<kbd>1</kbd></button>
<button class="c" onclick="lab('check')">check<kbd>2</kbd></button>
<button class="n" onclick="lab('no_match')">no_match<kbd>3</kbd></button>
<button onclick="skip()">skip<kbd>s</kbd></button><button onclick="undo()">undo<kbd>u</kbd></button>
<input id="note" placeholder="note (press n) - saved with the next label"></footer>
<script>
let S=null, lastRecall=null;
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function norm(s){return s.toUpperCase().replace(/[\s\-./_]/g,'')}
function hl(text, ids){
  let t=esc(text); if(!ids||!ids.length) return t;
  const pats=ids.filter(i=>i&&i.length>=3).map(i=>i.split('').map(ch=>/[\-./_\s]/.test(ch)?'':ch.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).filter(Boolean).join('[\\s\\-./_]?'));
  if(!pats.length) return t;
  pats.sort((a,b)=>b.length-a.length);
  try{const re=new RegExp('(?<![A-Za-z0-9])('+pats.join('|')+')(?![A-Za-z0-9])','gi'); return t.replace(re,'<mark>$1</mark>');}catch(e){return t}
}
function list(xs){return (xs||[]).map(esc).join('<br>')}
function render(){
  const s=S; document.getElementById('bar').style.width=(100*s.done/Math.max(1,s.total))+'%';
  document.getElementById('prog').textContent=s.done+' / '+s.total+(s.skipped?' ('+s.skipped+' skipped)':'');
  document.getElementById('cm').textContent='match '+s.counts.match; document.getElementById('cc').textContent='check '+s.counts.check;
  document.getElementById('cn').textContent='no_match '+s.counts.no_match;
  document.getElementById('eta').textContent=s.eta_min!=null?('~'+s.sec_per_label+'s each, ETA '+s.eta_min+' min'):'ETA after a few labels';
  const app=document.getElementById('app');
  if(!s.item){app.innerHTML='<div class="done">All pairs labeled. Thank you! Labels are in data/gold/labels.jsonl</div>';return}
  const r=s.item.recall, l=s.item.listing, ids=(r.regex_ids||[]).concat(r.upcs||[]);
  const isNew=lastRecall!==r.recall_number; lastRecall=r.recall_number;
  const imgs=(r.images||[]).slice(0,2).map(u=>'<img loading="lazy" src="'+esc(u)+'" referrerpolicy="no-referrer" onerror="this.remove()">').join('');
  const sp=l.item_specifics||{}; const spRows=Object.keys(sp).map(k=>'<tr><td>'+esc(k)+'</td><td>'+esc(Array.isArray(sp[k])?sp[k].join(', '):sp[k])+'</td></tr>').join('');
  app.innerHTML='<main>'+
   '<section class="card'+(isNew?' newrec':'')+'"><div class="k">Recall '+esc(r.recall_number)+' &middot; '+esc(r.recall_date)+' &middot; listing '+s.item.recall_pos[0]+' of '+s.item.recall_pos[1]+' for this recall'+(r.is_childrens?' &middot; <span class="tag">children\'s</span>':'')+'</div>'+
   '<h2>'+hl(r.title,ids)+'</h2><div><b>'+hl((r.product_names||[]).join(' ; '),ids)+'</b>'+(r.units?' <span class="tag">'+esc(r.units)+' units</span>':'')+'</div>'+
   (ids.length?'<div class="k">Identifiers in the notice (regex)</div><div class="ids">'+ids.map(i=>'<code>'+esc(i)+'</code>').join('')+'</div>':'<div class="k">No identifiers found in the notice text</div>')+
   '<div class="k">Description</div><div class="desc">'+hl(r.description,ids)+'</div>'+
   '<div class="imgs" style="margin-top:8px">'+imgs+'</div>'+
   '<div class="k">Sold</div><div>'+list(r.retailers)+'</div>'+
   '<div class="k">Hazard</div><div>'+list(r.hazards)+'</div>'+
   '<div class="k">Remedy</div><div>'+esc((r.remedy_options||[]).join(', '))+' &mdash; '+esc(((r.remedies||[])[0]||'').slice(0,300))+'</div>'+
   '<div class="k">Firm</div><div>'+list((r.manufacturers||[]).concat(r.importers||[]))+'</div>'+
   (r.url?'<div style="margin-top:8px"><a href="'+esc(r.url)+'" target="_blank" rel="noopener">CPSC notice &#8599;</a></div>':'')+
   '</section>'+
   '<section class="card flash"><div class="k">eBay listing &middot; '+esc(l.listing_id)+(s.item.skipped?' &middot; previously skipped':'')+'</div>'+
   '<div class="lt"><a href="'+esc(l.link)+'" target="_blank" rel="noopener">'+hl(l.title,ids)+' &#8599;</a></div>'+
   (l.subtitle?'<div>'+hl(l.subtitle,ids)+'</div>':'')+
   '<div style="margin-top:6px">'+(l.condition?'<span class="tag">'+esc(l.condition)+'</span>':'')+(l.price?'<span class="tag">'+esc(l.price)+'</span>':'')+'</div>'+
   (l.thumbnail?'<img class="limg" src="'+esc(l.thumbnail)+'" referrerpolicy="no-referrer" onerror="this.remove()">':'')+
   (spRows?'<div class="k">Item details</div><table class="spec">'+spRows+'</table>':'')+
   '</section></main>';
  if(isNew) window.scrollTo(0,0);
}
async function refresh(){S=await (await fetch('/api/state')).json(); render()}
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); S=await r.json(); render()}
function lab(l){if(!S||!S.item)return; const n=document.getElementById('note'); post('/api/label',{pair_id:S.item.pair_id,label:l,note:n.value||null}); n.value=''}
function skip(){if(S&&S.item) post('/api/skip',{pair_id:S.item.pair_id})}
function undo(){post('/api/undo',{})}
document.addEventListener('keydown',e=>{
  const note=document.getElementById('note');
  if(document.activeElement===note){ if(e.key==='Enter'||e.key==='Escape'){note.blur(); e.preventDefault()} return }
  if(e.ctrlKey||e.metaKey||e.altKey) return;
  const k=e.key.toLowerCase();
  if(k==='1')lab('match'); else if(k==='2')lab('check'); else if(k==='3')lab('no_match');
  else if(k==='s')skip(); else if(k==='u')undo();
  else if(k==='n'){e.preventDefault(); note.focus()}
  else if(k==='g'){const g=document.getElementById('guide'); g.open=!g.open}
});
refresh();
</script></body></html>"""


def build_app(store: Store):
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="RecallDesk label UI")
    page = PAGE.replace("__GUIDE__", guide_html())

    @app.get("/", response_class=HTMLResponse)
    def index():
        return page

    @app.get("/api/state")
    def state():
        return JSONResponse(store.state())

    @app.post("/api/label")
    def label(body: dict):
        try:
            store.label(body.get("pair_id"), body.get("label"), body.get("note"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return JSONResponse(store.state())

    @app.post("/api/skip")
    def skip(body: dict):
        store.skip(body.get("pair_id"))
        return JSONResponse(store.state())

    @app.post("/api/undo")
    def undo(body: dict | None = None):
        store.undo()
        return JSONResponse(store.state())

    return app


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--split", default="test", choices=["test", "train", "all"])
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    store = Store(args.split, args.seed)
    st = store.state()
    print(f"{st['total']} pairs ({st['done']} labeled) -> http://localhost:{args.port}   labels: {LABELS_P}")
    import uvicorn

    uvicorn.run(build_app(store), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
