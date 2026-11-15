"""Region land masks. A bounding box is not a region: the CONUS bbox also covers ocean, southern
Canada and northern Mexico. Masks are stored once at fine resolution and aggregated onto any
analysis grid as a cell fraction (keep cells with >= `min_frac` of their area inside the region)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]


def _edges(centers: np.ndarray) -> np.ndarray:
    c = np.asarray(centers, dtype=float)
    if c.size == 1:
        return np.array([c[0] - 0.5, c[0] + 0.5])
    mid = (c[:-1] + c[1:]) / 2
    return np.r_[c[0] - (mid[0] - c[0]), mid, c[-1] + (c[-1] - mid[-1])]


def fraction_on_grid(fine: xr.DataArray, lat: np.ndarray, lon: np.ndarray) -> xr.DataArray:
    """Fraction of fine cells (value 1 = inside) falling in each target cell. Target cells with no
    fine cells at all get 0. Coordinates must be ascending."""
    f = np.asarray(fine.values, dtype=float)
    f = np.where(np.isnan(f), 0.0, f)
    iy = np.digitize(fine["lat"].values, _edges(lat)) - 1
    ix = np.digitize(fine["lon"].values, _edges(lon)) - 1
    oky = (iy >= 0) & (iy < len(lat))
    okx = (ix >= 0) & (ix < len(lon))
    f = f[np.ix_(oky, okx)]
    iy, ix = iy[oky], ix[okx]
    flat = (iy[:, None] * len(lon) + ix[None, :]).ravel()
    n = np.bincount(flat, minlength=len(lat) * len(lon))
    s = np.bincount(flat, weights=f.ravel(), minlength=len(lat) * len(lon))
    frac = np.where(n > 0, s / np.maximum(n, 1), 0.0).reshape(len(lat), len(lon))
    return xr.DataArray(frac, dims=("lat", "lon"), coords={"lat": lat, "lon": lon})


def load_fine(path) -> xr.DataArray:
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    with xr.open_dataarray(p) as d:
        return d.load().sortby("lat")


def region_mask(region_def: dict, lat, lon, min_frac: float = 0.5) -> xr.DataArray | None:
    """Boolean (lat, lon) mask for the region on the given grid, or None if the region has no mask."""
    path = region_def.get("mask")
    if not path:
        return None
    frac = fraction_on_grid(load_fine(path), np.asarray(lat), np.asarray(lon))
    return frac >= min_frac
