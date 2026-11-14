"""NASA POWER analysis-ready Zarr on AWS open data (anonymous S3). Cropped on read."""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from . import _common as C


def standardize(raw: xr.DataArray, name, units, spec, bbox) -> xr.DataArray:
    """Pure step. POWER stamps months at month END and pre-allocates the time axis to 2029
    (future months are all-NaN); both are handled here."""
    raw = raw.dropna("time", how="all")
    return C.finalize(raw, name, units, spec["native_units"], "nasa_power", bbox,
                      dataset=spec["dataset"], native_variable=spec["variable"], product_type=spec["product_type"])


def _open(store: str) -> xr.Dataset:
    import s3fs
    fs = s3fs.S3FileSystem(anon=True)
    return xr.open_zarr(fs.get_mapper(store.removeprefix("s3://")), consolidated=None)


def load(name, units, spec, bbox, months, cache_path, target_deg=None, **_) -> xr.DataArray:
    def batches(missing):
        ds = _open(spec["dataset"])
        v = ds[spec["variable"]]
        v = v.sel(lat=slice(bbox["lat_min"] - 1, bbox["lat_max"] + 1), lon=slice(bbox["lon_min"] - 1, bbox["lon_max"] + 1))
        t = C.to_month_start(v["time"].values)
        v = v.isel(time=np.where(t.isin(missing))[0]).load()
        if v.sizes["time"]:
            yield C.coarsen_to(standardize(v, name, units, spec, bbox), target_deg)

    return C.cached_series(cache_path, months, batches)
