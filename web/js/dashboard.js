import { base, getJSON, cellAt } from "./data.js";
import { mercatorImage, corners, rampCSS } from "./overlay.js";
import { lineChart } from "./chart.js";

const params = new URLSearchParams(location.search);
const REGION = params.get("region") || "conus";
const B = base(REGION);
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
// signed number; small magnitudes get extra decimals so a real -0.02 never prints as "-0.0"
const sgn = (x, d = 2) => {
  if (x == null || !isFinite(x)) return "–";
  const dd = Math.abs(x) > 0 && Math.abs(x) < 10 ** -d ? d + 1 : d;
  const s = x.toFixed(dd);
  return Number(s) === 0 ? "0" : `${x > 0 ? "+" : ""}${s}`;
};
const pfmt = (p) => (p == null ? "–" : p < 0.001 ? "<0.001" : p.toFixed(3));
const RES_LABEL = { solar: "Solar", wind: "Wind", hydro: "Hydro", none: "Supporting" };
const THEME_LABEL = { hydrology: "Hydrology", cryosphere: "Cryosphere", atmospheric_dynamics: "Atmos. dynamics",
  atmospheric_chemistry: "Atmos. chemistry" };
const PRODUCT_LABEL = { reanalysis: "Reanalysis", model: "Model", gridded_observation: "Gridded observations",
  satellite_derived: "Satellite-derived", synthetic: "Synthetic" };
const SEASONS = ["annual", "DJF", "MAM", "JJA", "SON"];

const state = { variable: null, season: "annual", layer: "trend", pair: "r_solar_hydro", cell: null };
let catalog, narrative, portfolio, alerts, summaries = {}, map, marker, mapReady = false;

// ---------------------------------------------------------------------------------------------
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  for (const k of ["variable", "season", "layer", "pair"]) if (h.get(k)) state[k] = h.get(k);
}
function writeHash() {
  const h = new URLSearchParams({ variable: state.variable, season: state.season, layer: state.layer, pair: state.pair });
  history.replaceState(null, "", `#${h}`);
}
const varDef = (name) => catalog.variables.find((v) => v.name === name);
const entryFor = (v, season) => (season === "annual" ? v.annual : v.seasons[season]);

// ---------------------------------------------------------------------------------------------
async function init() {
  readHash();
  catalog = await getJSON(`${B}catalog.json`);
  const opt = (f) => (catalog.files[f] ? getJSON(`${B}${catalog.files[f]}`).catch(() => null) : Promise.resolve(null));
  [narrative, portfolio, alerts] = await Promise.all([opt("narrative"), opt("portfolio"), opt("alerts")]);
  await Promise.all(catalog.variables.map(async (v) => { summaries[v.name] = await getJSON(`${B}${v.annual.summary}`); }));
  if (!state.variable || !varDef(state.variable)) {
    state.variable = catalog.variables.find((v) => v.primary && v.resource === "solar")?.name || catalog.variables[0].name;
  }
  $("title").textContent = `Resource Trends: ${catalog.region.name}`;
  $("period").textContent = `${catalog.period} · ${catalog.region.analysis_deg}° analysis grid`;
  document.title = `Resource Trends · ${catalog.region.name}`;
  buildControls();
  renderCards();
  renderPortfolio();
  renderAlerts();
  renderRanking();
  renderFooter();
  update();          // panels render immediately; the map overlay follows once the basemap has loaded
  initMap();
}

// --- controls ---------------------------------------------------------------------------------
function buildControls() {
  $("layerSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.layer = b.dataset.layer; update();
  });
  $("pairSel").addEventListener("change", (e) => { state.pair = e.target.value; update(); });
  $("seasonSeg").innerHTML = SEASONS.map((s) => `<button data-season="${s}">${s === "annual" ? "Annual" : s}</button>`).join("");
  $("seasonSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b || b.disabled) return;
    state.season = b.dataset.season; update();
  });
  const groups = ["solar", "wind", "hydro", "none"];
  $("varList").innerHTML = groups.map((g) => {
    const vs = catalog.variables.filter((v) => v.resource === g);
    if (!vs.length) return "";
    return `<div class="grp">${RES_LABEL[g]}</div>` + vs.map((v) =>
      `<button data-var="${v.name}" title="${esc(v.long_name)}"><span>${esc(v.long_name)}${v.primary ? " ★" : ""}</span>` +
      `<span class="small muted">${esc(THEME_LABEL[v.theme])}</span></button>`).join("");
  }).join("");
  $("varList").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    selectVariable(b.dataset.var);
  });
}

function selectVariable(name, layer) {
  state.variable = name;
  if (layer) state.layer = layer;
  state.cell = null;
  update();
}

function syncControls() {
  for (const b of $("layerSeg").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.layer === state.layer));
  const v = varDef(state.variable);
  for (const b of $("seasonSeg").querySelectorAll("button")) {
    const s = b.dataset.season;
    b.disabled = s !== "annual" && !v.seasons[s];
    b.setAttribute("aria-pressed", String(s === state.season));
  }
  if (state.season !== "annual" && !v.seasons[state.season]) state.season = "annual";
  for (const b of $("varList").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.var === state.variable));
  $("seasonBlock").hidden = state.layer !== "trend";
  $("pairBlock").hidden = state.layer !== "portfolio";
  $("varBlock").hidden = state.layer === "portfolio";
  $("pairSel").value = state.pair;
}

// --- map --------------------------------------------------------------------------------------
// OpenStreetMap standard raster tiles: no API key (Carto's keyless tiles were withdrawn), allowed for
// light use with attribution. Desaturated to a quiet grey so it does not compete with the diverging
// overlay. (A vector basemap was tried first but could not be verified to render in headless checks.)
function basemapStyle() {
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  return {
    version: 8,
    sources: {
      osm: { type: "raster", tileSize: 256, maxzoom: 19, tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' },
    },
    layers: [{ id: "osm", type: "raster", source: "osm",
      paint: dark
        ? { "raster-saturation": -1, "raster-brightness-min": 0.0, "raster-brightness-max": 0.32, "raster-contrast": 0.1 }
        : { "raster-saturation": -1, "raster-brightness-min": 0.35, "raster-contrast": -0.25 } }],
  };
}

function firstLabelLayer() {
  return undefined;   // raster basemap: no separate label layers; overlay goes on top
}

function initMap() {
  const b = catalog.region.bbox;
  map = new maplibregl.Map({ container: "map", style: basemapStyle(), bounds: [[b.lon_min, b.lat_min], [b.lon_max, b.lat_max]],
    fitBoundsOptions: { padding: 20 }, attributionControl: { compact: true } });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  // attach the overlay as soon as the style is parsed, without waiting for every basemap tile
  map.once("style.load", () => { mapReady = true; updateOverlay(); });
  map.on("click", onMapClick);
  map.getCanvas().style.cursor = "crosshair";
}

function currentOverlay() {
  const v = varDef(state.variable);
  if (state.layer === "portfolio") {
    const m = catalog.portfolio_maps?.[state.pair];
    return m ? { png: m.png, legend: m.legend } : null;
  }
  if (state.layer === "alert") {
    const m = catalog.alert_maps?.[state.variable];
    return m ? { png: m.png, legend: m.legend, data_month: m.data_month } : null;
  }
  const e = entryFor(v, state.season);
  return { png: e.trend_png, legend: e.legend };
}

let overlaySeq = 0;
async function updateOverlay() {
  const ov = currentOverlay();
  const seq = ++overlaySeq;
  if (!ov) {
    if (map.getLayer("ov")) map.removeLayer("ov");
    if (map.getSource("ov")) map.removeSource("ov");
    renderLegend(null);
    return;
  }
  const url = await mercatorImage(`${B}${ov.png}`, ov.legend.bounds);
  if (seq !== overlaySeq) return;                     // a newer selection arrived meanwhile
  const coords = corners(ov.legend.bounds);
  const src = map.getSource("ov");
  if (src) src.updateImage({ url, coordinates: coords });
  else {
    map.addSource("ov", { type: "image", url, coordinates: coords });
    map.addLayer({ id: "ov", type: "raster", source: "ov", paint: { "raster-opacity": 0.9, "raster-resampling": "nearest", "raster-fade-duration": 0 } },
      firstLabelLayer());
  }
  renderLegend(ov);
}

function renderLegend(ov) {
  if (!ov) { $("legend").innerHTML = `<span class="muted">No map for this selection.</span>`; return; }
  const L = ov.legend;
  const tick = (x) => (Number.isInteger(x) || Math.abs(x) >= 10 ? x.toFixed(0) : Math.abs(x) >= 1 ? x.toFixed(1) : x.toFixed(2));
  let lo = L.vmin, hi = L.vmax, mid = 0, label = L.units;
  if (state.layer === "alert") { lo += 50; hi += 50; mid = 50; label = "trend-adjusted percentile"; }
  if (state.pair === "joint_low_ratio" && state.layer === "portfolio") { lo += 1; hi += 1; mid = 1; label = "joint-low ratio (1 = chance)"; }
  let note = L.note || "Faded cells: not significant (FDR 10%).";
  if (state.layer === "trend") {
    note = `${L.positive_color === "blue" ? "Blue = increase, red = decrease" : "Red = increase, blue = decrease"}. Faded: not significant (FDR 10%). Scale clipped at the 98th percentile.`;
  }
  $("legend").innerHTML = `<strong>${esc(label)}</strong><div class="ramp" style="background:${rampCSS(L.colors_neg_to_pos)}"></div>` +
    `<div class="ticks num"><span>${tick(lo)}</span><span>${tick(mid)}</span><span>${tick(hi)}</span></div>` +
    `<div class="small muted" style="margin-top:4px">${esc(note)}</div>`;
}

function renderMapTitle() {
  const v = varDef(state.variable);
  let t;
  if (state.layer === "portfolio") {
    t = `<strong>${esc($("pairSel").selectedOptions[0].text)}</strong> <span class="muted small">monthly anomalies, ${esc(portfolio?.regional?.period || "")}</span>`;
  } else if (state.layer === "alert") {
    const a = alerts?.alerts.find((x) => x.variable === state.variable);
    t = `<strong>${esc(v.long_name)}</strong> <span class="muted small">latest month ${esc(a?.data_month || "")} vs same-month baseline · anomaly, not forecast</span>`;
  } else {
    const e = entryFor(v, state.season);
    t = `<strong>${esc(v.long_name)}</strong> <span class="muted small">${state.season === "annual" ? "annual" : state.season} trend, ${esc(e.period)}</span>`;
  }
  $("mapTitle").innerHTML = t;
}

async function onMapClick(e) {
  if (state.layer === "portfolio") return;
  const v = varDef(state.variable);
  const { lat, lng } = e.lngLat;
  const cell = await cellAt(REGION, v.annual, lat, lng).catch(() => null);
  if (!cell) { $("cellInfo").textContent = "No data at that point (outside the region or masked)."; return; }
  state.cell = cell;
  if (!marker) marker = new maplibregl.Marker({ color: "#2a78d6", scale: 0.6 });
  marker.setLngLat([cell.lon, cell.lat]).addTo(map);
  renderSeries();
}

// --- right panel ------------------------------------------------------------------------------
function renderCards() {
  const prim = ["solar", "wind", "hydro"].map((r) => catalog.variables.find((v) => v.primary && v.resource === r)).filter(Boolean);
  $("cards").innerHTML = prim.map((v) => {
    const s = summaries[v.name], r = s.regional;
    const big = r.pct_change_per_decade != null ? `${sgn(r.pct_change_per_decade, 1)}%` : sgn(r.slope_per_decade);
    const sig = r.p_value != null && r.p_value < 0.05;
    return `<div class="card click" data-var="${v.name}" role="button" tabindex="0" aria-label="Show ${esc(v.long_name)}">
      <div class="small muted">${RES_LABEL[v.resource]}</div>
      <div class="big num">${big}<span class="unit"> /dec</span></div>
      <div class="small">${sig ? "significant" : "not significant"} (p ${pfmt(r.p_value)})</div>
      <div class="small muted">area ▲ ${pct(s.area_frac_sig_up)} ▼ ${pct(s.area_frac_sig_down)}</div>
      <div class="small muted">${esc(PRODUCT_LABEL[s.product_type] || s.product_type || "")}</div></div>`;
  }).join("");
  for (const c of $("cards").querySelectorAll(".card")) {
    c.addEventListener("click", () => selectVariable(c.dataset.var, "trend"));
    c.addEventListener("keydown", (e) => { if (e.key === "Enter") selectVariable(c.dataset.var, "trend"); });
  }
  $("cardsNote").textContent = `Regional (area-weighted) trend of each resource's headline index, ${catalog.period}. ▲▼ = share of the area with a significant trend.`;
}

function renderDetail() {
  const v = varDef(state.variable);
  const e = entryFor(v, state.season);
  const s = summaries[v.name];
  const sents = (narrative?.sentences || []).filter((x) => x.topic === v.name);
  const subs = (e.subregions || []).slice().sort((a, b) => a.mean - b.mean);
  const unit = e.legend.units;
  $("detail").innerHTML = `
    <h2>Selected variable</h2>
    <h3>${esc(v.long_name)}</h3>
    <div class="badges">
      <span class="chip">${esc(RES_LABEL[v.resource])}</span>
      <span class="chip">${esc(THEME_LABEL[v.theme])}</span>
      <span class="chip">${esc(PRODUCT_LABEL[s.product_type] || s.product_type || "")}</span>
      <span class="chip">${esc(s.provider)}</span>
      <span class="chip">${esc(e.period)} · ${s.n_years} yr</span>
      <span class="chip">${esc(v.status)}</span>
    </div>
    ${sents.map((x) => `<p class="sentence">${esc(x.text)}</p>`).join("")}
    ${state.season !== "annual" ? `<p class="note">Map shows the ${state.season} trend; the sentences above describe the annual trend.</p>` : ""}
    ${(v.caveats || []).map((c) => `<p class="note">${esc(c)}</p>`).join("")}
    ${subs.length ? `<table><thead><tr><th>Sub-region</th><th class="r">Mean change (${esc(unit)})</th><th class="r">Sig ▲</th><th class="r">Sig ▼</th></tr></thead><tbody>
      ${subs.map((x) => `<tr><td>${esc(x.name)}</td><td class="r num">${sgn(x.mean)}</td><td class="r num">${pct(x.frac_sig_up)}</td><td class="r num">${pct(x.frac_sig_down)}</td></tr>`).join("")}
    </tbody></table>` : ""}`;
}

function renderSeries() {
  const v = varDef(state.variable);
  const s = summaries[v.name];
  if (state.cell && state.cell.trend) {
    const c = state.cell, t = c.trend;
    $("seriesTitle").textContent = `Annual series · cell ${c.lat.toFixed(2)}°, ${c.lon.toFixed(2)}°`;
    lineChart($("chart"), { years: c.years, values: c.values, units: c.units, slopePerDecade: t.slope_per_decade,
      caption: `Dashed: Theil-Sen trend ${sgn(t.slope_per_decade, 3)} ${c.units}/decade${t.pct_change_per_decade != null ? ` (${sgn(t.pct_change_per_decade, 1)}%/decade)` : ""}.` });
    $("cellInfo").innerHTML = `Mann-Kendall p ${pfmt(t.p_value)}, FDR q ${pfmt(t.q_value)} → <strong>${t.significant ? "significant" : "not significant"}</strong> at FDR 10%. ` +
      `<a href="#" id="backRegional">Show regional mean</a>`;
    $("backRegional").addEventListener("click", (e) => { e.preventDefault(); state.cell = null; marker?.remove(); renderSeries(); });
    return;
  }
  const r = s.regional;
  const years = Object.keys(r.series).map(Number);
  $("seriesTitle").textContent = `Annual series · ${catalog.region.name} mean`;
  lineChart($("chart"), { years, values: Object.values(r.series), units: s.units, slopePerDecade: r.slope_per_decade,
    caption: `Area-weighted regional mean (annual ${s.aggregation}). Dashed: Theil-Sen trend ${sgn(r.slope_per_decade, 3)} ${s.units}/decade, p ${pfmt(r.p_value)}.` });
  $("cellInfo").textContent = "Click the map to see one grid cell.";
}

function renderPortfolio() {
  if (!portfolio) { $("portfolioBlock").hidden = true; return; }
  const c = portfolio.regional.correlations, jl = portfolio.regional.joint_low;
  const name = { solar_wind: "Solar · wind", solar_hydro: "Solar · hydro", wind_hydro: "Wind · hydro" };
  const read = (x) => (x.p >= 0.05 ? "little co-variation" : x.r < -0.1 ? "complementary" : x.r > 0.1 ? "move together" : "weak");
  $("portfolioBlock").innerHTML = `<h2>Do the resources cover for each other?</h2>
    <table><thead><tr><th>Pair</th><th class="r">r</th><th class="r">p</th><th>Reading</th></tr></thead><tbody>
    ${Object.entries(c).map(([k, x]) => `<tr class="click" data-pair="r_${k}"><td>${name[k] || k}</td><td class="r num">${sgn(x.r)}</td><td class="r num">${pfmt(x.p)}</td><td>${read(x)}</td></tr>`).join("")}
    </tbody></table>
    <p class="small">Two or more resources unusually low in the same month: <strong>${(jl.frequency * 100).toFixed(1)}%</strong> of months vs
    ${(jl.expected_independent * 100).toFixed(1)}% if independent (ratio ${jl.ratio.toFixed(2)}).</p>
    <p class="small muted">Contemporaneous monthly anomalies; runoff lags snowmelt, so lagged effects are not captured. Click a row to map it.</p>`;
  for (const tr of $("portfolioBlock").querySelectorAll("tr.click")) {
    tr.addEventListener("click", () => { state.pair = tr.dataset.pair; state.layer = "portfolio"; update(); });
  }
}

function statusHTML(s) {
  const map = { "strong alert": ["strong", "!!", "Strong alert"], alert: ["alert", "!", "Alert"], "local alert": ["local", "•", "Local alert"] };
  const m = map[s];
  return m ? `<span class="status ${m[0]}"><span class="ico" aria-hidden="true">${m[1]}</span>${m[2]}</span>` : `<span class="small muted">No alert</span>`;
}

function renderAlerts() {
  if (!alerts) { $("alertsBlock").hidden = true; return; }
  const active = alerts.alerts.filter((a) => a.status !== "none");
  const quiet = alerts.alerts.filter((a) => a.status === "none");
  const item = (a) => {
    const v = varDef(a.variable);
    const stale = a.latency_days > 120;
    const where = a.subregions.slice(0, 3).map((s) => `${s.name} ${pct(s.area_frac_adverse)}`).join(", ");
    return `<div class="alert-item click" data-var="${a.variable}">
      ${statusHTML(a.status)} <strong>${esc(v?.long_name || a.variable)}</strong>
      <div class="badges"><span class="chip">${esc(a.data_month)}</span>
        ${stale ? `<span class="chip warn" title="The source lags; this is not current">${Math.round(a.latency_days / 365 * 10) / 10} yr old data</span>` : `<span class="chip">${a.latency_days} days old</span>`}
        <span class="chip">${a.adverse === "low" ? "low is adverse" : a.adverse === "high" ? "high is adverse" : "both tails"}</span></div>
      <div class="small">Regional percentile ${a.regional.percentile?.toFixed(0) ?? "–"} (raw ${a.regional.percentile_raw?.toFixed(0) ?? "–"})${where ? ` · ${esc(where)}` : ""}</div></div>`;
  };
  $("alertsBlock").innerHTML = `<h2>Latest-month anomaly alerts</h2>
    <p class="small muted">${esc(alerts.label)}. Each variable's latest available month vs the same calendar month over the previous 30 years, trend-adjusted.</p>
    ${active.map(item).join("") || "<p class='small'>No active alerts.</p>"}
    <details><summary class="small">${quiet.length} variables without an alert</summary>${quiet.map(item).join("")}</details>`;
  for (const el of $("alertsBlock").querySelectorAll(".alert-item")) {
    el.addEventListener("click", () => selectVariable(el.dataset.var, "alert"));
  }
}

function renderRanking() {
  const rows = catalog.variables.map((v) => ({ v, s: summaries[v.name] }))
    .map((x) => ({ ...x, sig: x.s.area_frac_sig_up + x.s.area_frac_sig_down }))
    .sort((a, b) => b.sig - a.sig);
  $("rankBlock").innerHTML = `<h2>Where is change detectable?</h2>
    <table><thead><tr><th>Variable</th><th class="r">Sig ▲</th><th class="r">Sig ▼</th><th class="r">Regional /dec</th></tr></thead><tbody>
    ${rows.map(({ v, s }) => {
      const r = s.regional;
      const val = r.pct_change_per_decade != null ? `${sgn(r.pct_change_per_decade, 1)}%` : sgn(r.slope_per_decade);
      return `<tr class="click" data-var="${v.name}"><td>${esc(v.long_name)}</td><td class="r num">${pct(s.area_frac_sig_up)}</td>` +
        `<td class="r num">${pct(s.area_frac_sig_down)}</td><td class="r num">${val}</td></tr>`;
    }).join("")}</tbody></table>
    <p class="small muted">Share of the region with a statistically significant annual trend (FDR 10%), ${esc(catalog.period)}.</p>`;
  for (const tr of $("rankBlock").querySelectorAll("tr.click")) tr.addEventListener("click", () => selectVariable(tr.dataset.var, "trend"));
}

function renderFooter() {
  $("footer").innerHTML = `${catalog.disclaimers.map(esc).join(" ")}<br>${esc(catalog.method)}<br>
    Data: MERRA-2 (NASA GMAO via Earthdata), NASA POWER, TerraClimate, Daymet, NOAA nClimGrid (Microsoft Planetary Computer); validation: NOAA GSOM, USCRN.`;
}

async function update() {
  syncControls();
  writeHash();
  renderMapTitle();
  renderDetail();
  renderSeries();
  if (mapReady) await updateOverlay();
}

init().catch((err) => {
  document.body.insertAdjacentHTML("afterbegin", `<p style="padding:16px;color:var(--critical)">Could not load the export: ${esc(err.message)}.
  Serve the repository root (python -m http.server 8000) and open /web/dashboard.html?region=${esc(REGION)}.</p>`);
  console.error(err);
});
