"""Single-variable trend pipeline: load -> annual/seasonal aggregate -> per-pixel trends + FDR ->
regional summary, start-year sensitivity and a breakpoint check. Every output records provider,
period and method (CLAUDE.md section 10)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import xarray as xr

from . import masks, preprocess, sources, stats
from .registry import Registry

DEFAULT_START, DEFAULT_END = 1981, 2020
SHIFT = 5
BREAKPOINT_ALPHA = 0.05


def _f(x):
    """JSON-safe float (NaN -> None)."""
    x = float(x)
    return None if math.isnan(x) else x


def _cos_weights(ds_or_da) -> np.ndarray:
    lat = ds_or_da["lat"].values
    return np.cos(np.deg2rad(lat))[:, None] * np.ones(ds_or_da.sizes["lon"])[None, :]


def _aggregate(da, how, season):
    if season:
        return preprocess.seasonalize(da, season, how)
    return preprocess.annualize(da, how, min_count=10)


def _regional(series_da: xr.DataArray, relative: bool) -> dict:
    years = series_da["year"].values.astype(float)
    y = series_da.values
    r = stats.trend(y[:, None], years)
    slope_dec = r["slope"][0] * 10.0
    mean = float(np.nanmean(y)) if np.isfinite(y).any() else float("nan")
    out = {
        "slope_per_decade": _f(slope_dec),
        "p_value": _f(r["p"][0]),
        "rho1": _f(r["rho1"][0]),
        "mean": _f(mean),
        "series": {str(int(t)): _f(v) for t, v in zip(years, y)},
    }
    if relative and abs(mean) > 1e-12:
        out["pct_change_per_decade"] = _f(100.0 * slope_dec / abs(mean))
    return out


def run(region: str, variable: str, start_year: int = DEFAULT_START, end_year: int = DEFAULT_END,
        season: str | None = None, registry: Registry | None = None, loader=None, out_dir=None,
        alpha_fdr: float = 0.10, shift: int = SHIFT, apply_mask: bool = True):
    """Run the trend analysis for one (region, variable[, season]). Returns (Dataset, summary dict)
    and, if out_dir is given, writes `<var>[.<season>].trend.nc` and `<var>[.<season>].summary.json`."""
    reg = registry or Registry.load()
    loader = loader or sources.load
    vdef = reg.variables[variable]
    how, relative = vdef["aggregation"], vdef["relative"]
    notes: list[str] = []

    lo = start_year - shift
    first_month = f"{lo - 1}-12" if season == "DJF" else f"{lo}-01"     # DJF needs the previous December
    da = loader(variable, region, reg, first_month, f"{end_year}-12")
    mask_path = None
    if apply_mask:
        m = masks.region_mask(reg.regions[region], da["lat"].values, da["lon"].values)
        if m is not None:
            da = da.where(m.values[None, :, :])
            mask_path = reg.regions[region]["mask"]
    if mask_path is None:
        notes.append("no land mask applied: statistics cover the whole bounding box (may include ocean / other countries)")
    agg = _aggregate(da, how, season)
    has = agg["year"].values[np.isfinite(agg.values).reshape(agg.sizes["year"], -1).any(axis=1)]
    if has.size == 0:
        raise ValueError(f"no valid {variable} data for {region}")
    data_start, data_end = int(has.min()), int(has.max())
    if data_start > start_year:
        raise ValueError(f"{variable} data begin {data_start}, after requested start {start_year}")
    if data_end < end_year:
        notes.append(f"data end {data_end}, before requested end {end_year}; period truncated")
        end_year = data_end

    main = agg.sel(year=slice(start_year, end_year))
    ds = stats.trend_map(main, relative=relative, alpha_fdr=alpha_fdr)

    # --- area fractions (cos-lat weighted) ---
    w = _cos_weights(ds)
    valid = np.isfinite(ds["p_value"].values)
    any_data = np.isfinite(main.values).any(axis=0)
    sig = ds["significant"].values
    slope = ds["slope_per_decade"].values
    wv = (w * valid).sum()
    up = float((w * (sig & (slope > 0))).sum() / wv) if wv else 0.0
    down = float((w * (sig & (slope < 0))).sum() / wv) if wv else 0.0
    opposing = 2 * min(up, down) / (up + down) if (up + down) > 0 else 0.0
    coverage = float((w * valid).sum() / (w * any_data).sum()) if any_data.any() else 0.0

    # --- regional series + breakpoint ---
    series = preprocess.area_weighted_mean(main)
    regional = _regional(series, relative)
    # Pettitt on the Sen-DETRENDED regional series: on a raw trending series Pettitt always finds a
    # "change point", so a smooth trend must be removed first; a genuine step still leaves a jump.
    yrs = main["year"].values.astype(float)
    sl, ic = stats.theil_sen(series.values[:, None], yrs)
    resid = series.values - (ic[0] + sl[0] * yrs)
    bp = stats.pettitt(resid)
    bp_year = int(main["year"].values[bp["index"]]) if bp["index"] is not None else None
    breakpoint = {"year": bp_year, "p": _f(bp["p"]),
                  "method": "Pettitt (1979) on the Sen-detrended area-weighted regional series"}
    if bp["p"] == bp["p"] and bp["p"] < BREAKPOINT_ALPHA:
        notes.append(f"Possible breakpoint in the regional series at {bp_year} (Pettitt p={bp['p']:.3g}). "
                     "A step can be a real shift or a product/observing-system change; check before trusting the trend.")

    # --- start-year sensitivity ---
    sensitivity = []
    for s in (start_year - shift, start_year + shift):
        if s < data_start:
            notes.append(f"start-year sensitivity at {s} skipped: data begin {data_start}")
            continue
        if end_year - s + 1 < 10:
            notes.append(f"start-year sensitivity at {s} skipped: fewer than 10 years")
            continue
        alt_main = agg.sel(year=slice(s, end_year))
        alt = stats.trend_map(alt_main, relative=relative, alpha_fdr=alpha_fdr)
        a_slope = alt["slope_per_decade"].values
        both = sig & np.isfinite(a_slope)
        agree = float((np.sign(a_slope[both]) == np.sign(slope[both])).mean()) if both.any() else None
        still = float((alt["significant"].values[sig]).mean()) if sig.any() else None
        sensitivity.append({
            "start_year": s,
            "period": f"{s}-{end_year}",
            "sign_agreement": agree,                 # among pixels significant in the main run
            "still_significant": still,
            "regional_slope_per_decade": _regional(preprocess.area_weighted_mean(alt_main), relative)["slope_per_decade"],
        })

    summary = {
        "variable": variable,
        "region": region,
        "season": season,
        "provider": da.attrs.get("provider"),
        "dataset": da.attrs.get("dataset"),
        "product_type": da.attrs.get("product_type"),
        "units": da.attrs.get("units"),
        "aggregation": how,
        "mask": mask_path,
        "period": f"{start_year}-{end_year}",
        "n_years": int(main.sizes["year"]),
        "method": ds.attrs["method"] + "; per-pixel annual " + (f"{season} " if season else "") + f"{how}",
        "alpha_fdr": alpha_fdr,
        "area_frac_sig_up": up,
        "area_frac_sig_down": down,
        "opposing_trend_score": opposing,
        "coverage_score": coverage,
        "regional": regional,
        "breakpoint": breakpoint,
        "sensitivity": sensitivity,
        "caveats": list(vdef.get("caveats", [])),
        "notes": notes,
    }
    ds.attrs.update(provider=str(summary["provider"]), variable=variable, region=region,
                    period=summary["period"], units_of_slope=f"{summary['units']} per decade",
                    season=season or "annual")

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = variable + (f".{season}" if season else "")
        enc = ds.copy()
        enc["significant"] = enc["significant"].astype("int8")
        enc.to_netcdf(out / f"{stem}.trend.nc")
        (out / f"{stem}.summary.json").write_text(json.dumps(summary, indent=2))
    return ds, summary
