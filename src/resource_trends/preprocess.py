"""Temporal aggregation (annual / seasonal), quality filtering and area weighting."""
from __future__ import annotations

import math

import numpy as np
import xarray as xr

SEASONS = {
    "DJF": (12, 1, 2),
    "MAM": (3, 4, 5),
    "JJA": (6, 7, 8),
    "SON": (9, 10, 11),
}
_HOWS = ("sum", "mean", "max")


def _default_min_count(n_months: int) -> int:
    return math.ceil(0.8 * n_months - 1e-9)  # same 80% valid rule as the statistics engine


def _aggregate(da: xr.DataArray, group: xr.DataArray, how: str, min_count: int) -> xr.DataArray:
    if how not in _HOWS:
        raise ValueError(f"how must be one of {_HOWS}, got {how!r}")
    g = da.groupby(group)
    count = da.notnull().groupby(group).sum()
    out = getattr(g, how)(skipna=True)
    out = out.where(count >= min_count)
    out = out.rename({group.name: "year"}) if group.name != "year" else out
    out.attrs = dict(da.attrs)
    out.name = da.name
    return out


def annualize(da: xr.DataArray, how: str, min_count: int = 10) -> xr.DataArray:
    """Monthly -> calendar-year values. A year is NaN if fewer than `min_count` months are valid.

    Note for how="sum": a year with a few missing months is biased low; keep min_count high.
    """
    return _aggregate(da, da["time"].dt.year.rename("year"), how, min_count)


def seasonalize(da: xr.DataArray, season: str, how: str, min_count: int | None = None) -> xr.DataArray:
    """Monthly -> one value per year for a 3-month season (DJF/MAM/JJA/SON).

    DJF is labelled by the year of its January/February (Dec 2000 + Jan/Feb 2001 -> 2001).
    Default min_count is 80% of the season's months (i.e. all 3).
    """
    months = SEASONS[season]
    if min_count is None:
        min_count = _default_min_count(len(months))
    sel = da.sel(time=da["time"].dt.month.isin(months))
    year = sel["time"].dt.year
    if 12 in months and 1 in months:
        year = year + (sel["time"].dt.month == 12)
    return _aggregate(sel, year.rename("year"), how, min_count)


def area_weights(lat, lon, valid=None) -> np.ndarray:
    """cos(latitude) weights shaped (lat, lon); zero where `valid` is False (e.g. data is NaN)."""
    lat = np.asarray(lat, dtype=float)
    w = np.cos(np.deg2rad(lat))[:, None] * np.ones(len(np.asarray(lon)))[None, :]
    if valid is not None:
        w = np.where(np.asarray(valid, bool), w, 0.0)
    return w


def area_weighted_mean(da: xr.DataArray) -> xr.DataArray:
    """cos(lat)-weighted mean over (lat, lon) per remaining coordinate; NaN cells get zero weight.

    Result is NaN where no cell is valid.
    """
    w = xr.DataArray(
        np.cos(np.deg2rad(da["lat"].values))[:, None] * np.ones(da.sizes["lon"])[None, :],
        dims=("lat", "lon"),
        coords={"lat": da["lat"], "lon": da["lon"]},
    )
    w = w.where(da.notnull(), 0.0)  # broadcasts to da's shape; zero weight where data is NaN
    num = (da.fillna(0.0) * w).sum(("lat", "lon"))
    den = w.sum(("lat", "lon"))
    return (num / den.where(den > 0)).rename(da.name)
