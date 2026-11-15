"""Portfolio (cross-resource) tests on synthetic data with KNOWN correlation / joint-low behaviour."""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from resource_trends import portfolio
from resource_trends.registry import Registry

N_YEARS = 40
T = N_YEARS * 12
MONTHS = np.tile(np.arange(1, 13), N_YEARS)


def correlated_pair(rng, rho, k, phi=0.0):
    """Two (T, k) noise fields with correlation rho at lag 0, each AR(1) with coefficient phi."""
    def ar1(e):
        x = np.zeros_like(e)
        x[0] = e[0]
        for i in range(1, len(e)):
            x[i] = phi * x[i - 1] + np.sqrt(1 - phi ** 2) * e[i]
        return x
    e1 = rng.normal(size=(T, k))
    e2 = rho * e1 + np.sqrt(1 - rho ** 2) * rng.normal(size=(T, k))
    return ar1(e1), ar1(e2)


def add_season_and_trend(x, amp, slope):
    t = np.arange(T)[:, None]
    return x + amp * np.sin(2 * np.pi * (MONTHS[:, None] - 1) / 12) + slope * t


# --- anomalies ----------------------------------------------------------------------------------
def test_anomalies_remove_seasonality_and_trend():
    rng = np.random.default_rng(0)
    a, b = correlated_pair(rng, 0.0, 200)
    # strong SHARED seasonal cycle and SHARED trend, independent noise
    A = add_season_and_trend(a, 10, 0.02)
    B = add_season_and_trend(b, 10, 0.02)
    raw_r = np.mean([np.corrcoef(A[:, i], B[:, i])[0, 1] for i in range(200)])
    assert raw_r > 0.9                                    # naive correlation is spurious
    r = portfolio.correlation(portfolio.monthly_anomalies(A, MONTHS), portfolio.monthly_anomalies(B, MONTHS))["r"]
    assert abs(r.mean()) < 0.02                           # anomalies reveal independence


def test_anomalies_handle_nan():
    rng = np.random.default_rng(1)
    x = add_season_and_trend(rng.normal(size=(T, 3)), 5, 0.01)
    x[::7, 0] = np.nan
    x[:, 2] = np.nan
    an = portfolio.monthly_anomalies(x, MONTHS)
    assert np.isnan(an[::7, 0]).all() and np.isfinite(an[1::7, 0]).all()
    assert np.isnan(an[:, 2]).all()
    assert abs(np.nanmean(an[:, 0])) < 1e-9


# --- correlation with effective sample size ------------------------------------------------------
@pytest.mark.parametrize("rho", [-0.6, 0.0, 0.3, 0.7])
def test_correlation_recovers_known_rho(rho):
    rng = np.random.default_rng(2)
    a, b = correlated_pair(rng, rho, 300)
    out = portfolio.correlation(portfolio.monthly_anomalies(add_season_and_trend(a, 8, 0.01), MONTHS),
                                portfolio.monthly_anomalies(add_season_and_trend(b, 3, -0.02), MONTHS))
    assert out["r"].mean() == pytest.approx(rho, abs=0.03)


# MEASURED 2026-11-15: independent AR(1) pairs, phi=0.7, n=480 months, 2000 pixels x 3 seeds (10-12),
# two-sided alpha 0.05 -> naive test FPR 25.3%, effective-n (Bretherton 1999) test FPR 5.2% (nominal).
# Thresholds sit just outside the measured values to absorb seed noise.
def test_effective_sample_size_controls_false_positives():
    naive, eff = [], []
    for seed in (10, 11, 12):
        rng = np.random.default_rng(seed)
        a, b = correlated_pair(rng, 0.0, 2000, phi=0.7)
        out = portfolio.correlation(portfolio.monthly_anomalies(a, MONTHS), portfolio.monthly_anomalies(b, MONTHS))
        naive.append((out["p_naive"] < 0.05).mean())
        eff.append((out["p"] < 0.05).mean())
    naive, eff = float(np.mean(naive)), float(np.mean(eff))
    print(f"naive FPR {naive:.4f}  n_eff FPR {eff:.4f}")
    assert naive > 0.20            # measured 25.3%: autocorrelation badly inflates the naive test
    assert eff < 0.065             # measured 5.2%: the effective-n test is near nominal
    assert eff < naive / 2


# --- joint lows ---------------------------------------------------------------------------------
def test_low_flags_are_per_calendar_month():
    rng = np.random.default_rng(3)
    x = add_season_and_trend(rng.normal(size=(T, 50)), 20, 0.0)   # huge seasonal cycle
    low = portfolio.low_flags(portfolio.monthly_anomalies(x, MONTHS), MONTHS, q=0.2)
    by_month = [low[MONTHS == m].mean() for m in range(1, 13)]
    np.testing.assert_allclose(by_month, 0.2, atol=0.03)            # no month is "always low"


def test_joint_low_independent_matches_expectation():
    rng = np.random.default_rng(4)
    an = [portfolio.monthly_anomalies(rng.normal(size=(T, 400)), MONTHS) for _ in range(3)]
    res = portfolio.joint_low(an, MONTHS, q=0.2, k=2)
    # P(at least 2 of 3 low) = 3 * 0.2^2 * 0.8 + 0.2^3 = 0.104
    assert res["expected_independent"].mean() == pytest.approx(0.104, abs=0.005)
    assert res["frequency"].mean() == pytest.approx(0.104, abs=0.01)
    assert res["ratio"].mean() == pytest.approx(1.0, abs=0.1)


def test_joint_low_correlated_vs_complementary():
    rng = np.random.default_rng(5)
    a, b = correlated_pair(rng, 0.95, 300)
    same = portfolio.joint_low([portfolio.monthly_anomalies(a, MONTHS), portfolio.monthly_anomalies(b, MONTHS)], MONTHS, k=2)
    opp = portfolio.joint_low([portfolio.monthly_anomalies(a, MONTHS), portfolio.monthly_anomalies(-b, MONTHS)], MONTHS, k=2)
    assert same["frequency"].mean() > 0.14         # co-moving resources fail together (indep. = 0.04)
    assert opp["frequency"].mean() < 0.005         # complementary resources almost never both low
    assert same["ratio"].mean() > 3 and opp["ratio"].mean() < 0.15


def test_poisson_binomial_at_least_k():
    assert portfolio.prob_at_least_k([0.2, 0.2, 0.2], 2) == pytest.approx(0.104)
    assert portfolio.prob_at_least_k([0.5, 0.5], 1) == pytest.approx(0.75)
    assert portfolio.prob_at_least_k([0.1, 0.2, 0.3], 3) == pytest.approx(0.006)


# --- regridding ---------------------------------------------------------------------------------
def test_regrid_mean_block_average_nan_aware():
    lat = np.arange(0.125, 1.0, 0.25)
    lon = np.arange(0.125, 1.0, 0.25)
    v = np.arange(16, dtype=float).reshape(4, 4)
    v[0, 0] = np.nan
    da = xr.DataArray(np.stack([v, v + 100]), dims=("time", "lat", "lon"),
                      coords={"time": pd.to_datetime(["2000-01-01", "2000-02-01"]), "lat": lat, "lon": lon})
    out = portfolio.regrid_mean(da, np.array([0.25, 0.75]), np.array([0.25, 0.75]))
    assert out.dims == ("time", "lat", "lon") and out.shape == (2, 2, 2)
    assert out.values[0, 0, 0] == pytest.approx(np.mean([1, 4, 5]))
    assert out.values[1, 1, 1] == pytest.approx(np.mean([10, 11, 14, 15]) + 100)


# --- registry primary indices -------------------------------------------------------------------
def test_one_primary_index_per_resource():
    reg = Registry.load()
    assert reg.primary_index("solar") == "solar_irradiance"
    assert reg.primary_index("wind") == "wind_power_density"
    assert reg.primary_index("hydro") == "runoff"


# --- end-to-end analyze on gridded synthetic data ------------------------------------------------
def test_analyze_end_to_end_regional_and_maps():
    rng = np.random.default_rng(6)
    ny, nx = 6, 8
    time = pd.date_range("1981-01-01", periods=T, freq="MS")
    a, b = correlated_pair(rng, -0.5, ny * nx)           # solar vs wind anticorrelated
    c = rng.normal(size=(T, ny * nx))                    # hydro independent
    mk = lambda x, amp: xr.DataArray(add_season_and_trend(x, amp, 0.0).reshape(T, ny, nx), dims=("time", "lat", "lon"),
                                     coords={"time": time, "lat": np.linspace(35, 40, ny), "lon": np.linspace(-100, -93, nx)})
    res = {"solar": mk(a, 50), "wind": mk(b, 2), "hydro": mk(c, 10)}
    maps, regional = portfolio.analyze(res, q=0.2)
    assert set(maps.data_vars) >= {"r_solar_wind", "r_solar_hydro", "r_wind_hydro", "p_solar_wind", "joint_low_frequency", "joint_low_ratio"}
    assert float(maps["r_solar_wind"].mean()) == pytest.approx(-0.5, abs=0.05)
    assert abs(float(maps["r_solar_hydro"].mean())) < 0.05
    pair = regional["correlations"]["solar_wind"]
    assert pair["r"] < -0.3 and pair["p"] < 0.05 and pair["n_eff"] > 50
    jl = regional["joint_low"]
    assert 0 <= jl["frequency"] <= 1 and jl["expected_independent"] == pytest.approx(0.104, abs=0.01)
    assert isinstance(jl["months"], list) and all(len(m["low"]) >= 2 for m in jl["months"])
