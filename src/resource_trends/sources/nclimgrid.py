"""NOAA nClimGrid monthly (CONUS, 1/24 deg) from Planetary Computer: one cloud-optimized GeoTIFF per month."""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from . import _common as C
from .planetary import _catalog, _years


def read_cog(href: str, bbox: dict) -> xr.DataArray:
    """Read the window covering bbox from one COG into a (lat, lon) DataArray (north-up flipped)."""
    import rasterio
    from rasterio.windows import from_bounds
    with rasterio.open(href) as r:
        w = from_bounds(bbox["lon_min"] - 0.1, bbox["lat_min"] - 0.1, bbox["lon_max"] + 0.1, bbox["lat_max"] + 0.1, r.transform)
        w = w.round_offsets().round_lengths()
        arr = r.read(1, window=w, boundless=False).astype("float32")
        tr = r.window_transform(w)
        h, wd = arr.shape
        lons = tr.c + tr.a * (np.arange(wd) + 0.5)
        lats = tr.f + tr.e * (np.arange(h) + 0.5)
        if r.nodata is not None and not np.isnan(r.nodata):
            arr[arr == r.nodata] = np.nan
    return xr.DataArray(arr, dims=("lat", "lon"), coords={"lat": lats, "lon": lons})


def standardize(raw: xr.DataArray, name, units, spec, bbox) -> xr.DataArray:
    return C.finalize(raw, name, units, spec["native_units"], "nclimgrid", bbox,
                      dataset=spec["dataset"], native_variable=spec["variable"], product_type=spec["product_type"])


def load(name, units, spec, bbox, months, cache_path, target_deg=None, **_):
    def batches(missing):
        cat = _catalog()
        for y, ms in _years(missing):
            ids = [f"nclimgrid-{m:%Y%m}" for m in ms]
            items = {i.id: i for i in cat.search(collections=[spec["dataset"]], ids=ids).items()}
            slices = []
            for m in ms:
                it = items.get(f"nclimgrid-{m:%Y%m}")
                if it is None:
                    continue
                da = read_cog(it.assets[spec["variable"]].href, bbox).expand_dims(time=[m])
                slices.append(da)
            if not slices:
                continue
            raw = xr.concat(slices, "time")
            yield C.coarsen_to(standardize(raw, name, units, spec, bbox), target_deg)
            print(f"  nclimgrid {spec['variable']}: cached {y}", flush=True)

    return C.cached_series(cache_path, months, batches)
