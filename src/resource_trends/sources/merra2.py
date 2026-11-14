"""MERRA-2 monthly 2-D collections via earthaccess, STREAMED and cropped (never downloaded whole).

Each global monthly file is 60-84 MB; we read only the region's hyperslab through HTTPS range
requests (earthaccess.open + h5netcdf), one worker process per file, then cache the cropped series.
"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import xarray as xr

from . import _common as C


def _init_worker():
    import earthaccess
    earthaccess.login(strategy="netrc")


def _fetch_one(args):
    """Worker: stream one granule's region subset. Returns (month 'YYYYMM', 2-D values, lat, lon)."""
    granule, var, bbox, month = args
    import earthaccess
    last = None
    for attempt in range(4):
        try:
            f = earthaccess.open([granule])[0]
            with xr.open_dataset(f, engine="h5netcdf") as ds:
                sub = ds[var].sel(lat=slice(bbox["lat_min"] - 1, bbox["lat_max"] + 1),
                                  lon=slice(bbox["lon_min"] - 1, bbox["lon_max"] + 1)).isel(time=0).load()
                return month, sub.values, sub["lat"].values, sub["lon"].values
        except Exception as e:  # network hiccups are common; retry with backoff
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed to stream {month} {var}: {last}")


def standardize(raw: xr.DataArray, name, units, spec, bbox) -> xr.DataArray:
    """Pure step: raw (time, lat, lon) with MERRA-2 coordinates -> contract."""
    return C.finalize(raw, name, units, spec["native_units"], "merra2", bbox,
                      dataset=spec["dataset"], native_variable=spec["variable"], product_type=spec["product_type"])


def load(name, units, spec, bbox, months, cache_path, target_deg=None, workers=4) -> xr.DataArray:
    import earthaccess

    def batches(missing):
        earthaccess.login(strategy="netrc")
        first, last = missing.min(), missing.max()
        granules = earthaccess.search_data(short_name=spec["dataset"],
                                           temporal=(f"{first:%Y-%m-01}", f"{last:%Y-%m-28}"))
        by_month = {g["umm"]["GranuleUR"].split(".")[-2]: g for g in granules}
        wanted = [f"{m:%Y%m}" for m in missing if f"{m:%Y%m}" in by_month]
        years = sorted({w[:4] for w in wanted})
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
            for y in years:  # one cache save per year
                jobs = [(by_month[w], spec["variable"], bbox, w) for w in wanted if w.startswith(y)]
                res = sorted(ex.map(_fetch_one, jobs), key=lambda r: r[0])
                lat, lon = res[0][2], res[0][3]
                raw = xr.DataArray(np.stack([r[1] for r in res]), dims=("time", "lat", "lon"),
                                   coords={"time": pd.to_datetime([r[0] + "01" for r in res], format="%Y%m%d"),
                                           "lat": lat, "lon": lon})
                yield C.coarsen_to(standardize(raw, name, units, spec, bbox), target_deg)
                print(f"  merra2 {spec['dataset']}/{spec['variable']}: cached {y}", flush=True)

    return C.cached_series(cache_path, months, batches)
