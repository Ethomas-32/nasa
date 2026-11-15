// Single-series annual line chart in plain SVG: 2px line, recessive grid, dashed Theil-Sen line,
// crosshair + tooltip on hover (dataviz mark specs). No legend box for one series; the title names it.
const median = (a) => {
  const s = a.filter((x) => x != null && isFinite(x)).sort((p, q) => p - q);
  if (!s.length) return NaN;
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

function niceTicks(lo, hi, n = 4) {
  if (!(hi > lo)) { hi = lo + 1; }
  const raw = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

const fmt = (v) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toPrecision(3));

/** years[], values[] (nulls allowed); slopePerDecade (optional) draws the Sen line through the medians. */
export function lineChart(el, { years, values, units, slopePerDecade, caption }) {
  const W = 360, H = 190, m = { l: 44, r: 10, t: 10, b: 24 };
  const pts = years.map((y, i) => [y, values[i]]).filter(([, v]) => v != null && isFinite(v));
  el.innerHTML = "";
  if (!pts.length) { el.textContent = "No data for this cell."; return; }
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const x0 = Math.min(...years), x1 = Math.max(...years);
  const X = (x) => m.l + ((x - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
  const Y = (y) => H - m.b - ((y - lo) / (hi - lo)) * (H - m.t - m.b);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", caption || "annual series");
  const add = (tag, attrs, text) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    svg.appendChild(n);
    return n;
  };
  for (const t of niceTicks(lo, hi)) {
    add("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), stroke: "var(--grid)", "stroke-width": 1 });
    add("text", { x: m.l - 6, y: Y(t) + 4, "text-anchor": "end", "font-size": 10, fill: "var(--muted)" }, fmt(t));
  }
  for (const t of niceTicks(x0, x1, 4).filter((t) => Number.isInteger(t))) {
    add("text", { x: X(t), y: H - 6, "text-anchor": "middle", "font-size": 10, fill: "var(--muted)" }, t);
  }
  add("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1 });
  // series with gaps kept as gaps
  let d = "", pen = false;
  years.forEach((yr, i) => {
    const v = values[i];
    if (v == null || !isFinite(v)) { pen = false; return; }
    d += `${pen ? "L" : "M"}${X(yr).toFixed(1)},${Y(v).toFixed(1)}`;
    pen = true;
  });
  add("path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" });
  if (slopePerDecade != null && isFinite(slopePerDecade)) {
    const s = slopePerDecade / 10, mx = median(xs), my = median(ys), b = my - s * mx;
    add("line", { x1: X(x0), y1: Y(b + s * x0), x2: X(x1), y2: Y(b + s * x1), stroke: "var(--ink-2)",
      "stroke-width": 1.5, "stroke-dasharray": "5 4" });
  }
  const cross = add("line", { y1: m.t, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1, visibility: "hidden" });
  const dot = add("circle", { r: 4, fill: "var(--accent)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" });
  const hit = add("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  const tip = document.createElement("div");
  tip.className = "tip"; tip.hidden = true;
  el.append(svg, tip);
  hit.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const sx = ((e.clientX - r.left) / r.width) * W;
    const yr = Math.round(x0 + ((sx - m.l) / (W - m.l - m.r)) * (x1 - x0));
    const p = pts.reduce((a, b) => (Math.abs(b[0] - yr) < Math.abs(a[0] - yr) ? b : a));
    cross.setAttribute("x1", X(p[0])); cross.setAttribute("x2", X(p[0])); cross.setAttribute("visibility", "visible");
    dot.setAttribute("cx", X(p[0])); dot.setAttribute("cy", Y(p[1])); dot.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.textContent = `${p[0]}: ${fmt(p[1])} ${units || ""}`;
    const px = (X(p[0]) / W) * r.width, py = (Y(p[1]) / H) * r.height;
    tip.style.left = `${Math.min(px + 10, r.width - 120)}px`;
    tip.style.top = `${Math.max(py - 30, 0)}px`;
  });
  hit.addEventListener("pointerleave", () => {
    tip.hidden = true; cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden");
  });
  if (caption) {
    const cap = document.createElement("div");
    cap.className = "small muted";
    cap.textContent = caption;
    el.appendChild(cap);
  }
}
