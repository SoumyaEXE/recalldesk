// Shared helpers for the RecallDesk blog visuals.
// Signals are always shape + colour + label: DO NOT SELL = octagon (red), CHECK LABEL = triangle (amber),
// clear / no match = circle (green). Charts use emphasis encoding: ours in ink blue, everything else neutral.
window.RDV = (function () {
  const C = {
    match: "#b50909", check: "#e5a000", no_match: "#216e1f",
    matchS: "#f8e1de", checkS: "#faf3d1", no_matchS: "#e3f5e1",
    matchT: "#8b0a03", checkT: "#5c410a", no_matchT: "#154c21",
    ink: "#1b1b1b", ink2: "#565c65", ink3: "#71767a", grid: "#e6e8ea", rule: "#dfe1e2",
    ours: "#1a4480", other: "#c6cace", s1: "#005ea2", s2: "#c05600", a700: "#162e51", a50: "#eff6fb",
  };
  const LABEL = { match: "DO NOT SELL", check: "CHECK LABEL", no_match: "clear" };
  const VERDICT = { match: "match", check: "check", no_match: "no_match" };
  const MONO = 'font-family="Roboto Mono, monospace"';
  const NOTICE = 'font-family="Public Sans, sans-serif"';

  function octPts(cx, cy, r) {
    const pts = [];
    for (let i = 0; i < 8; i++) {
      const a = Math.PI / 8 + (i * Math.PI) / 4;
      pts.push((cx + r * Math.cos(a)).toFixed(2) + "," + (cy + r * Math.sin(a)).toFixed(2));
    }
    return pts.join(" ");
  }
  function triPts(cx, cy, r) {
    const h = r * 1.9, top = cy - h * 0.58, bot = cy + h * 0.42, half = h / Math.sqrt(3);
    return `${cx},${top.toFixed(2)} ${(cx + half).toFixed(2)},${bot.toFixed(2)} ${(cx - half).toFixed(2)},${bot.toFixed(2)}`;
  }
  // kind: match | check | no_match ; style: "fill" | "outline"
  function shape(kind, cx, cy, r, style = "fill", color) {
    const col = color || C[kind];
    const fill = style === "fill" ? col : "#ffffff";
    const sw = style === "fill" ? 0 : Math.max(1.4, r * 0.24);
    const common = `fill="${fill}" stroke="${col}" stroke-width="${sw}" stroke-linejoin="round"`;
    if (kind === "no_match") return `<circle cx="${cx}" cy="${cy}" r="${style === "fill" ? r : r - sw / 2}" ${common}/>`;
    if (kind === "check") return `<polygon points="${triPts(cx, cy, style === "fill" ? r * 1.08 : r)}" ${common}/>`;
    return `<polygon points="${octPts(cx, cy, style === "fill" ? r * 1.04 : r - sw / 2)}" ${common}/>`;
  }
  // glyph inside a stamp: white octagon for DO NOT SELL, dark "!" triangle for CHECK LABEL
  function glyph(kind, size = 13) {
    const r = size / 2;
    if (kind === "match")
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="vertical-align:-1px;flex:none"><polygon points="${octPts(r, r, r * 0.98)}" fill="#fff"/><rect x="${r * 0.45}" y="${r * 0.82}" width="${r * 1.1}" height="${r * 0.36}" fill="#b50909"/></svg>`;
    if (kind === "check")
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="vertical-align:-1px"><polygon points="${triPts(r, r * 1.08, r * 1.02)}" fill="#1b1b1b"/><rect x="${r - 0.8}" y="${r * 0.62}" width="1.6" height="${r * 0.62}" fill="#e5a000"/><rect x="${r - 0.8}" y="${r * 1.42}" width="1.6" height="1.6" fill="#e5a000"/></svg>`;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="vertical-align:-1px"><circle cx="${r}" cy="${r}" r="${r * 0.95}" fill="#fff"/></svg>`;
  }
  function stamp(kind, text) {
    const cls = kind === "match" ? "stop" : kind === "check" ? "check" : "clear";
    return `<span class="stamp ${cls}">${glyph(kind)}${text || LABEL[kind]}</span>`;
  }
  function icon(kind, size = 12, style = "fill") {
    const r = size / 2;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="vertical-align:-1px">${shape(kind, r, r, r * 0.9, style)}</svg>`;
  }
  const money = (v, d = 2) => (v == null ? "n/a" : v === 0 ? "$0" : "$" + (v < 0.01 ? v.toFixed(4) : v.toFixed(d)));
  const n = (v) => (v == null ? "n/a" : Number(v).toLocaleString("en-US"));
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const frac = (s) => { const m = String(s || "").match(/(\d+)\s*\/\s*(\d+)/); return m ? [+m[1], +m[2]] : [0, 0]; };
  const short = (s, k) => (s && s.length > k ? s.slice(0, k - 1).trimEnd() + "…" : s || "");

  const SRC_OF = { scan: "scan_summary", eval: "eval", training: "training", spend: "spend", crash: "crash",
                   memory: "memory", corpus: "recalls", card: "card", example: "eval" };

  // Watermark the frame if any listed section is not real. Returns the worst status.
  function mark(sections) {
    const frame = document.getElementById("frame");
    let worst = "real", whys = [];
    sections.forEach((s) => {
      const sec = s === "example" ? RD.eval.example : RD[s];
      const st = (sec && sec.status) || "placeholder";
      const src = (RD.sources || {})[SRC_OF[s]] || {};
      if (st === "placeholder") { worst = "placeholder"; whys.push(`${src.path || s}${src.why ? " (" + src.why + ")" : ""}`); }
      else if (st === "provisional" && worst !== "placeholder") { worst = "provisional"; whys.push(`${src.path || s}: ${src.why || "provisional"}`); }
    });
    // Real eval scored against the project's answer key (teacher + rule 7 by code): a footnote, not a watermark.
    const usesEval = sections.some((s) => s === "eval" || s === "example");
    if (usesEval && worst !== "placeholder" && RD.eval && RD.eval.answer_key !== "human") {
      const src = frame.querySelector(".src span:not(.brand)");
      const note = RD.eval.answer_key === "targets" ? "answer key: teacher + rule 7, not human" : "answer key: raw teacher labels, not human";
      if (src) src.innerHTML += ` · <b>${note}</b>`;
    }
    if (worst === "real") return worst;
    const ph = worst === "placeholder";
    const word = ph ? "PLACEHOLDER · NOT REAL DATA" : "PROVISIONAL · RAW TEACHER LABELS";
    const col = ph ? "#b50909" : "#936f38";
    const w = frame.offsetWidth, h = frame.offsetHeight;
    let t = "";
    for (let y = -h; y < h * 2; y += 92) for (let x = -w; x < w * 2; x += 430)
      t += `<text x="${x + ((y / 92) % 2 ? 215 : 0)}" y="${y}" ${MONO} font-size="21" font-weight="700" letter-spacing="3" fill="${col}" fill-opacity="${ph ? 0.13 : 0.11}">${word}</text>`;
    const wm = document.createElement("div");
    wm.className = "wm";
    wm.innerHTML = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><g transform="rotate(-18 ${w / 2} ${h / 2})">${t}</g></svg>`;
    frame.appendChild(wm);
    const b = document.createElement("div");
    b.className = "wm-badge" + (ph ? "" : " prov");
    b.innerHTML = `${ph ? "Placeholder" : "Provisional"}<small>${esc(whys.join("; "))}</small>`;
    frame.appendChild(b);
    return worst;
  }
  return { C, LABEL, VERDICT, MONO, NOTICE, shape, glyph, stamp, icon, money, n, esc, frac, short, mark };
})();
