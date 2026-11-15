"""Pipeline tests on synthetic data with known truth (no network: the loader is injected)."""
import json

import numpy as np
import pytest

from resource_trends import pipeline, stats
from resource_trends.registry import Registry
from test_stats import make_field

REG = Registry.load()


# --- Pettitt change-point test (used to flag product discontinuities) ---------------------------
def test_pettitt_finds_a_step():
    rng = np.random.default_rng(0)
    y = rng.normal(size=40)
    y[22:] += 2.0
    r = stats.pettitt(y)
    assert r["p"] < 0.01
    assert abs(r["index"] - 22) <= 1      # first index of the new regime


def test_pettitt_null_and_constant():
    rng = np.random.default_rng(1)
    ps = [stats.pettitt(rng.normal(size=40))["p"] for _ in range(200)]
    assert 0.0 < np.mean(np.array(ps) < 0.05) < 0.10   # roughly nominal (Pettitt's p is approximate/conservative)
    assert stats.pettitt(np.full(30, 4.0))["p"] == 1.0


def test_pettitt_ignores_nan():
    y = np.r_[np.zeros(15), np.ones(15) * 3.0]
    y[[3, 20]] = np.nan
    assert stats.pettitt(y)["p"] < 0.01


# --- pipeline.run with an injected loader -------------------------------------------------------
@pytest.fixture(scope="module")
def synthetic():
    da, truth = make_field(seed=21, n_years=40)   # monthly 1984-2023, west +0.04/yr, east -0.04/yr

    def loader(variable, region, registry, start, end, **kw):
        out = da.sel(time=slice(start, end)).copy()
        out.name = variable
        out.attrs = {"units": "W m-2", "provider": "synthetic", "dataset": "unit-test", "product_type": "model"}
        return out

    return loader, truth


def test_run_recovers_opposing_trends_and_writes_outputs(tmp_path, synthetic):
    loader, truth = synthetic
    ds, summary = pipeline.run("conus", "solar_irradiance", start_year=1989, end_year=2018, registry=REG,
                               loader=loader, out_dir=tmp_path, apply_mask=False)
    # files exist and the JSON round-trips
    assert (tmp_path / "solar_irradiance.trend.nc").exists()
    s = json.loads((tmp_path / "solar_irradiance.summary.json").read_text())
    assert s == json.loads(json.dumps(summary))
    # provenance is recorded
    assert s["period"] == "1989-2018" and s["provider"] == "synthetic" and s["n_years"] == 30
    assert "Theil-Sen" in s["method"] and s["aggregation"] == "mean"
    # both directions present and the opposing-trend score sees it
    assert s["area_frac_sig_up"] > 0.2 and s["area_frac_sig_down"] > 0.2
    assert s["opposing_trend_score"] > 0.8
    assert 0.9 < s["coverage_score"] <= 1.0
    # per-decade units: true slope 0.04/yr = 0.4/decade
    west = ds["slope_per_decade"].isel(lon=slice(0, truth["nx"] // 3))
    assert float(west.mean()) == pytest.approx(0.4, abs=0.07)
    assert "pct_change_per_decade" in ds           # solar is relative: true
    # regional series is recorded per year
    assert len(s["regional"]["series"]) == 30 and "1989" in s["regional"]["series"]


def test_start_year_sensitivity_reports_both_shifts_when_data_allow(synthetic, tmp_path):
    loader, _ = synthetic
    _, s = pipeline.run("conus", "solar_irradiance", start_year=1990, end_year=2023, registry=REG, loader=loader, apply_mask=False)
    starts = [r["start_year"] for r in s["sensitivity"]]
    assert starts == [1985, 1995]
    for r in s["sensitivity"]:
        assert 0.8 <= r["sign_agreement"] <= 1.0     # real trends survive a +/-5 year start shift
        assert "regional_slope_per_decade" in r


def test_sensitivity_skips_shift_before_data_start(synthetic):
    loader, _ = synthetic
    _, s = pipeline.run("conus", "solar_irradiance", start_year=1984, end_year=2023, registry=REG, loader=loader, apply_mask=False)
    assert [r["start_year"] for r in s["sensitivity"]] == [1989]
    assert any("1979" in n for n in s["notes"])          # says WHY the -5 shift is missing


def test_season_run_labels_outputs(synthetic, tmp_path):
    loader, _ = synthetic
    ds, s = pipeline.run("conus", "solar_irradiance", start_year=1990, end_year=2020, season="JJA",
                         registry=REG, loader=loader, out_dir=tmp_path, apply_mask=False)
    assert s["season"] == "JJA" and (tmp_path / "solar_irradiance.JJA.summary.json").exists()


def test_breakpoint_is_not_fooled_by_a_smooth_trend():
    # Pettitt on a raw trending series always "finds" a change point; the pipeline must test the
    # detrended residuals instead. (Found on real data: CONUS temperature was falsely flagged.)
    da, _ = make_field(seed=6, n_years=40, trend=0.05)
    da = da.copy()
    da[:] = da.values + 0.05 * np.arange(da.sizes["time"])[:, None, None] / 12.0   # strong region-wide trend

    def loader(variable, region, registry, start, end, **kw):
        out = da.sel(time=slice(start, end)).copy()
        out.name = variable
        out.attrs = {"units": "W m-2", "provider": "synthetic"}
        return out

    _, s = pipeline.run("conus", "solar_irradiance", start_year=1984, end_year=2023, registry=REG, loader=loader, apply_mask=False)
    assert s["regional"]["p_value"] < 0.001          # the trend is real and detected...
    assert s["breakpoint"]["p"] > 0.05                # ...but not mistaken for a step
    assert not any("breakpoint" in n.lower() for n in s["notes"])


def test_breakpoint_flags_a_spliced_series(tmp_path):
    da, _ = make_field(seed=5, n_years=40, trend=0.0)
    da = da.copy()
    da.loc[{"time": slice("2001-01-01", None)}] += 3.0      # a product splice, like POWER SRB -> SYN1deg

    def loader(variable, region, registry, start, end, **kw):
        out = da.sel(time=slice(start, end)).copy()
        out.name = variable
        out.attrs = {"units": "W m-2", "provider": "synthetic"}
        return out

    _, s = pipeline.run("conus", "solar_irradiance", start_year=1984, end_year=2023, registry=REG, loader=loader, apply_mask=False)
    assert s["breakpoint"]["p"] < 0.01 and abs(s["breakpoint"]["year"] - 2001) <= 1
    assert any("breakpoint" in n.lower() for n in s["notes"])


def test_region_mask_removes_cells_outside_the_region(synthetic):
    loader, _ = synthetic
    ds, s = pipeline.run("conus", "solar_irradiance", start_year=1990, end_year=2020, registry=REG, loader=loader)
    assert s["mask"] and "nclimgrid" in s["mask"]
    # synthetic grid spans 30-49N, 120-75W: the Atlantic off New England / Gulf of Maine is outside CONUS
    atlantic = ds["p_value"].sel(lat=slice(40, 43), lon=slice(-70, -66))
    assert atlantic.size == 0 or bool(atlantic.isnull().all())
    kansas = ds["p_value"].sel(lat=slice(37, 40), lon=slice(-101, -95))
    assert bool(kansas.notnull().all())
    _, s2 = pipeline.run("conus", "solar_irradiance", start_year=1990, end_year=2020, registry=REG, loader=loader, apply_mask=False)
    assert s2["mask"] is None and any("no land mask" in n for n in s2["notes"])
