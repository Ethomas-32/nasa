"""Compare gridded products with station observations (NOAA).

Sources (verified 2026-11-15, see docs/sources.md):
- NCEI Access Data Service v1 (no key): dataset `global-summary-of-the-month`, TAVG (degC), PRCP (mm).
- USCRN monthly01 files (no key): SOLRAD_MONTHLY_AVG (MJ m-2 day-1 -> W m-2), T_MONTHLY_AVG, P_MONTHLY_CALC.
The older CDO v2 API needs a token (https://www.ncdc.noaa.gov/cdo-web/token) and is not used.

Caveat: nClimGrid is interpolated from station networks that include these GSOM stations, so the
precipitation comparison is a consistency check, not independent validation.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import alerts, preprocess, sources, stats
from .portfolio import monthly_anomalies
from .registry import Registry

ADS = "https://www.ncei.noaa.gov/access/services/data/v1"
USCRN = "https://www.ncei.noaa.gov/pub/data/uscrn/products/monthly01/"
MJ_PER_DAY_TO_WM2 = 1e6 / 86400.0

GSOM_STATIONS = ["USW00023183", "USW00094846", "USW00024233", "USW00013874", "USW00024127", "USW00094728",
                 "USW00013985", "USW00014922", "USW00023174", "USW00003927", "USW00024155", "USW00013722"]
USCRN_STATES = ["AZ", "CA", "CO", "GA", "ME", "MN", "NE", "NM", "OK", "OR", "PA", "TX", "WA", "ND", "SC", "TN", "MT", "NV"]


# --- parsing ------------------------------------------------------------------------------------
def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def parse_gsom(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame({
        "station": [r["STATION"] for r in rows],
        "name": [r.get("NAME") for r in rows],
        "lat": [_num(r.get("LATITUDE")) for r in rows],
        "lon": [_num(r.get("LONGITUDE")) for r in rows],
        "date": pd.to_datetime([r["DATE"] + "-01" for r in rows]),
        "tavg": [_num(r.get("TAVG")) for r in rows],
        "prcp": [_num(r.get("PRCP")) for r in rows],
    })
    return df


def parse_uscrn(text: str, station: str) -> pd.DataFrame:
    rec = []
    for line in text.splitlines():
        f = line.split()
        if len(f) < 11:
            continue
        val = lambda i: np.nan if float(f[i]) <= -9999 else float(f[i])
        rec.append({"station": station, "name": station, "date": pd.to_datetime(f[1] + "01", format="%Y%m%d"),
                    "lon": float(f[3]), "lat": float(f[4]), "tavg": val(8), "prcp": val(9),
                    "solar": val(10) * MJ_PER_DAY_TO_WM2})
    return pd.DataFrame(rec)


# --- fetching (cached) --------------------------------------------------------------------------
def fetch_gsom(stations=GSOM_STATIONS, start="1981-01-01", end="2026-12-31", cache_dir=None) -> pd.DataFrame:
    import requests
    cache = Path(cache_dir or sources._common.DEFAULT_CACHE) / "validation_gsom.csv"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["date"])
    r = requests.get(ADS, params=dict(dataset="global-summary-of-the-month", stations=",".join(stations),
                                      startDate=start, endDate=end, dataTypes="TAVG,PRCP", format="json", units="metric",
                                      includeStationName="true", includeStationLocation="1"), timeout=300)
    r.raise_for_status()
    df = parse_gsom(r.json())
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def fetch_uscrn(states=USCRN_STATES, cache_dir=None) -> pd.DataFrame:
    """First USCRN station (alphabetical) per state in `states`."""
    import re
    import requests
    cache = Path(cache_dir or sources._common.DEFAULT_CACHE) / "validation_uscrn.csv"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["date"])
    listing = requests.get(USCRN, timeout=120).text
    files = sorted(set(re.findall(r'href="(CRNM0102-[^"]+\.txt)"', listing)))
    frames = []
    for st in states:
        f = next((x for x in files if x.startswith(f"CRNM0102-{st}_")), None)
        if f is None:
            continue
        txt = requests.get(USCRN + f, timeout=120).text
        frames.append(parse_uscrn(txt, f.removeprefix("CRNM0102-").removesuffix(".txt")))
    df = pd.concat(frames, ignore_index=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


# --- comparison ---------------------------------------------------------------------------------
def cell_series(da: xr.DataArray, lat: float, lon: float):
    """Series of the nearest grid cell that has data (coastal stations may sit in a masked/ocean cell)."""
    la, lo = da["lat"].values, da["lon"].values
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    d = np.hypot(LA - lat, (LO - lon) * np.cos(np.deg2rad(lat)))
    has = np.isfinite(da.values).any(axis=0)
    d = np.where(has, d, np.inf)
    i, j = np.unravel_index(np.argmin(d), d.shape)
    s = da.isel(lat=i, lon=j).to_series()
    return s, {"cell_lat": float(la[i]), "cell_lon": float(lo[j]), "distance_deg": float(d[i, j])}


def _annual_trend(s: pd.Series):
    da = xr.DataArray(s.values[:, None, None], dims=("time", "lat", "lon"),
                      coords={"time": s.index.values, "lat": [0.0], "lon": [0.0]})
    ann = preprocess.annualize(da, "mean", min_count=10)
    y = ann.values[:, 0, 0]
    r = stats.trend(y[:, None], ann["year"].values.astype(float), min_count=10)
    return float(r["slope"][0] * 10), float(r["p"][0])


def compare(obs: pd.Series, model: pd.Series, relative: bool = False) -> dict:
    """Metrics over months where both exist: bias, RMSE, r, r of deseasonalized+detrended anomalies,
    and the difference of annual-mean Theil-Sen trends (model minus obs) over the same months."""
    df = pd.concat({"o": obs, "m": model}, axis=1).dropna()
    full = pd.date_range(df.index.min(), df.index.max(), freq="MS")
    df = df.reindex(full)
    ok = df.notna().all(axis=1)
    o, m = df["o"].where(ok), df["m"].where(ok)
    diff = (m - o).dropna()
    months = full.month.values
    ao = monthly_anomalies(o.values[:, None], months)[:, 0]
    am = monthly_anomalies(m.values[:, None], months)[:, 0]
    v = np.isfinite(ao) & np.isfinite(am)
    t_o, p_o = _annual_trend(o)
    t_m, p_m = _annual_trend(m)
    out = {
        "period": f"{full[0]:%Y-%m}..{full[-1]:%Y-%m}",
        "n_months": int(ok.sum()),
        "bias": float(diff.mean()),
        "rmse": float(np.sqrt((diff ** 2).mean())),
        "r": float(np.corrcoef(o[ok], m[ok])[0, 1]) if ok.sum() > 2 else np.nan,
        "r_anom": float(np.corrcoef(ao[v], am[v])[0, 1]) if v.sum() > 2 else np.nan,
        "trend_obs_per_decade": t_o, "trend_obs_p": p_o,
        "trend_model_per_decade": t_m, "trend_model_p": p_m,
        "trend_diff_per_decade": (t_m - t_o) if np.isfinite(t_m) and np.isfinite(t_o) else np.nan,
    }
    if relative:
        out["bias_pct"] = float(100 * diff.mean() / o[ok].mean())
    return out


def _alert_check(obs: pd.Series, month: str) -> dict:
    s = obs[obs.index <= pd.Timestamp(month + "-01")]
    if s.empty or pd.Timestamp(month + "-01") not in s.index or np.isnan(s.loc[pd.Timestamp(month + "-01")]):
        return {"month": month, "percentile": None}
    da = xr.DataArray(s.values[:, None, None], dims=("time", "lat", "lon"),
                      coords={"time": s.index.values, "lat": [0.0], "lon": [0.0]})
    r = alerts.pixel_percentiles(da)
    f = lambda x: None if np.isnan(x) else round(float(x), 1)
    return {"month": month, "percentile": f(r["percentile"].ravel()[0]), "percentile_raw": f(r["percentile_raw"].ravel()[0])}


def run(region: str = "conus", registry: Registry | None = None, out_dir=None, start="1981-01", end="2026-12",
        alert_months: dict | None = None) -> dict:
    """Validation table for temperature (GSOM), precipitation (GSOM; not independent of nClimGrid)
    and solar (USCRN), plus station percentiles for the months that raised gridded alerts."""
    reg = registry or Registry.load()
    alert_months = alert_months or {"air_temp_2m": "2026-09", "precipitation": "2022-09"}
    gsom, crn = fetch_gsom(), fetch_uscrn()
    rows = []
    plan = [("air_temp_2m", "tavg", gsom, False, "GSOM first-order station"),
            ("precipitation", "prcp", gsom, True, "GSOM first-order station (NOT independent of nClimGrid)"),
            ("solar_irradiance", "solar", crn, True, "USCRN reference station (independent)")]
    for var, col, obs_df, rel, obs_label in plan:
        da = sources.load(var, region, reg, start, end)
        for st, g in obs_df.groupby("station"):
            g = g.sort_values("date")
            obs = pd.Series(g[col].values, index=pd.DatetimeIndex(g["date"])).astype(float)
            if obs.notna().sum() < 60:
                continue
            mod, info = cell_series(da, float(g["lat"].iloc[0]), float(g["lon"].iloc[0]))
            row = {"variable": var, "provider": da.attrs.get("provider"), "observation": obs_label, "station": st,
                   "name": g["name"].iloc[0], "lat": float(g["lat"].iloc[0]), "lon": float(g["lon"].iloc[0]), **info,
                   **compare(obs, mod, relative=rel)}
            if var in alert_months:
                row["alert_check"] = _alert_check(obs, alert_months[var])
            rows.append(row)
    clean = lambda x: None if isinstance(x, float) and np.isnan(x) else x
    rows = [{k: clean(v) for k, v in r.items()} for r in rows]
    result = {"region": region, "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
              "metrics": "bias/rmse in variable units (model minus obs); r on monthly values; r_anom on "
                         "deseasonalized+detrended monthly anomalies; trends = Theil-Sen on annual means, per decade, "
                         "over the months both have",
              "rows": rows}
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "validation.json").write_text(json.dumps(result, indent=2, default=str))
        pd.DataFrame([{k: v for k, v in r.items() if k != "alert_check"} for r in rows]).to_csv(out / "validation.csv", index=False)
    return result
