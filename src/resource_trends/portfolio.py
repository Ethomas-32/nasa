"""Cross-resource (portfolio) analysis: do solar, wind and hydro resources cover for each other?

- Correlation of DETRENDED, DESEASONALIZED monthly anomalies, per grid cell and for the regional
  series, with a significance test that uses an effective sample size (Bretherton et al. 1999),
  because monthly anomalies are autocorrelated and a naive test overstates significance.
- Joint-low frequency: share of months in which >= k resources are below their own 20th percentile
  FOR THAT CALENDAR MONTH (a normally calm summer is not a "low"), compared with the rate expected
  if the resources were independent.
All numpy functions take (n_time, n_pixels) arrays with NaN for missing.
"""
from __future__ import annotations

import itertools
import json
import warnings
from pathlib import Path

import numpy as np
import xarray as xr
from scipy import stats as sps

from . import masks, preprocess, sources, stats
from .registry import Registry

Q_LOW = 0.2
K_JOINT = 2


def _quiet():
    w = warnings.catch_warnings()
    w.__enter__()
    warnings.simplefilter("ignore", RuntimeWarning)
    return w


# --- anomalies ----------------------------------------------------------------------------------
def monthly_anomalies(x, months) -> np.ndarray:
    """Remove each calendar month's mean, then a linear (OLS) trend in time. NaN-aware."""
    x = np.asarray(x, dtype=float)
    months = np.asarray(months)
    w = _quiet()
    try:
        clim = np.stack([np.nanmean(x[months == m], axis=0) for m in range(1, 13)])
        a = x - clim[months - 1]
        t = np.arange(x.shape[0], dtype=float)[:, None]
        v = np.isfinite(a)
        n = v.sum(axis=0)
        tm = np.where(n > 0, (t * v).sum(axis=0) / np.maximum(n, 1), np.nan)
        am = np.nanmean(a, axis=0)
        dt = np.where(v, t - tm, 0.0)
        den = (dt * dt).sum(axis=0)
        slope = np.where(den > 0, (dt * np.where(v, a - am, 0.0)).sum(axis=0) / np.where(den > 0, den, 1), 0.0)
        return a - (am + slope * (t - tm))
    finally:
        w.__exit__(None, None, None)


# --- correlation --------------------------------------------------------------------------------
def correlation(a, b) -> dict:
    """Pearson r over months where both are valid, with p-values from a t-test using the naive n and
    the effective n_eff = n (1 - r1a r1b) / (1 + r1a r1b) (lag-1 autocorrelations of each series)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    v = np.isfinite(a) & np.isfinite(b)
    A, B = np.where(v, a, np.nan), np.where(v, b, np.nan)
    w = _quiet()
    try:
        n = v.sum(axis=0).astype(float)
        ac = A - np.nanmean(A, axis=0)
        bc = B - np.nanmean(B, axis=0)
        num = np.nansum(ac * bc, axis=0)
        den = np.sqrt(np.nansum(ac * ac, axis=0) * np.nansum(bc * bc, axis=0))
        r = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
        r = np.where(n >= 3, r, np.nan)
        r1 = stats.lag1_autocorr(A) * stats.lag1_autocorr(B)
        n_eff = np.clip(n * (1 - r1) / (1 + r1), 3, n)

        def p_of(nn):
            df = np.maximum(nn - 2, 1)
            tt = r * np.sqrt(df / np.maximum(1 - r * r, 1e-12))
            return 2 * sps.t.sf(np.abs(tt), df)

        return {"r": r, "p": p_of(n_eff), "p_naive": p_of(n), "n": n, "n_eff": n_eff}
    finally:
        w.__exit__(None, None, None)


# --- joint lows ---------------------------------------------------------------------------------
def low_flags(an, months, q: float = Q_LOW) -> np.ndarray:
    """1.0 where the anomaly is below the q-quantile of its calendar month, 0.0 otherwise, NaN if missing."""
    an = np.asarray(an, dtype=float)
    months = np.asarray(months)
    w = _quiet()
    try:
        thr = np.stack([np.nanquantile(an[months == m], q, axis=0) for m in range(1, 13)])
    finally:
        w.__exit__(None, None, None)
    out = (an < thr[months - 1]).astype(float)
    return np.where(np.isfinite(an), out, np.nan)


def prob_at_least_k(ps, k: int):
    """P(at least k of the independent events with probabilities ps occur) (Poisson-binomial)."""
    ps = [np.asarray(p, dtype=float) for p in ps]
    shape = np.broadcast(*ps).shape
    dist = [np.ones(shape)] + [np.zeros(shape) for _ in ps]
    for p in ps:
        new = [d * (1 - p) for d in dist]
        for j in range(1, len(dist)):
            new[j] = new[j] + dist[j - 1] * p
        dist = new
    out = sum(dist[k:])
    return float(out) if out.ndim == 0 else out


def joint_low(anoms: list, months, q: float = Q_LOW, k: int = K_JOINT) -> dict:
    """Frequency of months with >= k resources low, over months where ALL resources are valid,
    plus the expectation under independence (from each resource's own low rate) and their ratio."""
    flags = [low_flags(a, months, q) for a in anoms]
    valid = np.all([np.isfinite(f) for f in flags], axis=0)
    count = np.sum([np.nan_to_num(f) for f in flags], axis=0)
    joint = np.where(valid, (count >= k).astype(float), np.nan)
    w = _quiet()
    try:
        freq = np.nanmean(joint, axis=0)
        rates = [np.nanmean(np.where(valid, f, np.nan), axis=0) for f in flags]
    finally:
        w.__exit__(None, None, None)
    expected = prob_at_least_k(rates, k)
    ratio = np.where(np.asarray(expected) > 0, freq / np.where(np.asarray(expected) > 0, expected, 1), np.nan)
    return {"frequency": freq, "expected_independent": expected, "ratio": ratio, "joint": joint, "flags": flags}


# --- regridding ---------------------------------------------------------------------------------
def regrid_mean(da: xr.DataArray, lat, lon) -> xr.DataArray:
    """Average (NaN-aware, unweighted) every fine cell into the target cell containing its centre."""
    from scipy import sparse
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    iy = np.digitize(da["lat"].values, masks._edges(lat)) - 1
    ix = np.digitize(da["lon"].values, masks._edges(lon)) - 1
    IY, IX = np.meshgrid(iy, ix, indexing="ij")
    ok = ((IY >= 0) & (IY < lat.size) & (IX >= 0) & (IX < lon.size)).ravel()
    tgt = (IY * lon.size + IX).ravel()
    nf = tgt.size
    W = sparse.csr_matrix((np.ones(ok.sum()), (np.arange(nf)[ok], tgt[ok])), shape=(nf, lat.size * lon.size))
    V = da.transpose("time", "lat", "lon").values.reshape(da.sizes["time"], nf)
    valid = np.isfinite(V)
    sums = np.asarray((sparse.csr_matrix(np.where(valid, V, 0.0)) @ W).todense())
    cnt = np.asarray((sparse.csr_matrix(valid.astype(float)) @ W).todense())
    out = np.where(cnt > 0, sums / np.maximum(cnt, 1), np.nan).reshape(-1, lat.size, lon.size)
    res = xr.DataArray(out, dims=("time", "lat", "lon"), coords={"time": da["time"], "lat": lat, "lon": lon}, name=da.name)
    res.attrs = dict(da.attrs)
    return res


# --- analysis -----------------------------------------------------------------------------------
def analyze(resources: dict, q: float = Q_LOW, k: int = K_JOINT):
    """resources: name -> monthly DataArray (time, lat, lon), all on the same grid. Returns
    (maps Dataset, regional dict). Uses the months common to all resources."""
    names = list(resources)
    common = None
    for da in resources.values():
        idx = da.get_index("time")
        common = idx if common is None else common.intersection(idx)
    das = {n: resources[n].sel(time=common) for n in names}
    ref = das[names[0]]
    months = common.month.values
    shape = ref.shape[1:]
    flat = {n: das[n].values.reshape(len(common), -1) for n in names}
    an = {n: monthly_anomalies(flat[n], months) for n in names}

    coords = {"lat": ref["lat"], "lon": ref["lon"]}
    data = {}
    for a, b in itertools.combinations(names, 2):
        c = correlation(an[a], an[b])
        data[f"r_{a}_{b}"] = (("lat", "lon"), c["r"].reshape(shape))
        data[f"p_{a}_{b}"] = (("lat", "lon"), c["p"].reshape(shape))
    jl = joint_low([an[n] for n in names], months, q, k)
    data["joint_low_frequency"] = (("lat", "lon"), jl["frequency"].reshape(shape))
    data["joint_low_expected"] = (("lat", "lon"), np.asarray(jl["expected_independent"]).reshape(shape))
    data["joint_low_ratio"] = (("lat", "lon"), jl["ratio"].reshape(shape))
    maps = xr.Dataset(data, coords=coords)
    maps.attrs.update(period=f"{common[0]:%Y-%m}..{common[-1]:%Y-%m}", resources=",".join(names),
                      method=f"Pearson r of detrended, deseasonalized monthly anomalies; p from t-test with effective "
                             f"n (Bretherton 1999). Low = below calendar-month {int(q * 100)}th percentile of anomalies; "
                             f"joint low = >= {k} resources low in the same month.")

    # regional series: cos-lat area-weighted mean of each resource over valid cells
    reg_series = {n: preprocess.area_weighted_mean(das[n]).values[:, None] for n in names}
    ran = {n: monthly_anomalies(reg_series[n], months) for n in names}
    corr = {}
    for a, b in itertools.combinations(names, 2):
        c = correlation(ran[a], ran[b])
        corr[f"{a}_{b}"] = {"r": float(c["r"][0]), "p": float(c["p"][0]), "n": int(c["n"][0]),
                            "n_eff": float(c["n_eff"][0]), "p_naive": float(c["p_naive"][0])}
    rjl = joint_low([ran[n] for n in names], months, q, k)
    joint_months = [{"month": f"{common[i]:%Y-%m}", "low": [n for j, n in enumerate(names) if rjl["flags"][j][i, 0] == 1.0]}
                    for i in range(len(common)) if rjl["joint"][i, 0] == 1.0]
    regional = {
        "period": f"{common[0]:%Y-%m}..{common[-1]:%Y-%m}",
        "n_months": int(len(common)),
        "correlations": corr,
        "joint_low": {
            "definition": f">= {k} of {len(names)} resources below their calendar-month {int(q * 100)}th percentile "
                          "(detrended, deseasonalized anomalies of the area-weighted regional series)",
            "frequency": float(rjl["frequency"][0]),
            "expected_independent": float(np.asarray(rjl["expected_independent"]).ravel()[0]),
            "ratio": float(rjl["ratio"][0]),
            "months": joint_months,
        },
    }
    return maps, regional


def _spacing(da):
    return float(np.abs(np.diff(da["lat"].values)).mean())


def run(region: str, start: str = "1981-01", end: str = "2020-12", registry: Registry | None = None, loader=None,
        out_dir=None, q: float = Q_LOW, k: int = K_JOINT, apply_mask: bool = True):
    """Load each resource's primary index, bring them to the coarsest grid, mask, analyze, and write
    `portfolio.json` + `portfolio.nc` (if out_dir). Trend cards come from existing `<var>.summary.json`."""
    reg = registry or Registry.load()
    loader = loader or sources.load
    prim = {r: reg.primary_index(r) for r in ("solar", "wind", "hydro")}
    raw = {r: loader(v, region, reg, start, end) for r, v in prim.items()}
    target = max(raw.values(), key=_spacing)
    lat, lon = target["lat"].values, target["lon"].values
    grid = {}
    for r, da in raw.items():
        same = da.sizes["lat"] == lat.size and da.sizes["lon"] == lon.size and np.allclose(da["lat"], lat) and np.allclose(da["lon"], lon)
        grid[r] = da if same else regrid_mean(da, lat, lon)
    mask_path = None
    if apply_mask:
        m = masks.region_mask(reg.regions[region], lat, lon)
        if m is not None:
            grid = {r: da.where(m.values[None]) for r, da in grid.items()}
            mask_path = reg.regions[region]["mask"]
    maps, regional = analyze(grid, q, k)

    cards = {}
    for r, v in prim.items():
        card = {"variable": v, "provider": raw[r].attrs.get("provider"), "units": raw[r].attrs.get("units"),
                "caveats": reg.variables[v].get("caveats", [])}
        if out_dir and (Path(out_dir) / f"{v}.summary.json").exists():
            s = json.loads((Path(out_dir) / f"{v}.summary.json").read_text())
            card.update(period=s["period"], regional_trend=s["regional"], area_frac_sig_up=s["area_frac_sig_up"],
                        area_frac_sig_down=s["area_frac_sig_down"])
        cards[r] = card
    result = {
        "region": region,
        "resources": prim,
        "grid": f"{_spacing(target):.3g} deg (coarsest input; finer inputs area-averaged onto it)",
        "mask": mask_path,
        "method": maps.attrs["method"],
        "regional": regional,
        "trend_cards": cards,
        "caveats": ["Resource proxies, not generation: solar and wind are reanalysis, runoff is a water-balance model "
                    "(dams and operations are not modeled).",
                    "Correlations describe co-variability of monthly anomalies, not causation or forecasts."],
    }
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        maps.to_netcdf(out / "portfolio.nc")
        (out / "portfolio.json").write_text(json.dumps(result, indent=2))
    return maps, result
