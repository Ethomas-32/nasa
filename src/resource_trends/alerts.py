"""Anomaly alerts: is the LATEST available month unusual against a trend-adjusted baseline?

Baseline = the same calendar month in the previous `baseline_years` years (>= `min_years` valid),
detrended with Theil-Sen, so a long-term trend does not make every month look extreme and seasonality
is handled by comparing like with like. The latest value's residual is ranked among the baseline
residuals (empirical percentile). This is an ANOMALY ALERT, NOT A FORECAST.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import masks, preprocess, sources, stats
from .registry import Registry

LABEL = "anomaly, not forecast"
BASELINE_YEARS = 30
MIN_YEARS = 15
TAILS = {"alert": 10.0, "strong alert": 5.0}


def percentile_of(x, base) -> np.ndarray:
    """Empirical percentile (0-100) of x within each column of base; ties count half. NaN-aware."""
    x = np.asarray(x, dtype=float)
    base = np.asarray(base, dtype=float)
    valid = np.isfinite(base)
    n = valid.sum(axis=0)
    below = np.sum(valid & (base < x), axis=0)
    ties = np.sum(valid & (base == x), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        pct = 100.0 * (below + 0.5 * ties) / n
    return np.where(np.isfinite(x) & (n > 0), pct, np.nan)


def pixel_percentiles(da: xr.DataArray, baseline_years: int = BASELINE_YEARS, min_years: int = MIN_YEARS) -> dict:
    """Per-cell trend-adjusted and raw percentiles of the latest month with any data."""
    da = da.transpose("time", ...)
    shape = da.shape[1:]
    flat = da.values.reshape(da.sizes["time"], -1)
    has = np.isfinite(flat).any(axis=1)
    if not has.any():
        raise ValueError("no data")
    li = int(np.where(has)[0][-1])
    times = pd.DatetimeIndex(da["time"].values)
    latest = times[li]
    same = (times.month == latest.month) & (times.year >= latest.year - baseline_years) & (times.year < latest.year)
    base = flat[same]
    years = times[same].year.values.astype(float)
    v = flat[li]
    n_valid = np.isfinite(base).sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        slope, icept = stats.theil_sen(base, years) if base.shape[0] >= 2 else (np.full(v.shape, np.nan),) * 2
    expected = icept + slope * latest.year
    resid = base - (icept + slope * years[:, None])
    pct = percentile_of(v - expected, resid)
    raw = percentile_of(v, base)
    short = n_valid < min_years
    pct = np.where(short, np.nan, pct)
    raw = np.where(short, np.nan, raw)
    return {
        "percentile": pct.reshape(shape),
        "percentile_raw": raw.reshape(shape),
        "anomaly": np.where(short, np.nan, v - expected).reshape(shape),
        "value": v.reshape(shape),
        "latest": da["time"].values[li],
        "baseline_years": (int(years.min()), int(years.max())) if years.size else (None, None),
        "n_baseline": int(years.size),
    }


def _f(x):
    x = float(x)
    return None if np.isnan(x) else round(x, 4)


def _status(adverse: str, regional_pct: float, adverse_area: float) -> str:
    if regional_pct == regional_pct:
        lo = regional_pct
        hi = 100.0 - regional_pct
        tail = {"low": lo, "high": hi, "both": min(lo, hi)}[adverse]
        if tail <= TAILS["strong alert"]:
            return "strong alert"
        if tail <= TAILS["alert"]:
            return "alert"
    if adverse_area >= 0.2:
        return "local alert"      # regional mean unremarkable, but >= 20% of the area is in the adverse 10% tail
    return "none"


def variable_alert(da: xr.DataArray, variable: str, registry: Registry, region: str,
                   today: pd.Timestamp | None = None, baseline_years: int = BASELINE_YEARS) -> dict:
    vdef = registry.variables[variable]
    adverse = vdef.get("adverse", "both")
    res = pixel_percentiles(da, baseline_years)
    pct = res["percentile"]
    lat = da["lat"].values
    w = np.cos(np.deg2rad(lat))[:, None] * np.ones(da.sizes["lon"])[None, :]
    ok = np.isfinite(pct)
    wv = (w * ok).sum()
    frac = lambda m: float((w * (m & ok)).sum() / wv) if wv else 0.0
    f_lo10, f_lo5 = frac(pct <= 10), frac(pct <= 5)
    f_hi90, f_hi95 = frac(pct >= 90), frac(pct >= 95)
    adverse_area = {"low": f_lo10, "high": f_hi90, "both": max(f_lo10, f_hi90)}[adverse]
    adv_mask = {"low": pct <= 10, "high": pct >= 90, "both": (pct <= 10) | (pct >= 90)}[adverse]

    series = preprocess.area_weighted_mean(da)
    rres = pixel_percentiles(series.expand_dims(lat=[0.0], lon=[0.0]).transpose("time", "lat", "lon"), baseline_years)
    rp = float(rres["percentile"].ravel()[0])

    subs = []
    for name, b in registry.regions.get(region, {}).get("subregions", {}).items():
        sel = (lat[:, None] >= b["lat_min"]) & (lat[:, None] <= b["lat_max"]) & \
              (da["lon"].values[None, :] >= b["lon_min"]) & (da["lon"].values[None, :] <= b["lon_max"]) & ok
        if not sel.any():
            continue
        a = float((w * (adv_mask & sel)).sum() / (w * sel).sum())
        if a > 0:
            subs.append({"name": name, "area_frac_adverse": round(a, 4),
                         "mean_percentile": _f((w * np.where(sel, pct, 0)).sum() / (w * sel).sum())})
    subs.sort(key=lambda s: -s["area_frac_adverse"])

    latest = pd.Timestamp(res["latest"])
    today = today or pd.Timestamp.today().normalize()
    month_end = latest + pd.offsets.MonthEnd(0)
    return {
        "variable": variable,
        "label": LABEL,
        "resource": vdef["resource"],
        "theme": vdef["theme"],
        "provider": da.attrs.get("provider"),
        "units": da.attrs.get("units"),
        "data_month": latest.strftime("%Y-%m"),
        "latency_days": int((today - month_end).days),
        "adverse": adverse,
        "status": _status(adverse, rp, adverse_area),
        "regional": {"percentile": _f(rp), "percentile_raw": _f(rres["percentile_raw"].ravel()[0]),
                     "anomaly": _f(rres["anomaly"].ravel()[0]), "value": _f(rres["value"].ravel()[0])},
        "area_frac_low_10": round(f_lo10, 4), "area_frac_low_5": round(f_lo5, 4),
        "area_frac_high_90": round(f_hi90, 4), "area_frac_high_95": round(f_hi95, 4),
        "subregions": subs,
        "baseline": {
            "definition": (f"same calendar month in the {res['n_baseline']} previous years, Theil-Sen detrended; "
                           "percentile of the latest residual among baseline residuals (ties count half); "
                           f"cells need >= {MIN_YEARS} valid baseline years"),
            "years": list(res["baseline_years"]),
        },
        "caveats": list(vdef.get("caveats", [])),
        "_maps": res,
    }


SEVERITY = {"strong alert": 0, "alert": 1, "local alert": 2, "none": 3}


def run(region: str, registry: Registry | None = None, loader=None, out_dir=None, variables=None,
        today: pd.Timestamp | None = None, start: str = "1981-01", end: str = "2026-12", apply_mask: bool = True) -> dict:
    """Alerts for every variable's latest available month. Writes alerts.json and <var>.alert.nc."""
    reg = registry or Registry.load()
    loader = loader or sources.load
    today = today or pd.Timestamp.today().normalize()
    items, failures = [], []
    for v in variables or list(reg.variables):
        try:
            da = loader(v, region, reg, start, end)
            if apply_mask:
                m = masks.region_mask(reg.regions[region], da["lat"].values, da["lon"].values)
                if m is not None:
                    da = da.where(m.values[None])
            a = variable_alert(da, v, reg, region, today)
        except Exception as e:  # noqa: BLE001 - one variable must not stop the alert run
            failures.append({"variable": v, "error": f"{type(e).__name__}: {e}"})
            continue
        maps = a.pop("_maps")
        if out_dir:
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            xr.Dataset({k: (("lat", "lon"), maps[k]) for k in ("percentile", "percentile_raw", "anomaly", "value")},
                       coords={"lat": da["lat"], "lon": da["lon"]},
                       attrs={"label": LABEL, "variable": v, "data_month": a["data_month"]}).to_netcdf(out / f"{v}.alert.nc")
            a["file"] = f"{v}.alert.nc"
        items.append(a)
    items.sort(key=lambda a: (SEVERITY[a["status"]], a["data_month"]))
    result = {
        "region": region,
        "label": LABEL,
        "generated": today.strftime("%Y-%m-%d"),
        "thresholds": {"alert": "regional percentile in the adverse 10% tail",
                       "strong alert": "regional percentile in the adverse 5% tail",
                       "local alert": ">= 20% of the area in the adverse 10% tail while the regional mean is not"},
        "note": "Each variable uses its own latest available month; hydrology sources lag by years (see data_month).",
        "alerts": items,
        "failures": failures,
    }
    if out_dir:
        (Path(out_dir) / "alerts.json").write_text(json.dumps(result, indent=2))
    return result
