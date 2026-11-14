"""Shared helpers for all loaders: unit conversion, contract finalisation, coarsening, caching.

Loader contract (CLAUDE.md section 5): DataArray named after the variable, dims (time, lat, lon),
ascending lat, lon in [-180, 180], cropped to the region bbox, with `units` and `provider` attrs.
Time values are the first day of each month.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

DEFAULT_CACHE = Path(__file__).resolve().parents[3] / "data" / "cache"

_ALIASES = {
    "c": "degC", "degc": "degC", "degrees c": "degC", "degrees_c": "degC",
    "m/s": "m s-1", "m s-1": "m s-1",
    "unitless": "1", "dimensionless": "1", "1": "1",
    "w m-2": "W m-2", "w/m^2": "W m-2", "w/m2": "W m-2",
    "mm": "mm", "hpa": "hPa", "kpa": "kPa", "pa": "Pa", "kg m-2": "kg m-2",
}
_FACTORS = {("kPa", "hPa"): 10.0, ("hPa", "kPa"): 0.1, ("Pa", "hPa"): 0.01, ("hPa", "Pa"): 100.0,
            ("kg m-2", "mm"): 1.0}  # 1 kg m-2 of water = 1 mm


def norm_units(u: str) -> str:
    return _ALIASES.get(str(u).strip().lower(), str(u).strip())


def convert_units(da: xr.DataArray, native: str, canonical: str) -> xr.DataArray:
    a, b = norm_units(native), norm_units(canonical)
    if a != b:
        if (a, b) not in _FACTORS:
            raise ValueError(f"no conversion from {native!r} to {canonical!r}")
        da = da * _FACTORS[(a, b)]
    da.attrs["units"] = canonical
    return da


def month_index(start: str, end: str) -> pd.DatetimeIndex:
    return pd.period_range(start, end, freq="M").to_timestamp()


def to_month_start(time_values) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(time_values).to_period("M").to_timestamp()


def crop(da: xr.DataArray, bbox: dict) -> xr.DataArray:
    """Sort lat ascending, wrap lon to [-180, 180], crop to bbox (inclusive)."""
    da = da.sortby("lat")
    if float(da["lon"].max()) > 180:
        da = da.assign_coords(lon=((da["lon"] + 180) % 360) - 180)
    da = da.sortby("lon")
    return da.where(
        (da.lat >= bbox["lat_min"]) & (da.lat <= bbox["lat_max"]) &
        (da.lon >= bbox["lon_min"]) & (da.lon <= bbox["lon_max"]), drop=True)


def coarsen_to(da: xr.DataArray, target_deg: float | None) -> xr.DataArray:
    """Block-average (NaN-aware) by an integer factor if the native grid is finer than target_deg."""
    if not target_deg:
        return da
    step = float(min(np.abs(np.diff(da["lat"].values)).mean(), np.abs(np.diff(da["lon"].values)).mean()))
    f = int(round(target_deg / step))
    if f <= 1:
        return da
    out = da.coarsen(lat=f, lon=f, boundary="trim").mean()
    out.attrs = dict(da.attrs)
    return out


def finalize(da: xr.DataArray, name: str, units: str, native_units: str, provider: str,
             bbox: dict, **attrs) -> xr.DataArray:
    """Apply the loader contract. `da` must already have dims time/lat/lon (any order/direction)."""
    da = da.transpose("time", "lat", "lon")
    da = da.assign_coords(time=to_month_start(da["time"].values))
    da = crop(da, bbox)
    da = da.sortby("time")
    da = da.astype("float32")
    da.attrs = {}
    da = convert_units(da, native_units, units)
    da.attrs.update(provider=provider, **attrs)
    da.name = name
    return da


def check_contract(da: xr.DataArray, name: str | None = None, bbox: dict | None = None):
    """Raise AssertionError if `da` violates the loader contract."""
    assert da.dims == ("time", "lat", "lon"), da.dims
    assert np.all(np.diff(da["lat"].values) > 0), "lat must be ascending"
    assert float(da["lon"].min()) >= -180 and float(da["lon"].max()) <= 180, "lon must be in [-180, 180]"
    assert np.all(np.diff(da["lon"].values) > 0), "lon must be ascending"
    assert "units" in da.attrs and "provider" in da.attrs
    assert all(pd.Timestamp(t).day == 1 for t in da["time"].values), "time must be month starts"
    if name:
        assert da.name == name
    if bbox:
        assert float(da.lat.min()) >= bbox["lat_min"] and float(da.lat.max()) <= bbox["lat_max"]
        assert float(da.lon.min()) >= bbox["lon_min"] and float(da.lon.max()) <= bbox["lon_max"]


def cached_series(path: Path, months: pd.DatetimeIndex, fetch_batches) -> xr.DataArray:
    """Incremental cache. `fetch_batches(missing_months)` yields finalized DataArrays; each batch is
    merged and saved immediately so an interrupted run keeps its progress. Months the provider does
    not have simply stay missing (they are not retried within one call).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cached = None
    if path.exists():
        with xr.open_dataarray(path) as d:
            cached = d.load()
    have = pd.DatetimeIndex(cached["time"].values) if cached is not None else pd.DatetimeIndex([])
    missing = months.difference(have)
    if len(missing):
        for batch in fetch_batches(missing):
            cached = batch if cached is None else xr.concat([cached, batch], "time").sortby("time")
            cached = cached.isel(time=~cached.get_index("time").duplicated(keep="last"))
            tmp = path.with_suffix(".tmp")
            cached.to_netcdf(tmp)
            tmp.replace(path)
    if cached is None:
        raise LookupError(f"no data available for {months[0]:%Y-%m}..{months[-1]:%Y-%m}")
    keep = months.intersection(pd.DatetimeIndex(cached["time"].values))
    return cached.sel(time=keep)
