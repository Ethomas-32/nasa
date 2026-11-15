"""Anomaly alerts vs a trend-adjusted, same-calendar-month baseline (synthetic truth; no network)."""
import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from resource_trends import alerts
from resource_trends.registry import Registry

REG = Registry.load()


def monthly_field(n_years=40, start="1985-01", ny=4, nx=5, trend=0.0, seed=0, season_amp=10.0):
    rng = np.random.default_rng(seed)
    time = pd.date_range(start, periods=n_years * 12, freq="MS")
    t = np.arange(time.size)
    season = season_amp * np.sin(2 * np.pi * (time.month.values - 1) / 12)
    data = 50 + season[:, None, None] + trend * (t / 12.0)[:, None, None] + rng.normal(size=(time.size, ny, nx))
    return xr.DataArray(data, dims=("time", "lat", "lon"),
                        coords={"time": time, "lat": np.linspace(35, 38, ny), "lon": np.linspace(-100, -96, nx)})


# --- core percentile ----------------------------------------------------------------------------
def test_percentile_rank_definition():
    base = np.arange(1.0, 11.0)[:, None]                 # 1..10
    assert alerts.percentile_of(np.array([0.5]), base)[0] == 0.0
    assert alerts.percentile_of(np.array([10.5]), base)[0] == 100.0
    assert alerts.percentile_of(np.array([5.0]), base)[0] == pytest.approx(45.0)   # 4 below + half of 1 tie


def test_extreme_low_latest_month_is_flagged():
    da = monthly_field(seed=1)
    da[-1, :2, :] = da[-1, :2, :] - 8.0                  # very low last month in the north half
    res = alerts.pixel_percentiles(da)
    pct = res["percentile"]
    assert (pct[:2] <= 5).all() and (pct[2:] > 5).any()
    assert res["latest"] == da["time"].values[-1]
    # data 1985-01..2024-12: latest is Dec 2024, baseline = the 30 previous Decembers 1994-2023
    assert res["baseline_years"] == (1994, 2023) and res["n_baseline"] == 30


def test_trend_adjustment_matters():
    # Strong warming: an ON-TREND latest value is unremarkable after trend adjustment, but would be a
    # "record high" against the raw same-month history.
    da = monthly_field(trend=0.5, seed=2)
    res = alerts.pixel_percentiles(da)
    assert np.median(res["percentile"]) > 15 and np.median(res["percentile"]) < 85
    assert np.median(res["percentile_raw"]) > 90


def test_same_calendar_month_only():
    # Huge seasonal cycle; latest month is a December at the December norm -> not an alert, even though
    # it is far below the annual mean.
    da = monthly_field(season_amp=40.0, seed=3)
    da = da.isel(time=slice(0, -1))                       # ends in November
    da = da.isel(time=slice(0, -1))                       # ends in October; Oct is near-norm
    res = alerts.pixel_percentiles(da)
    assert (res["percentile"] > 5).mean() > 0.8


def test_nan_and_short_baseline():
    da = monthly_field(n_years=12, seed=4)               # only 11 baseline years < 15
    res = alerts.pixel_percentiles(da)
    assert np.isnan(res["percentile"]).all()
    da = monthly_field(seed=5)
    da[:, 0, 0] = np.nan
    res = alerts.pixel_percentiles(da)
    assert np.isnan(res["percentile"][0, 0]) and np.isfinite(res["percentile"][1, 1])


def test_latest_month_is_last_with_data():
    da = monthly_field(seed=6)
    da = xr.concat([da, da.isel(time=slice(-2, None)).assign_coords(
        time=pd.date_range(pd.Timestamp(da.time.values[-1]) + pd.offsets.MonthBegin(1), periods=2, freq="MS")) * np.nan], "time")
    res = alerts.pixel_percentiles(da)
    assert res["latest"] == da["time"].values[-3]         # trailing all-NaN months ignored


# --- variable-level alert -----------------------------------------------------------------------
def test_alert_for_variable_reports_area_direction_and_label():
    da = monthly_field(seed=7)
    da[-1] = da[-1] - 8.0                                # whole region very low
    a = alerts.variable_alert(da, "runoff", REG, region="conus", today=pd.Timestamp("2026-11-15"))
    assert a["label"] == "anomaly, not forecast"
    assert a["adverse"] == "low" and a["status"] in ("alert", "strong alert")
    assert a["area_frac_low_10"] > 0.9 and a["area_frac_high_90"] == 0.0
    assert a["regional"]["percentile"] <= 5
    assert a["data_month"] == pd.Timestamp(da.time.values[-1]).strftime("%Y-%m")
    assert a["latency_days"] > 0
    assert "same calendar month" in a["baseline"]["definition"]


def test_high_adverse_variable_low_value_is_not_an_alert():
    da = monthly_field(seed=8)
    da[-1] = da[-1] - 8.0                                # very LOW temperature month
    a = alerts.variable_alert(da, "air_temp_2m", REG, region="conus", today=pd.Timestamp("2026-11-15"))
    assert a["adverse"] == "high"
    assert a["status"] == "none"                         # unusual, but not in the adverse direction
    assert a["area_frac_low_10"] > 0.9                   # still reported


def test_subregions_listed_for_alert_cells():
    da = monthly_field(seed=9)
    da[-1] = da[-1] - 8.0
    a = alerts.variable_alert(da, "runoff", REG, region="conus", today=pd.Timestamp("2026-11-15"))
    names = [s["name"] for s in a["subregions"]]
    assert "Plains" in names or "Southwest" in names    # synthetic grid sits at 35-38N, 100-96W
    for s in a["subregions"]:
        assert 0 <= s["area_frac_adverse"] <= 1


def test_every_variable_has_adverse_direction():
    for name, v in REG.variables.items():
        assert v.get("adverse") in ("low", "high", "both"), name
    assert "subregions" in REG.regions["conus"]


def test_run_writes_sorted_alerts_and_records_failures(tmp_path):
    def loader(variable, region, registry, start, end, **kw):
        if variable == "pdsi":
            raise ConnectionError("simulated outage")
        da = monthly_field(seed=hash(variable) % 1000)
        if variable == "runoff":
            da[-1] = da[-1] - 8.0
        da.attrs = {"units": "x", "provider": "synthetic"}
        return da

    res = alerts.run("conus", REG, loader=loader, out_dir=tmp_path, variables=["solar_irradiance", "runoff", "pdsi"],
                     today=pd.Timestamp("2026-11-15"), apply_mask=False)
    saved = json.loads((tmp_path / "alerts.json").read_text())
    assert saved["label"] == "anomaly, not forecast" and saved == json.loads(json.dumps(res))
    assert saved["alerts"][0]["variable"] == "runoff"                 # most severe first
    assert [f["variable"] for f in saved["failures"]] == ["pdsi"]
    assert (tmp_path / "runoff.alert.nc").exists()
    assert all("_maps" not in a for a in saved["alerts"])
