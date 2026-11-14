"""Per-pixel trend statistics: Theil-Sen slope, Mann-Kendall test, autocorrelation correction, BH-FDR.

Numpy in, numpy out. Inputs are shaped (n_time, n_pixels) with NaN for missing values and must be
ordered by ascending time. Pairwise differences grow with n^2, so all heavy work is chunked over
pixels to keep memory bounded. `trend_map` is a thin xarray wrapper that builds map Datasets.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
from scipy.special import erfc

DEFAULT_MIN_VALID_FRAC = 0.8
DEFAULT_MIN_COUNT = 10
_CHUNK_BYTES = 64e6


def _chunk_slices(n_time: int, n_pix: int, budget: float = _CHUNK_BYTES):
    npairs = n_time * (n_time - 1) // 2
    per_pixel = max(1, 8 * 3 * npairs + n_time * n_time)
    size = max(1, int(budget // per_pixel))
    for a in range(0, n_pix, size):
        yield slice(a, min(a + size, n_pix))


def _as_2d(y):
    y = np.asarray(y, dtype=float)
    if y.ndim != 2:
        raise ValueError("expected an array shaped (n_time, n_pixels)")
    return y


def _nanmedian0(a):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(a, axis=0)


# --- Theil-Sen ----------------------------------------------------------------------------------
def theil_sen(y, t):
    """Median of pairwise slopes using the real time coordinate t, skipping pairs with a NaN.

    Returns (slope, intercept) per pixel; intercept = median(y) - slope * median(t) over valid points
    (same convention as scipy.stats.theilslopes). NaN where fewer than 2 usable pairs.
    """
    y = _as_2d(y)
    t = np.asarray(t, dtype=float)
    n, k = y.shape
    if t.shape != (n,):
        raise ValueError("t must have length n_time")
    i, j = np.triu_indices(n, 1)
    dt = (t[j] - t[i])[:, None]
    dt = np.where(dt == 0, np.nan, dt)  # duplicate times carry no slope information
    slope = np.full(k, np.nan)
    intercept = np.full(k, np.nan)
    for sl in _chunk_slices(n, k):
        yc = y[:, sl]
        slope[sl] = _nanmedian0((yc[j] - yc[i]) / dt)
        t_med = _nanmedian0(np.where(np.isnan(yc), np.nan, t[:, None]))
        intercept[sl] = _nanmedian0(yc) - slope[sl] * t_med
    return slope, intercept


# --- Mann-Kendall -------------------------------------------------------------------------------
def mann_kendall(y):
    """Mann-Kendall test per pixel (series must be in time order; NaNs are skipped).

    Returns dict with S, var (tie-corrected), z (continuity-corrected), p (two-sided), n (valid count).
    A constant series gives S=0, z=0, p=1. Pixels with fewer than 2 valid values are NaN.
    """
    y = _as_2d(y)
    n, k = y.shape
    i, j = np.triu_indices(n, 1)
    S = np.zeros(k)
    tie = np.zeros(k)
    for sl in _chunk_slices(n, k):
        yc = y[:, sl]
        S[sl] = np.nansum(np.sign(yc[j] - yc[i]), axis=0)
        eq = yc[:, None, :] == yc[None, :, :]  # NaN == NaN is False, so NaNs never tie
        c = eq.sum(axis=1)  # group size per valid element (includes itself)
        tie[sl] = np.where(np.isnan(yc), 0, (c - 1) * (2 * c + 5)).sum(axis=0)
    nv = np.sum(~np.isnan(y), axis=0).astype(float)
    var = (nv * (nv - 1) * (2 * nv + 5) - tie) / 18.0
    z, p = _z_p(S, var)
    too_few = nv < 2
    S = np.where(too_few, np.nan, S)
    var = np.where(too_few, np.nan, var)
    z = np.where(too_few, np.nan, z)
    p = np.where(too_few, np.nan, p)
    return {"S": S, "var": var, "z": z, "p": p, "n": nv.astype(int)}


def _z_p(S, var):
    with np.errstate(divide="ignore", invalid="ignore"):
        sd = np.sqrt(var)
        z = np.where(S > 0, (S - 1) / sd, np.where(S < 0, (S + 1) / sd, 0.0))
    z = np.where(var > 0, z, 0.0)
    p = erfc(np.abs(z) / math.sqrt(2.0))
    return z, p


# --- Autocorrelation ----------------------------------------------------------------------------
def lag1_autocorr(resid):
    """Lag-1 autocorrelation per pixel, NaN-aware (pairs with a NaN are skipped). 0 if variance is 0."""
    r = _as_2d(resid)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        a = r - np.nanmean(r, axis=0)
        num = np.nansum(a[:-1] * a[1:], axis=0)
        den = np.nansum(a * a, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = np.where(den > 0, num / den, 0.0)
    return np.clip(rho, -0.99, 0.99)


# --- Combined trend -----------------------------------------------------------------------------
def trend(y, t, min_valid_frac=DEFAULT_MIN_VALID_FRAC, min_count=DEFAULT_MIN_COUNT, autocorr=True):
    """Theil-Sen slope + Mann-Kendall significance per pixel, with optional autocorrelation correction.

    Quality rule: a pixel is NaN unless it has >= min_valid_frac of n_time valid values AND at least
    min_count valid values. Autocorrelation: the MK variance is multiplied by (1+rho1)/(1-rho1) when
    the lag-1 autocorrelation rho1 of the Sen residuals is positive (never deflated).

    Returns dict: slope (per unit of t), intercept, S, z, p (corrected if autocorr), p_raw, rho1,
    var_factor, n_valid (reported even for rejected pixels).
    """
    y = _as_2d(y)
    t = np.asarray(t, dtype=float)
    n = y.shape[0]
    n_valid = np.sum(~np.isnan(y), axis=0)
    ok = (n_valid >= min_valid_frac * n - 1e-9) & (n_valid >= min_count)

    slope, intercept = theil_sen(y, t)
    mk = mann_kendall(y)
    resid = y - (intercept + slope * t[:, None])
    rho = lag1_autocorr(resid)
    factor = np.where(rho > 0, (1 + rho) / (1 - rho), 1.0) if autocorr else np.ones_like(rho)
    z, p = _z_p(mk["S"], mk["var"] * factor)

    out = {
        "slope": slope,
        "intercept": intercept,
        "S": mk["S"],
        "z": z,
        "p": p,
        "p_raw": mk["p"],
        "rho1": rho,
        "var_factor": factor,
    }
    out = {name: np.where(ok, v, np.nan) for name, v in out.items()}
    out["n_valid"] = n_valid
    return out


# --- Change point -------------------------------------------------------------------------------
def pettitt(y):
    """Pettitt (1979) non-parametric single change-point test on a 1-D series (NaNs skipped).

    Returns dict(index, K, p): `index` is the position (in the ORIGINAL array) of the first value of
    the new regime; p uses the standard approximation 2*exp(-6K^2/(n^3+n^2)), capped at 1.
    Used to flag product discontinuities (e.g. a satellite-era splice), not to model them.
    """
    y = np.asarray(y, dtype=float)
    pos = np.where(~np.isnan(y))[0]
    x = y[pos]
    n = x.size
    if n < 3:
        return {"index": None, "K": 0.0, "p": float("nan")}
    D = np.sign(x[None, :] - x[:, None])          # D[i, j] = sign(x_j - x_i)
    U = np.array([D[: t + 1, t + 1:].sum() for t in range(n - 1)])
    t_star = int(np.argmax(np.abs(U)))
    K = float(np.abs(U[t_star]))
    p = min(1.0, 2.0 * math.exp(-6.0 * K * K / (n ** 3 + n ** 2)))
    return {"index": int(pos[t_star + 1]), "K": K, "p": p}


# --- Field significance -------------------------------------------------------------------------
def fdr_bh(p, alpha=0.10):
    """Benjamini-Hochberg FDR across pixels (any array shape). Returns (significant mask, q-values).

    NaN p-values stay NaN in q and False in the mask. q is monotone in sorted p.
    """
    p = np.asarray(p, dtype=float)
    flat = p.ravel()
    q = np.full(flat.shape, np.nan)
    ok = ~np.isnan(flat)
    m = int(ok.sum())
    if m:
        order = np.argsort(flat[ok], kind="stable")
        scaled = flat[ok][order] * m / np.arange(1, m + 1)
        scaled = np.minimum.accumulate(scaled[::-1])[::-1]
        qv = np.empty(m)
        qv[order] = np.minimum(scaled, 1.0)
        q[ok] = qv
    mask = np.zeros(flat.shape, bool)
    mask[ok] = q[ok] <= alpha
    return mask.reshape(p.shape), q.reshape(p.shape)


# --- xarray wrapper -----------------------------------------------------------------------------
def _time_in_years(coord):
    v = np.asarray(coord.values)
    if np.issubdtype(v.dtype, np.datetime64):
        return v.astype("datetime64[ns]").astype("int64") / (365.2425 * 86400e9) + 1970.0
    return v.astype(float)


def trend_map(da, time_dim=None, relative=False, alpha_fdr=0.10, **kwargs):
    """Run `trend` + FDR on a (time|year, lat, lon) DataArray and return a Dataset of maps.

    Variables: slope_per_decade, total_change (slope * span of the record), pct_change_per_decade
    (only if relative=True; NaN where |mean| is ~0), p_value, q_value, significant, direction
    (+1/-1 where significant, else 0; NaN where undefined), rho1, n_valid.
    The time coordinate must be in years (or datetime64, converted to decimal years).
    """
    import xarray as xr

    time_dim = time_dim or ("year" if "year" in da.dims else "time")
    da = da.transpose(time_dim, ...)
    spatial = da.dims[1:]
    shape = da.shape[1:]
    t = _time_in_years(da[time_dim])
    y = da.values.reshape(da.shape[0], -1)
    r = trend(y, t, **kwargs)
    mask, q = fdr_bh(r["p"], alpha=alpha_fdr)

    def m(a):
        return (spatial, np.asarray(a, dtype=float).reshape(shape))

    slope_dec = r["slope"] * 10.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(y, axis=0)
    ds = xr.Dataset(
        {
            "slope_per_decade": m(slope_dec),
            "total_change": m(r["slope"] * (t[-1] - t[0])),
            "p_value": m(r["p"]),
            "q_value": m(q),
            "significant": (spatial, mask.reshape(shape)),
            "direction": m(np.where(np.isnan(r["p"]), np.nan, np.where(mask, np.sign(r["slope"]), 0.0))),
            "rho1": m(r["rho1"]),
            "n_valid": (spatial, r["n_valid"].reshape(shape)),
        },
        coords={d: da[d] for d in spatial if d in da.coords},
    )
    if relative:
        with np.errstate(divide="ignore", invalid="ignore"):
            pct = np.where(np.abs(mean) > 1e-12, 100.0 * slope_dec / np.abs(mean), np.nan)
        ds["pct_change_per_decade"] = m(pct)
    ds.attrs.update(
        period=f"{t[0]:.0f}-{t[-1]:.0f}",
        method="Theil-Sen slope; Mann-Kendall (tie-corrected, lag-1 autocorrelation-adjusted: "
        f"{kwargs.get('autocorr', True)}); Benjamini-Hochberg FDR alpha={alpha_fdr}",
    )
    return ds
