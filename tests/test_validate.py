"""Validation helpers: parsing NOAA formats and comparison metrics (synthetic truth; no network)."""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from resource_trends import validate

USCRN_LINES = """\
53926 201906  2.622  -97.0914   36.1181    31.2    19.8    25.5    25.7    95.3   24.30 C    38.0    21.6    29.0
53926 201907  2.622  -97.0914   36.1181 -9999.0 -9999.0 -9999.0 -9999.0 -9999.0 -9999.0 U -9999.0 -9999.0 -9999.0
53926 201908  2.622  -97.0914   36.1181    33.9    21.0    27.5    27.4    61.0   21.60 C    40.1    23.0    30.5
"""


def test_parse_uscrn_units_and_missing():
    df = validate.parse_uscrn(USCRN_LINES, "OK_Stillwater_2_W")
    assert list(df["date"].dt.strftime("%Y-%m")) == ["2019-06", "2019-07", "2019-08"]
    assert df["solar"].iloc[0] == pytest.approx(24.30 * 1e6 / 86400)       # MJ m-2 day-1 -> W m-2
    assert np.isnan(df["solar"].iloc[1]) and np.isnan(df["tavg"].iloc[1])
    assert df["tavg"].iloc[2] == pytest.approx(27.4) and df["prcp"].iloc[0] == pytest.approx(95.3)
    assert df["lat"].iloc[0] == pytest.approx(36.1181) and df["station"].iloc[0] == "OK_Stillwater_2_W"


def test_parse_gsom_rows():
    rows = [{"DATE": "1981-01", "STATION": "USW00023183", "NAME": "PHOENIX AIRPORT, AZ US", "LATITUDE": "33.4278",
             "LONGITUDE": "-112.00365", "TAVG": "15.1", "PRCP": "18.0"},
            {"DATE": "1981-02", "STATION": "USW00023183", "NAME": "PHOENIX AIRPORT, AZ US", "LATITUDE": "33.4278",
             "LONGITUDE": "-112.00365", "TAVG": "", "PRCP": "3.2"}]
    df = validate.parse_gsom(rows)
    assert df["tavg"].iloc[0] == 15.1 and np.isnan(df["tavg"].iloc[1]) and df["prcp"].iloc[1] == 3.2
    assert df["date"].iloc[1] == pd.Timestamp("1981-02-01") and df["lon"].iloc[0] == pytest.approx(-112.00365)


def _series(values, start="1981-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"))


def test_compare_known_bias_and_trend():
    rng = np.random.default_rng(0)
    n = 40 * 12
    t = np.arange(n)
    season = 10 * np.sin(2 * np.pi * t / 12)
    obs = _series(15 + season + 0.003 * t + rng.normal(scale=0.5, size=n))          # 0.36 /decade
    model = _series(obs.values + 1.5)                                                 # pure +1.5 bias
    m = validate.compare(obs, model)
    assert m["bias"] == pytest.approx(1.5) and m["rmse"] == pytest.approx(1.5)
    assert m["r"] == pytest.approx(1.0) and m["r_anom"] == pytest.approx(1.0)
    assert m["trend_obs_per_decade"] == pytest.approx(0.36, abs=0.06)
    assert m["trend_diff_per_decade"] == pytest.approx(0.0, abs=1e-9)
    assert m["n_months"] == n and m["period"] == "1981-01..2020-12"


def test_compare_detects_trend_mismatch_and_handles_gaps():
    rng = np.random.default_rng(1)
    n = 30 * 12
    t = np.arange(n)
    obs = _series(rng.normal(size=n) + 0.0 * t)
    model = _series(obs.values + 0.01 * t)                                            # spurious +1.2 /decade
    obs.iloc[rng.choice(n, 15, replace=False)] = np.nan   # sparse random gaps, like real station records
    m = validate.compare(obs, model, relative=False)
    assert m["trend_diff_per_decade"] == pytest.approx(1.2, abs=0.1)
    assert m["n_months"] == int(np.isfinite(obs).sum())


def test_compare_relative_bias_for_precip_like():
    obs = _series(np.full(24, 100.0))
    m = validate.compare(obs, _series(np.full(24, 90.0)), relative=True)
    assert m["bias_pct"] == pytest.approx(-10.0)


def test_nearest_cell_series_skips_masked_cell():
    time = pd.date_range("2000-01-01", periods=3, freq="MS")
    vals = np.ones((3, 2, 2))
    vals[:, 0, 0] = np.nan                                         # nearest cell is all-NaN (coast)
    vals[:, 0, 1] = 7.0
    da = xr.DataArray(vals, dims=("time", "lat", "lon"), coords={"time": time, "lat": [30.0, 30.5], "lon": [-90.0, -89.5]})
    s, info = validate.cell_series(da, 30.05, -89.95)
    assert info["distance_deg"] > 0 and (s.values == 7.0).all()   # next-nearest valid cell used, and reported


def test_compare_too_gappy_for_annual_trend_gives_nan_not_garbage():
    # every 5th month missing -> only 9-10 valid months a year; the >=10-month annual rule drops most
    # years, so the trend is reported as NaN instead of being estimated from too little data
    rng = np.random.default_rng(2)
    obs = _series(rng.normal(size=360))
    obs.iloc[::5] = np.nan
    m = validate.compare(obs, _series(rng.normal(size=360)))
    assert np.isnan(m["trend_diff_per_decade"]) and np.isfinite(m["bias"])
