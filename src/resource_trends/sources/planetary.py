"""Microsoft Planetary Computer loaders: TerraClimate (Zarr), Daymet (Zarr, Lambert), NClimGrid (COG)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from . import _common as C

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"


def _catalog():
    import planetary_computer as pc
    import pystac_client
    return pystac_client.Client.open(STAC, modifier=pc.sign_inplace)


def _open_zarr_asset(collection: str) -> xr.Dataset:
    a = _catalog().get_collection(collection).assets["zarr-abfs"]
    kw = dict(a.extra_fields.get("xarray:open_kwargs", {}))
    kw.setdefault("storage_options", a.extra_fields.get("xarray:storage_options"))
    kw.update(engine="zarr", chunks={})
    return xr.open_dataset(a.href, **kw)


def _years(missing: pd.DatetimeIndex):
    for y in sorted(set(missing.year)):
        yield y, missing[missing.year == y]


# --- TerraClimate -------------------------------------------------------------------------------
def standardize_terraclimate(raw: xr.DataArray, name, units, spec, bbox) -> xr.DataArray:
    return C.finalize(raw, name, units, spec["native_units"], "terraclimate", bbox,
                      dataset=spec["dataset"], native_variable=spec["variable"], product_type=spec["product_type"])


def load_terraclimate(name, units, spec, bbox, months, cache_path, target_deg=None, **_):
    def batches(missing):
        ds = _open_zarr_asset("terraclimate")
        v = ds[spec["variable"]].sel(lat=slice(bbox["lat_max"] + 0.1, bbox["lat_min"] - 0.1),   # lat descending
                                     lon=slice(bbox["lon_min"] - 0.1, bbox["lon_max"] + 0.1))
        for y, ms in _years(missing):
            t = v["time"].to_index()
            sub = v.isel(time=np.where(t.isin(ms))[0])
            if sub.sizes["time"] == 0:
                continue
            sub = C.coarsen_to(sub.sortby("lat"), target_deg).compute()   # block-average lazily, then load
            yield standardize_terraclimate(sub, name, units, spec, bbox)
            print(f"  terraclimate {spec['variable']}: cached {y}", flush=True)

    return C.cached_series(cache_path, months, batches)


# --- Daymet (1 km Lambert conformal conic -> lat/lon target grid) --------------------------------
LCC = dict(proj="lcc", lat_1=25, lat_2=60, lat_0=42.5, lon_0=-100, x_0=0, y_0=0, a=6378137, rf=298.257223563)


def standardize_daymet(raw: xr.DataArray, name, units, spec, bbox) -> xr.DataArray:
    """raw is already on a lat/lon grid with monthly TOTALS-of-daily-values converted by the caller.

    Daymet monthly `swe` has cell_methods 'time: sum within days, sum over days', i.e. it is the sum
    of daily SWE over the month. Dividing by days-in-month gives mean SWE (mm); the annual `max` of
    these is the peak monthly-mean SWE (a lower bound of true peak SWE)."""
    days = pd.DatetimeIndex(raw["time"].values).days_in_month.values
    raw = raw / xr.DataArray(days, dims="time", coords={"time": raw["time"]})
    return C.finalize(raw, name, units, spec["native_units"], "daymet", bbox,
                      dataset=spec["dataset"], native_variable=spec["variable"], product_type=spec["product_type"],
                      note="monthly mean of daily SWE (Daymet monthly value is a sum over days / days in month)")


def daymet_to_latlon(block: xr.DataArray, lat: np.ndarray, lon: np.ndarray, f: int) -> xr.DataArray:
    """Block-average (x,y) by f (NaN-aware), then nearest-sample at the target (lat, lon) grid."""
    from pyproj import Transformer
    block = block.drop_vars(["lat", "lon"], errors="ignore")   # Daymet's 2-D auxiliary coords clash with the new dims
    co = block.coarsen(y=f, x=f, boundary="trim").mean()
    tr = Transformer.from_crs("EPSG:4326", " ".join(f"+{k}={v}" for k, v in LCC.items()) + " +units=m +no_defs", always_xy=True)
    LON, LAT = np.meshgrid(lon, lat)
    X, Y = tr.transform(LON, LAT)
    xs, ys = co["x"].values, co["y"].values
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]            # dy is negative (y descending)
    ix = np.rint((X - xs[0]) / dx).astype(int)
    iy = np.rint((Y - ys[0]) / dy).astype(int)
    inside = (ix >= 0) & (ix < xs.size) & (iy >= 0) & (iy < ys.size)   # cells off the grid -> NaN
    idx = lambda a: xr.DataArray(a, dims=("lat", "lon"), coords={"lat": lat, "lon": lon})
    out = co.isel(x=idx(np.clip(ix, 0, xs.size - 1)), y=idx(np.clip(iy, 0, ys.size - 1)))
    out = out.where(idx(inside))
    return out.drop_vars(["x", "y"], errors="ignore")


def load_daymet(name, units, spec, bbox, months, cache_path, target_deg=0.25, **_):
    from pyproj import Transformer
    target_deg = target_deg or 0.25

    def batches(missing):
        ds = _open_zarr_asset("daymet-monthly-na")
        v = ds[spec["variable"]]
        tr = Transformer.from_crs("EPSG:4326", " ".join(f"+{k}={val}" for k, val in LCC.items()) + " +units=m +no_defs", always_xy=True)
        gl = np.linspace(bbox["lon_min"], bbox["lon_max"], 60)
        gt = np.linspace(bbox["lat_min"], bbox["lat_max"], 60)
        X, Y = tr.transform(*np.meshgrid(gl, gt))
        pad = 60e3
        v = v.sel(x=slice(X.min() - pad, X.max() + pad), y=slice(Y.max() + pad, Y.min() - pad))   # y descending
        lat = np.arange(np.ceil(bbox["lat_min"] / target_deg) * target_deg, bbox["lat_max"] + 1e-9, target_deg)
        lon = np.arange(np.ceil(bbox["lon_min"] / target_deg) * target_deg, bbox["lon_max"] + 1e-9, target_deg)
        f = int(round(target_deg * 111.0))   # ~km per target cell
        for y, ms in _years(missing):
            t = v["time"].to_index()
            idx = np.where(pd.DatetimeIndex(t).to_period("M").to_timestamp().isin(ms))[0]
            if idx.size == 0:
                continue
            sub = daymet_to_latlon(v.isel(time=idx), lat, lon, f).compute()
            yield standardize_daymet(sub, name, units, spec, bbox)
            print(f"  daymet {spec['variable']}: cached {y}", flush=True)

    return C.cached_series(cache_path, months, batches)
