import numpy as np
import pandas as pd
import pytest
import xarray as xr

from resource_trends import preprocess


def monthly(values, start="2000-01", lat=(0.0,), lon=(0.0,)):
    """(time,) or (time, lat, lon) monthly DataArray."""
    values = np.asarray(values, float)
    if values.ndim == 1:
        values = values[:, None, None]
    time = pd.date_range(start, periods=values.shape[0], freq="MS")
    return xr.DataArray(values, dims=("time", "lat", "lon"), coords={"time": time, "lat": list(lat), "lon": list(lon)})


def test_annualize_sum_mean_max():
    v = np.arange(1, 25, dtype=float)  # 2000: 1..12, 2001: 13..24
    da = monthly(v)
    s = preprocess.annualize(da, "sum", min_count=10)
    m = preprocess.annualize(da, "mean", min_count=10)
    x = preprocess.annualize(da, "max", min_count=10)
    assert s.dims[0] == "year" and s["year"].values.tolist() == [2000, 2001]
    assert s.values[:, 0, 0].tolist() == [78.0, 222.0]
    assert m.values[:, 0, 0].tolist() == [6.5, 18.5]
    assert x.values[:, 0, 0].tolist() == [12.0, 24.0]


def test_annualize_min_count_makes_nan():
    v = np.arange(1, 25, dtype=float)
    v[[0, 1, 2]] = np.nan  # 2000 has 9 valid months
    v[[12]] = np.nan  # 2001 has 11 valid
    da = monthly(v)
    out = preprocess.annualize(da, "mean", min_count=10)
    assert np.isnan(out.values[0, 0, 0]) and np.isfinite(out.values[1, 0, 0])
    assert preprocess.annualize(da, "mean", min_count=9).values[0, 0, 0] == pytest.approx(np.mean(np.arange(4, 13)))


def test_annualize_partial_final_year_is_nan():
    da = monthly(np.ones(30))  # 2000, 2001 full; 2002 has 6 months
    out = preprocess.annualize(da, "sum", min_count=10)
    assert out["year"].values.tolist() == [2000, 2001, 2002]
    assert np.isnan(out.values[2, 0, 0])


def test_annualize_rejects_unknown_how():
    with pytest.raises(ValueError):
        preprocess.annualize(monthly(np.ones(12)), "median", min_count=10)


def test_seasonalize_djf_wraps_year():
    # Months Jan 2000 .. Dec 2001. DJF of "2001" = Dec 2000 + Jan 2001 + Feb 2001.
    v = np.arange(1, 25, dtype=float)
    da = monthly(v)
    out = preprocess.seasonalize(da, "DJF", "mean", min_count=3)
    assert out["year"].values.tolist() == [2000, 2001, 2002]
    # 2000: only Jan, Feb present (Dec 1999 missing) -> NaN at min_count=3
    assert np.isnan(out.values[0, 0, 0])
    # 2001: Dec 2000 (12) + Jan 2001 (13) + Feb 2001 (14)
    assert out.values[1, 0, 0] == pytest.approx(13.0)
    # 2002: only Dec 2001 (24) -> NaN
    assert np.isnan(out.values[2, 0, 0])
    # relaxing min_count keeps the partial seasons
    relaxed = preprocess.seasonalize(da, "DJF", "mean", min_count=1)
    assert relaxed.values[0, 0, 0] == pytest.approx(1.5)


def test_seasonalize_jja_sum():
    v = np.arange(1, 25, dtype=float)
    out = preprocess.seasonalize(monthly(v), "JJA", "sum", min_count=3)
    assert out.values[:, 0, 0].tolist() == [6 + 7 + 8, 18 + 19 + 20]


def test_seasonalize_default_min_count_is_80_percent():
    v = np.ones(12)
    v[5] = np.nan  # JJA has 2 of 3 months
    out = preprocess.seasonalize(monthly(v), "JJA", "mean")
    assert np.isnan(out.values[0, 0, 0])  # ceil(0.8*3)=3 required


def test_area_weights_cos_lat_zero_where_nan():
    lat = np.array([0.0, 60.0])
    lon = np.array([0.0, 1.0, 2.0])
    valid = np.ones((2, 3), bool)
    valid[1, 2] = False
    w = preprocess.area_weights(lat, lon, valid)
    assert w.shape == (2, 3)
    assert w[0, 0] == pytest.approx(1.0) and w[1, 0] == pytest.approx(0.5)
    assert w[1, 2] == 0.0


def test_area_weighted_mean_skips_nan_and_weights_by_cos_lat():
    lat = [0.0, 60.0]
    vals = np.array([[[10.0, 10.0], [20.0, np.nan]]])  # (time=1, lat=2, lon=2)
    da = xr.DataArray(vals, dims=("time", "lat", "lon"), coords={"time": [0], "lat": lat, "lon": [0.0, 1.0]})
    out = preprocess.area_weighted_mean(da)
    # weights: lat0: 1,1 ; lat60: 0.5, (nan -> 0). mean = (10+10+0.5*20)/(1+1+0.5)
    assert out.values[0] == pytest.approx(30.0 / 2.5)


def test_area_weighted_mean_all_nan_is_nan():
    da = xr.DataArray(np.full((2, 2, 2), np.nan), dims=("time", "lat", "lon"),
                      coords={"time": [0, 1], "lat": [0.0, 1.0], "lon": [0.0, 1.0]})
    assert np.isnan(preprocess.area_weighted_mean(da).values).all()
