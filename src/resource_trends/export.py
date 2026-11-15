"""Export contract (CLAUDE.md section 7): static files under export/<region>/ that a front end reads.

Builds, on top of the pipeline / portfolio / alerts / validation outputs already in the directory:
- `<stem>.trend.png`   trend overlay, north-up, one pixel per grid cell, with bounds + legend in the catalog
- `pixel_series/<var>/<lat0>_<lon0>.json`  annual per-cell series in 5-degree tiles (click-for-series)
- `narrative.json`     plain-language sentences templated ONLY from computed numbers
- `catalog.json`       the index: every variable, its metadata, caveats and file paths
and validates every file against JSON schemas (`validate_export`).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import masks, preprocess, sources
from .registry import Registry

CONTRACT_VERSION = "1.0"
TILE_DEG = 5.0
NONSIG_ALPHA = 0.35
# Diverging ramp (dataviz reference palette): blue arm (ramp steps 650, 400), neutral gray midpoint,
# red arm (series red, darkened end). Index 0 = most negative, -1 = most positive.
NEG_TO_POS_BLUE_RED = ["#104281", "#3987e5", "#f0efec", "#e34948", "#8f1d1d"]
WATER_THEMES = {"hydrology", "cryosphere"}


# --- helpers ------------------------------------------------------------------------------------
def _hex(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)


def _ramp(stops, x):
    """Linear interpolation of RGB stops at positions in [0, 1]."""
    cols = np.stack([_hex(s) for s in stops])
    pos = np.linspace(0, 1, len(stops))
    return np.stack([np.interp(x, pos, cols[:, k]) for k in range(3)], axis=-1)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), indent=1))


def _bounds(lat, lon):
    dlat = float(np.abs(np.diff(lat)).mean()) if len(lat) > 1 else 1.0
    dlon = float(np.abs(np.diff(lon)).mean()) if len(lon) > 1 else 1.0
    return {"south": float(lat.min() - dlat / 2), "north": float(lat.max() + dlat / 2),
            "west": float(lon.min() - dlon / 2), "east": float(lon.max() + dlon / 2)}


# --- PNG overlay --------------------------------------------------------------------------------
def render_png(values, opaque, lat, lon, path: Path, field: str, positive_color: str = "red",
               vmax: float | None = None) -> dict:
    """North-up RGBA PNG of a diverging field centred on 0, one pixel per cell. NaN transparent;
    cells where `opaque` is False are faded to NONSIG_ALPHA. Returns legend + bounds for the catalog."""
    from PIL import Image
    v = np.asarray(values, dtype=float)
    finite = np.isfinite(v)
    if vmax is None:
        vmax = float(np.nanpercentile(np.abs(v[finite]), 98)) if finite.any() else 1.0
    vmax = vmax if vmax > 0 else 1.0
    stops = NEG_TO_POS_BLUE_RED if positive_color == "red" else NEG_TO_POS_BLUE_RED[::-1]
    x = np.clip((np.nan_to_num(v) / vmax + 1) / 2, 0, 1)
    rgb = _ramp(stops, x)
    alpha = np.where(finite, np.where(np.asarray(opaque, bool), 255, round(255 * NONSIG_ALPHA)), 0)
    rgba = np.concatenate([rgb, alpha[..., None]], axis=-1).astype(np.uint8)
    lat = np.asarray(lat)
    if lat[0] < lat[-1]:
        rgba = rgba[::-1]                                   # north-up
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(path)
    return {
        "field": field,
        "vmin": -vmax, "vmax": vmax,
        "colors_neg_to_pos": stops,
        "positive_color": positive_color,
        "nonsignificant_alpha": NONSIG_ALPHA,
        "transparent": "no data / outside region",
        "bounds": _bounds(lat, np.asarray(lon)),
        "width": int(rgba.shape[1]), "height": int(rgba.shape[0]),
    }


def render_trend_png(ds: xr.Dataset, path: Path, field: str, positive_color: str = "red") -> dict:
    """Trend overlay: colour = `field`, opaque where FDR-significant."""
    return render_png(ds[field].values, ds["significant"].values.astype(bool), ds["lat"].values, ds["lon"].values,
                      path, field, positive_color)


# --- pixel series -------------------------------------------------------------------------------
def write_pixel_series(annual: xr.DataArray, var_dir: Path, units: str, tile_deg: float = TILE_DEG,
                       trend: xr.Dataset | None = None) -> dict:
    """Annual per-cell series grouped into tile_deg x tile_deg JSON tiles. If `trend` (the annual
    trend Dataset on the same grid) is given, each cell also carries its tested trend statistics, so a
    click shows the real result rather than one recomputed in the browser. Returns an index."""
    years = [int(y) for y in annual["year"].values]
    lat, lon = annual["lat"].values, annual["lon"].values
    vals = annual.transpose("year", "lat", "lon").values
    stat_fields = [f for f in ("slope_per_decade", "pct_change_per_decade", "total_change", "p_value", "q_value",
                               "significant", "direction") if trend is not None and f in trend]
    if trend is not None:
        assert trend.sizes["lat"] == lat.size and trend.sizes["lon"] == lon.size, "trend grid != series grid"
        tv = {f: trend[f].values for f in stat_fields}
    tiles = {}
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            s = vals[:, i, j]
            if not np.isfinite(s).any():
                continue
            key = (math.floor(la / tile_deg) * tile_deg, math.floor(lo / tile_deg) * tile_deg)
            cell = {"lat": round(float(la), 4), "lon": round(float(lo), 4),
                    "values": [None if not np.isfinite(x) else float(f"{x:.5g}") for x in s]}
            if trend is not None:
                cell["trend"] = {f: (bool(tv[f][i, j]) if f == "significant" else
                                     (None if not np.isfinite(tv[f][i, j]) else float(f"{tv[f][i, j]:.5g}")))
                                 for f in stat_fields}
            tiles.setdefault(key, []).append(cell)
    names = []
    for (la0, lo0), cells in sorted(tiles.items()):
        name = f"{la0:+06.1f}_{lo0:+07.1f}.json"
        _write_json(var_dir / name, {"variable": annual.name, "units": units, "years": years,
                                     "tile": {"south": la0, "west": lo0, "size_deg": tile_deg}, "cells": cells})
        names.append(name)
    return {"dir": var_dir.name, "tile_deg": tile_deg, "naming": "{floor(lat/5)*5:+06.1f}_{floor(lon/5)*5:+07.1f}.json",
            "tiles": names, "years": [years[0], years[-1]]}


# --- sub-regional numbers + narrative -----------------------------------------------------------
def subregion_stats(ds: xr.Dataset, subregions: dict, field: str) -> list[dict]:
    out = []
    for name, b in subregions.items():
        s = ds.sel(lat=slice(b["lat_min"], b["lat_max"]), lon=slice(b["lon_min"], b["lon_max"]))
        if s.sizes["lat"] == 0 or s.sizes["lon"] == 0:
            continue
        w = np.cos(np.deg2rad(s["lat"].values))[:, None] * np.ones(s.sizes["lon"])
        v = s[field].values
        ok = np.isfinite(v)
        if not ok.any():
            continue
        sig = s["significant"].values.astype(bool)
        slope = s["slope_per_decade"].values
        wv = (w * ok).sum()
        out.append({"name": name, "mean": float((w * np.where(ok, v, 0)).sum() / wv),
                    "frac_sig_up": float((w * (sig & (slope > 0) & ok)).sum() / wv),
                    "frac_sig_down": float((w * (sig & (slope < 0) & ok)).sum() / wv)})
    return out


def _fmt(x, d=2):
    return f"{x:+.{d}f}"


def variable_sentences(var: str, vdef: dict, s: dict, subs: list[dict], region_name: str) -> list[dict]:
    r = s["regional"]
    pct = r.get("pct_change_per_decade")
    units = s["units"]
    sig = r["p_value"] is not None and r["p_value"] < 0.05
    trend_txt = (f"{_fmt(r['slope_per_decade'], 3)} {units} per decade"
                 + (f" ({_fmt(pct, 1)}% per decade)" if pct is not None else ""))
    out = [{
        "id": f"{var}.regional", "topic": var,
        "text": (f"{vdef.get('long_name', var)} over {region_name}, {s['period']}: the area-averaged trend is {trend_txt}, "
                 + ("statistically significant" if sig else "not statistically significant")
                 + f" (p = {r['p_value']:.2g}). {s['area_frac_sig_up']:.0%} of the area shows a significant increase and "
                 f"{s['area_frac_sig_down']:.0%} a significant decrease (false discovery rate 10%)."),
        "numbers": {"slope_per_decade": r["slope_per_decade"], "pct_per_decade": pct, "p": r["p_value"],
                    "area_frac_sig_up": s["area_frac_sig_up"], "area_frac_sig_down": s["area_frac_sig_down"]},
        "source": f"{var}.summary.json",
    }]
    if s["area_frac_sig_up"] >= 0.05 and s["area_frac_sig_down"] >= 0.05:
        out.append({"id": f"{var}.opposing", "topic": var,
                    "text": f"Significant trends run in opposite directions in different parts of {region_name}.",
                    "numbers": {"opposing_trend_score": s["opposing_trend_score"]}, "source": f"{var}.summary.json"})
    unit_word = "% per decade" if pct is not None else f" {units} per decade"
    sig_subs = [x for x in subs if max(x["frac_sig_up"], x["frac_sig_down"]) >= 0.1]
    if subs:
        lo = min(subs, key=lambda x: x["mean"])
        hi = max(subs, key=lambda x: x["mean"])
        txt = (f"By sub-region, the mean change ranges from {_fmt(lo['mean'], 2)}{unit_word} ({lo['name']}) to "
               f"{_fmt(hi['mean'], 2)}{unit_word} ({hi['name']}).")
        if sig_subs:
            txt += " Sub-regions with at least 10% of their area significant: " + ", ".join(
                f"{x['name']} ({x['frac_sig_up']:.0%} up, {x['frac_sig_down']:.0%} down)" for x in sig_subs) + "."
        else:
            txt += " No sub-region has 10% or more of its area significant, so these are directions, not detected trends."
        out.append({"id": f"{var}.subregions", "topic": var, "text": txt,
                    "numbers": {"subregions": subs}, "source": f"{var}.trend.nc"})
    bp = s.get("breakpoint", {})
    if bp.get("p") is not None and bp["p"] < 0.05:
        out.append({"id": f"{var}.breakpoint", "topic": var,
                    "text": (f"Caution: a possible step change around {bp['year']} (Pettitt p = {bp['p']:.2g}) may reflect "
                             "a product or observing-system change."),
                    "numbers": bp, "source": f"{var}.summary.json"})
    return out


def portfolio_sentences(p: dict, region_name: str) -> list[dict]:
    out = []
    names = {"solar": "solar", "wind": "wind", "hydro": "hydro (runoff)"}
    for key, c in p["regional"]["correlations"].items():
        a, b = key.split("_")
        kind = ("tend to move in opposite directions (complementary)" if c["r"] < -0.1 and c["p"] < 0.05
                else "tend to move together" if c["r"] > 0.1 and c["p"] < 0.05 else "show little co-variation")
        out.append({"id": f"portfolio.{key}", "topic": "portfolio",
                    "text": (f"Across {region_name}, monthly {names[a]} and {names[b]} anomalies {kind} "
                             f"(r = {c['r']:+.2f}, p = {c['p']:.2g}, effective n = {c['n_eff']:.0f})."),
                    "numbers": c, "source": "portfolio.json"})
    jl = p["regional"]["joint_low"]
    out.append({"id": "portfolio.joint_low", "topic": "portfolio",
                "text": (f"At least two of the three resources were unusually low in the same month {jl['frequency']:.1%} of the "
                         f"time, versus {jl['expected_independent']:.1%} expected if they were independent "
                         f"(ratio {jl['ratio']:.2f})."),
                "numbers": {k: jl[k] for k in ("frequency", "expected_independent", "ratio")}, "source": "portfolio.json"})
    return out


def alert_sentences(a: dict) -> list[dict]:
    out = []
    for x in a["alerts"]:
        if x["status"] == "none":
            continue
        where = ", ".join(f"{s['name']} ({s['area_frac_adverse']:.0%})" for s in x["subregions"][:3]) or "scattered cells"
        direction = {"low": "low", "high": "high", "both": "unusual"}[x["adverse"]]
        stale = f" Note: this is {x['latency_days']} days after the data month." if x["latency_days"] > 120 else ""
        out.append({"id": f"alert.{x['variable']}", "topic": "alerts",
                    "text": (f"{x['status'].capitalize()} ({a['label']}): {x['variable'].replace('_', ' ')} was {direction} in "
                             f"{x['data_month']}, at the {x['regional']['percentile']:.0f}th percentile of the trend-adjusted "
                             f"same-month baseline. Most affected: {where}.{stale}"),
                    "numbers": {"status": x["status"], "percentile": x["regional"]["percentile"],
                                "data_month": x["data_month"], "latency_days": x["latency_days"]},
                    "source": "alerts.json"})
    return out


# --- build --------------------------------------------------------------------------------------
def build(region: str, out_dir=None, registry: Registry | None = None, loader=None, apply_mask: bool = True) -> dict:
    """Add PNGs, pixel series, narrative and catalog to an export directory that already holds the
    pipeline outputs (run_all.json + per-variable files; portfolio/alerts/validation optional)."""
    reg = registry or Registry.load()
    loader = loader or sources.load
    rdef = reg.regions[region]
    out = Path(out_dir) if out_dir else Path("export") / region
    index = json.loads((out / "run_all.json").read_text())
    region_name = rdef.get("name", region)
    subregions = rdef.get("subregions", {})
    variables, sentences = {}, []

    for res in index["results"]:
        v, season = res["variable"], res["season"]
        vdef = reg.variables[v]
        stem = v + (f".{season}" if season else "")
        summary = json.loads((out / res["files"]["summary"]).read_text())
        with xr.open_dataset(out / res["files"]["trend"]) as d:
            ds = d.load()
        field = "pct_change_per_decade" if "pct_change_per_decade" in ds else "slope_per_decade"
        positive = "blue" if vdef["theme"] in WATER_THEMES else "red"
        legend = render_trend_png(ds, out / f"{stem}.trend.png", field, positive)
        legend["units"] = "% per decade" if field == "pct_change_per_decade" else f"{summary['units']} per decade"
        subs = subregion_stats(ds, subregions, field)
        entry = {"trend_nc": f"{stem}.trend.nc", "trend_png": f"{stem}.trend.png", "summary": f"{stem}.summary.json",
                 "legend": legend, "period": summary["period"], "subregions": subs}
        if season is None:
            da = loader(v, region, reg, f"{summary['period'][:4]}-01", f"{summary['period'][-4:]}-12")
            if apply_mask:
                m = masks.region_mask(rdef, da["lat"].values, da["lon"].values)
                if m is not None:
                    da = da.where(m.values[None])
            ann = preprocess.annualize(da, vdef["aggregation"], min_count=10)
            ann.name = v
            entry["pixel_series"] = write_pixel_series(ann, out / "pixel_series" / v, summary["units"], trend=ds)
            sentences += variable_sentences(v, vdef, summary, subs, region_name)
        card = variables.setdefault(v, {
            "name": v, "long_name": vdef.get("long_name", v), "theme": vdef["theme"], "resource": vdef["resource"],
            "audience": vdef["audience"], "units": vdef["units"], "aggregation": vdef["aggregation"],
            "relative": vdef["relative"], "primary": bool(vdef.get("primary", False)), "adverse": vdef.get("adverse"),
            "provider": summary["provider"], "dataset": summary.get("dataset"), "product_type": summary.get("product_type"),
            "status": vdef["status"], "caveats": vdef.get("caveats", []), "method": summary["method"],
            "annual": None, "seasons": {}})
        if season is None:
            card["annual"] = entry
        else:
            card["seasons"][season] = entry

    extra = {}
    for key, fname in (("portfolio", "portfolio.json"), ("alerts", "alerts.json"), ("validation", "validation.json")):
        if (out / fname).exists():
            extra[key] = fname
    portfolio_maps, alert_maps = {}, {}
    if "portfolio" in extra:
        sentences += portfolio_sentences(json.loads((out / "portfolio.json").read_text()), region_name)
        if (out / "portfolio.nc").exists():
            with xr.open_dataset(out / "portfolio.nc") as d:
                pm = d.load()
            for name in [n for n in pm.data_vars if n.startswith("r_")]:
                leg = render_png(pm[name].values, pm["p_" + name[2:]].values < 0.05, pm["lat"].values, pm["lon"].values,
                                 out / f"portfolio.{name}.png", name, "red")
                leg.update(units="correlation r", note="blue = complementary (opposite anomalies), red = move together; "
                                                       "faded = not significant (p >= 0.05, effective n)")
                portfolio_maps[name] = {"png": f"portfolio.{name}.png", "legend": leg}
            leg = render_png(pm["joint_low_ratio"].values - 1.0, np.isfinite(pm["joint_low_ratio"].values), pm["lat"].values,
                             pm["lon"].values, out / "portfolio.joint_low_ratio.png", "joint_low_ratio - 1", "red")
            leg.update(units="joint-low ratio minus 1", note="red = joint lows more frequent than if independent, blue = less")
            portfolio_maps["joint_low_ratio"] = {"png": "portfolio.joint_low_ratio.png", "legend": leg}
    if "alerts" in extra:
        alerts_doc = json.loads((out / "alerts.json").read_text())
        sentences += alert_sentences(alerts_doc)
        for a in alerts_doc["alerts"]:
            f = out / a.get("file", "")
            if not a.get("file") or not f.exists():
                continue
            with xr.open_dataset(f) as d:
                am = d.load()
            pct = am["percentile"].values
            positive = "blue" if reg.variables[a["variable"]]["theme"] in WATER_THEMES else "red"
            leg = render_png(pct - 50.0, (pct <= 10) | (pct >= 90), am["lat"].values, am["lon"].values,
                             out / f"{a['variable']}.alert.png", "percentile - 50", positive, vmax=50.0)
            leg.update(units="trend-adjusted percentile minus 50",
                       note="opaque = outside the 10th-90th percentile band; faded = within it")
            alert_maps[a["variable"]] = {"png": f"{a['variable']}.alert.png", "legend": leg, "data_month": a["data_month"]}

    narrative = {"region": region, "contract_version": CONTRACT_VERSION,
                 "note": "Every sentence is generated from the numbers in its `numbers` field and `source` file; no other claims.",
                 "sentences": sentences}
    _write_json(out / "narrative.json", narrative)

    catalog = {
        "contract_version": CONTRACT_VERSION,
        "region": {"id": region, "name": region_name, "bbox": rdef["bbox"], "mask": rdef.get("mask"),
                   "analysis_deg": rdef.get("analysis_deg"), "subregions": subregions},
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "period": index["period"],
        "method": ("Per-pixel Theil-Sen slope + Mann-Kendall test (tie-corrected, lag-1 autocorrelation variance "
                   "inflation), Benjamini-Hochberg FDR alpha 0.10; cos(latitude) area weighting."),
        "disclaimers": ["Trend detection and anomaly alerts only; no forecasts.",
                        "Reanalysis and model products are labelled as such; they are not site measurements.",
                        "Resource proxies, not generation."],
        "variables": list(variables.values()),
        "portfolio_maps": portfolio_maps,
        "alert_maps": alert_maps,
        "files": {"run_all": "run_all.json", "narrative": "narrative.json", **extra},
    }
    _write_json(out / "catalog.json", catalog)
    write_index(out.parent, reg)
    problems = validate_export(out)
    if problems:
        raise ValueError("export failed validation:\n" + "\n".join(problems[:20]))
    return catalog


def write_index(root: Path, reg: Registry) -> dict:
    """export/index.json: every configured region, its bbox and whether an export exists (globe page)."""
    idx = {"contract_version": CONTRACT_VERSION, "regions": []}
    for rid, r in reg.regions.items():
        cat = root / rid / "catalog.json"
        entry = {"id": rid, "name": r.get("name", rid), "bbox": r["bbox"], "available": cat.exists()}
        if cat.exists():
            c = json.loads(cat.read_text())
            entry.update(period=c["period"], n_variables=len(c["variables"]))
        idx["regions"].append(entry)
    _write_json(root / "index.json", idx)
    return idx


# --- schemas + validation -----------------------------------------------------------------------
NUM = {"type": ["number", "null"]}
STR = {"type": "string"}
LEGEND = {"type": "object", "required": ["field", "vmin", "vmax", "colors_neg_to_pos", "positive_color", "bounds", "width",
                                         "height", "units"],
          "properties": {"bounds": {"type": "object", "required": ["south", "north", "west", "east"]},
                         "colors_neg_to_pos": {"type": "array", "items": {"type": "string", "pattern": "^#[0-9a-f]{6}$"}}}}
ENTRY = {"type": "object", "required": ["trend_nc", "trend_png", "summary", "legend", "period"],
         "properties": {"legend": LEGEND, "period": {"type": "string", "pattern": r"^\d{4}-\d{4}$"}}}
SCHEMAS = {
    "catalog": {"type": "object", "required": ["contract_version", "region", "period", "method", "disclaimers", "variables", "files"],
                "properties": {"variables": {"type": "array", "minItems": 1, "items": {
                    "type": "object",
                    "required": ["name", "theme", "resource", "audience", "units", "provider", "status", "caveats", "annual"],
                    "properties": {"theme": {"enum": ["hydrology", "cryosphere", "atmospheric_dynamics", "atmospheric_chemistry"]},
                                   "resource": {"enum": ["solar", "wind", "hydro", "none"]},
                                   "status": {"enum": ["verified", "unverified"]},
                                   "annual": ENTRY,
                                   "seasons": {"type": "object", "additionalProperties": ENTRY}}}}}},
    "summary": {"type": "object",
                "required": ["variable", "region", "provider", "units", "period", "method", "area_frac_sig_up",
                             "area_frac_sig_down", "opposing_trend_score", "coverage_score", "regional", "breakpoint",
                             "sensitivity", "caveats", "notes"],
                "properties": {"regional": {"type": "object", "required": ["slope_per_decade", "p_value", "series"],
                                            "properties": {"slope_per_decade": NUM, "p_value": NUM}},
                               "area_frac_sig_up": {"type": "number", "minimum": 0, "maximum": 1},
                               "area_frac_sig_down": {"type": "number", "minimum": 0, "maximum": 1},
                               "coverage_score": {"type": "number", "minimum": 0, "maximum": 1}}},
    "portfolio": {"type": "object", "required": ["region", "resources", "regional", "trend_cards", "method", "caveats"],
                  "properties": {"regional": {"type": "object", "required": ["correlations", "joint_low", "period"]}}},
    "alerts": {"type": "object", "required": ["region", "label", "alerts"],
               "properties": {"label": {"const": "anomaly, not forecast"},
                              "alerts": {"type": "array", "items": {
                                  "type": "object",
                                  "required": ["variable", "label", "data_month", "latency_days", "status", "regional", "baseline"],
                                  "properties": {"label": {"const": "anomaly, not forecast"},
                                                 "status": {"enum": ["strong alert", "alert", "local alert", "none"]}}}}}},
    "narrative": {"type": "object", "required": ["region", "sentences"],
                  "properties": {"sentences": {"type": "array", "items": {
                      "type": "object", "required": ["id", "topic", "text", "numbers", "source"]}}}},
    "pixel_tile": {"type": "object", "required": ["variable", "units", "years", "tile", "cells"],
                   "properties": {"cells": {"type": "array", "items": {
                       "type": "object", "required": ["lat", "lon", "values"],
                       "properties": {"values": {"type": "array", "items": NUM}}}}}},
}


def validate_export(out_dir) -> list[str]:
    """Return a list of problems (empty = valid): every JSON file against its schema, every referenced
    file exists, PNG size matches the trend grid, pixel-series lengths match their years."""
    import jsonschema
    from PIL import Image
    out = Path(out_dir)
    problems = []

    def check(obj, schema, name):
        for e in jsonschema.Draft202012Validator(SCHEMAS[schema]).iter_errors(obj):
            problems.append(f"{name}: {e.message} at {list(e.path)}")

    cat = json.loads((out / "catalog.json").read_text())
    check(cat, "catalog", "catalog.json")
    for key, fname in cat.get("files", {}).items():
        if not (out / fname).exists():
            problems.append(f"catalog file missing: {fname}")
        elif key in ("portfolio", "alerts", "narrative"):
            check(json.loads((out / fname).read_text()), key, fname)
    for var in cat.get("variables", []):
        entries = ([var["annual"]] if var.get("annual") else []) + list(var.get("seasons", {}).values())
        for e in entries:
            for k in ("trend_nc", "trend_png", "summary"):
                if not (out / e[k]).exists():
                    problems.append(f"{var['name']}: missing {e[k]}")
            if (out / e["summary"]).exists():
                check(json.loads((out / e["summary"]).read_text()), "summary", e["summary"])
            if (out / e["trend_png"]).exists() and (out / e["trend_nc"]).exists():
                with Image.open(out / e["trend_png"]) as im, xr.open_dataset(out / e["trend_nc"]) as d:
                    if im.size != (d.sizes["lon"], d.sizes["lat"]) or im.mode != "RGBA":
                        problems.append(f"{e['trend_png']}: size {im.size}/{im.mode} != grid {(d.sizes['lon'], d.sizes['lat'])}")
            b = e["legend"]["bounds"]
            if not (b["south"] < b["north"] and b["west"] < b["east"]):
                problems.append(f"{e['trend_png']}: bad bounds {b}")
        ps = (var.get("annual") or {}).get("pixel_series")
        if ps and not var["annual"]["pixel_series"].get("tiles"):
            problems.append(f"{var['name']}: pixel_series has no tiles")
        if ps:
            for t in ps["tiles"]:
                p = out / "pixel_series" / ps["dir"] / t
                if not p.exists():
                    problems.append(f"missing tile {p}")
                    continue
                tile = json.loads(p.read_text())
                check(tile, "pixel_tile", str(p.relative_to(out)))
                n = len(tile["years"])
                if any(len(c["values"]) != n for c in tile["cells"]):
                    problems.append(f"{p.name}: series length != years")
    for group in ("portfolio_maps", "alert_maps"):
        for name, m in cat.get(group, {}).items():
            if not (out / m["png"]).exists():
                problems.append(f"{group}.{name}: missing {m['png']}")
                continue
            with Image.open(out / m["png"]) as im:
                if im.size != (m["legend"]["width"], m["legend"]["height"]) or im.mode != "RGBA":
                    problems.append(f"{m['png']}: size/mode does not match legend")
    return problems
