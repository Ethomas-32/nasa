"""Tests that define "correct" for the statistics engine (CLAUDE.md section 11)."""
import numpy as np
import pytest
from scipy import stats as sps

from reference import mk_reference, theil_sen_reference
from resource_trends import stats


def _random_columns(rng, n=30, k=40, nan_frac=0.0, ties=False):
    y = rng.integers(0, 6, size=(n, k)).astype(float) if ties else rng.normal(size=(n, k))
    if nan_frac:
        y[rng.random(y.shape) < nan_frac] = np.nan
    return y


# 1. Mann-Kendall vs pure-python reference ------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_mann_kendall_matches_reference_random(seed):
    rng = np.random.default_rng(seed)
    y = _random_columns(rng, nan_frac=0.1)
    out = stats.mann_kendall(y)
    for k in range(y.shape[1]):
        s, var, z, p, n = mk_reference(list(y[:, k]))
        assert out["S"][k] == s
        assert out["var"][k] == pytest.approx(var, abs=1e-9)
        assert out["z"][k] == pytest.approx(z, abs=1e-9)
        assert out["p"][k] == pytest.approx(p, abs=1e-9)
        assert out["n"][k] == n


# 3. Heavy ties ---------------------------------------------------------------------------------
def test_mann_kendall_heavy_ties_matches_reference():
    rng = np.random.default_rng(3)
    y = _random_columns(rng, n=40, k=50, ties=True, nan_frac=0.05)
    out = stats.mann_kendall(y)
    for k in range(y.shape[1]):
        s, var, z, p, _ = mk_reference(list(y[:, k]))
        assert out["S"][k] == s
        assert out["var"][k] == pytest.approx(var, abs=1e-9)
        assert out["z"][k] == pytest.approx(z, abs=1e-9)
        assert out["p"][k] == pytest.approx(p, abs=1e-9)


def test_tie_correction_actually_matters():
    # Guard against a "tie-corrected" implementation that silently ignores ties.
    y = np.array([[1, 1, 1, 2, 2, 3, 3, 3, 3, 4]], dtype=float).T
    n = 10
    uncorrected = n * (n - 1) * (2 * n + 5) / 18.0
    assert stats.mann_kendall(y)["var"][0] < uncorrected - 1


# 2. Theil-Sen vs scipy -------------------------------------------------------------------------
def test_theil_sen_matches_scipy_with_gaps():
    rng = np.random.default_rng(4)
    t = np.arange(1984, 2024, dtype=float)
    y = 0.3 * (t - t[0])[:, None] + rng.normal(size=(t.size, 12))
    y[rng.random(y.shape) < 0.15] = np.nan
    slope, intercept = stats.theil_sen(y, t)
    for k in range(y.shape[1]):
        ok = ~np.isnan(y[:, k])
        ref = sps.theilslopes(y[ok, k], t[ok])
        assert slope[k] == pytest.approx(ref[0], abs=1e-10)
        assert intercept[k] == pytest.approx(ref[1], abs=1e-9)
        assert slope[k] == pytest.approx(theil_sen_reference(t, y[:, k]), abs=1e-10)


def test_theil_sen_uses_real_time_coordinate():
    # Unevenly spaced times: slope must be per unit of t, not per index.
    t = np.array([0.0, 1.0, 2.0, 10.0, 20.0])
    y = (2.0 * t)[:, None]
    slope, _ = stats.theil_sen(y, t)
    assert slope[0] == pytest.approx(2.0, abs=1e-12)


# 4. Missing-data rules -------------------------------------------------------------------------
def test_missing_data_rules():
    rng = np.random.default_rng(5)
    n = 40
    t = np.arange(n, dtype=float)
    base = 0.1 * t + rng.normal(size=n)
    y = np.tile(base[:, None], (1, 4))
    y[rng.choice(n, 4, replace=False), 0] = np.nan  # 10% missing -> kept
    y[rng.choice(n, 16, replace=False), 1] = np.nan  # 40% missing -> NaN
    y[:, 2] = 5.0  # constant
    y[rng.choice(n, 8, replace=False), 3] = np.nan  # 20% missing -> exactly at the limit, kept
    r = stats.trend(y, t)
    assert np.isfinite(r["slope"][0]) and np.isfinite(r["p"][0])
    assert np.isnan(r["slope"][1]) and np.isnan(r["p"][1]) and np.isnan(r["z"][1])
    assert r["n_valid"][1] == 24  # n_valid is reported even where the pixel is rejected
    assert r["slope"][2] == 0.0 and r["p"][2] == 1.0
    assert np.isfinite(r["slope"][3])


def test_min_count_rule():
    t = np.arange(8, dtype=float)
    y = (t + np.array([0.1, -0.1, 0.2, -0.2, 0.1, 0.0, -0.1, 0.1]))[:, None]
    assert np.isnan(stats.trend(y, t, min_count=10)["slope"][0])
    assert np.isfinite(stats.trend(y, t, min_count=5)["slope"][0])


def test_all_nan_pixel_does_not_raise():
    y = np.full((30, 3), np.nan)
    y[:, 1] = np.arange(30.0)
    r = stats.trend(y, np.arange(30.0))
    assert np.isnan(r["slope"][0]) and np.isnan(r["p"][2])
    assert r["slope"][1] == pytest.approx(1.0)


def test_constant_series_mann_kendall():
    out = stats.mann_kendall(np.full((20, 2), 3.0))
    assert np.all(out["p"] == 1.0) and np.all(out["z"] == 0.0)


# 5. BH-FDR -------------------------------------------------------------------------------------
def test_fdr_bh_hand_computed_with_nan():
    # m = 4 valid. Sorted p: .005 .01 .03 .04 -> p*m/rank: .02 .02 .04 .04 (already monotone)
    p = np.array([0.01, 0.04, 0.03, 0.005, np.nan])
    mask, q = stats.fdr_bh(p, alpha=0.03)
    np.testing.assert_allclose(q[:4], [0.02, 0.04, 0.04, 0.02], atol=1e-15)
    assert np.isnan(q[4])
    assert mask.tolist() == [True, False, False, True, False]


def test_fdr_bh_enforces_monotone_q():
    # Raw p*m/rank = 0.04*3/1=.12, .05*3/2=.075, .06*3/3=.06 -> running min from the top gives .06 each
    p = np.array([0.04, 0.05, 0.06])
    _, q = stats.fdr_bh(p, alpha=0.1)
    np.testing.assert_allclose(q, [0.06, 0.06, 0.06], atol=1e-15)


def test_fdr_bh_q_monotone_in_sorted_p_random():
    rng = np.random.default_rng(6)
    p = rng.random((20, 30))
    p[rng.random(p.shape) < 0.1] = np.nan
    mask, q = stats.fdr_bh(p, alpha=0.1)
    assert p.shape == q.shape == mask.shape  # shape preserved for 2-D maps
    ok = ~np.isnan(p)
    order = np.argsort(p[ok])
    qs = q[ok][order]
    assert np.all(np.diff(qs) >= -1e-15)
    assert np.all(q[ok] >= p[ok] - 1e-15) and np.all(q[ok] <= 1.0)
    assert not mask[~ok].any() and np.isnan(q[~ok]).all()
    np.testing.assert_array_equal(mask[ok], q[ok] <= 0.1)


def test_fdr_all_nan():
    mask, q = stats.fdr_bh(np.full(5, np.nan))
    assert not mask.any() and np.isnan(q).all()


# Autocorrelation -------------------------------------------------------------------------------
def test_lag1_autocorr_recovers_phi():
    rng = np.random.default_rng(7)
    phi, n = 0.6, 4000
    e = rng.normal(size=n)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    assert stats.lag1_autocorr(x[:, None])[0] == pytest.approx(phi, abs=0.05)


def test_autocorr_correction_never_deflates_variance():
    rng = np.random.default_rng(8)
    y = rng.normal(size=(40, 200))
    t = np.arange(40.0)
    raw = stats.trend(y, t, autocorr=False)
    cor = stats.trend(y, t, autocorr=True)
    assert np.all(cor["p"] >= raw["p"] - 1e-12)  # only positive rho inflates; never makes p smaller


# 6. Synthetic field with known truth -----------------------------------------------------------
def make_field(seed, n_years=40, ny=24, nx=45, trend=0.04, phi=0.3, sd=0.5):
    """West third +trend, east third -trend, middle null; monthly data with a seasonal cycle,
    AR(1) annual noise and a NaN block. Returns (monthly DataArray, truth dict)."""
    import xarray as xr

    rng = np.random.default_rng(seed)
    time = np.arange(np.datetime64("1984-01", "M"), np.datetime64("1984-01", "M") + np.timedelta64(n_years * 12, "M"))
    year_idx = np.repeat(np.arange(n_years), 12)
    month_idx = np.tile(np.arange(12), n_years)
    t_years = year_idx + month_idx / 12.0

    true_slope = np.zeros(nx)
    true_slope[: nx // 3] = trend
    true_slope[-(nx // 3):] = -trend
    true_slope = np.broadcast_to(true_slope, (ny, nx))

    # AR(1) annual noise, stationary start
    ann = np.zeros((n_years, ny, nx))
    ann[0] = rng.normal(scale=sd, size=(ny, nx))
    for i in range(1, n_years):
        ann[i] = phi * ann[i - 1] + rng.normal(scale=sd * np.sqrt(1 - phi**2), size=(ny, nx))
    season = 5.0 * np.sin(2 * np.pi * month_idx / 12.0)
    data = (
        10.0
        + season[:, None, None]
        + true_slope[None] * t_years[:, None, None]
        + ann[year_idx]
        + rng.normal(scale=0.3, size=(n_years * 12, ny, nx))
    )
    nan_block = np.zeros((ny, nx), bool)
    nan_block[:5, 15:25] = True  # inside the null middle third
    data[:, nan_block] = np.nan
    da = xr.DataArray(
        data,
        dims=("time", "lat", "lon"),
        coords={"time": time.astype("datetime64[ns]"), "lat": np.linspace(30, 49, ny), "lon": np.linspace(-120, -75, nx)},
        name="synthetic",
    )
    return da, {"slope": true_slope, "nan_block": nan_block, "nx": nx}


def test_synthetic_field_recovers_opposing_trends():
    from resource_trends import preprocess

    da, truth = make_field(seed=11)
    annual = preprocess.annualize(da, how="mean", min_count=10)
    y = annual.values.reshape(annual.sizes["year"], -1)
    t = annual["year"].values.astype(float)
    r = stats.trend(y, t)
    slope = r["slope"].reshape(truth["slope"].shape)
    p = r["p"]
    mask, _ = stats.fdr_bh(p, alpha=0.10)
    mask = mask.reshape(slope.shape)
    nx = truth["nx"]
    west, mid, east = (slice(0, nx // 3), slice(nx // 3, nx - nx // 3), slice(nx - nx // 3, nx))
    valid = ~truth["nan_block"]

    # NaN block stays NaN, everything else is finite
    assert np.isnan(slope[truth["nan_block"]]).all()
    assert np.isfinite(slope[valid]).all()

    for sl, sign in ((west, +1), (east, -1)):
        s = slope[:, sl]
        assert s.mean() == pytest.approx(sign * 0.04, abs=0.005)
        detected = mask[:, sl]
        assert detected.mean() > 0.9  # high power where the trend is real
        assert (np.sign(s[detected]) == sign).all()  # and always the correct sign
    # BH controls the false fraction of DISCOVERIES (~alpha), not the false-positive rate among null
    # pixels: with 2/3 of the field truly trending, some null pixels are rightly let through.
    false_disc = mask[:, mid][valid[:, mid]].sum()
    assert false_disc / mask.sum() < 0.15
    # sign of regional mean slopes is opposite -> the "opposing trends" case works
    assert slope[:, west].mean() > 0 > slope[:, east].mean()


# 7. Pure-null field: false-positive rates ------------------------------------------------------
def _ar1_null(seed, phi, n=40, k=4000):
    rng = np.random.default_rng(seed)
    e = rng.normal(size=(n, k))
    x = np.zeros((n, k))
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + np.sqrt(1 - phi**2) * e[i]
    return x


NULL_SEEDS = (100, 101, 102, 103, 104)

# MEASURED (5 seeds x 4000 null pixels, n=40 annual values, alpha=0.05 two-sided; FDR alpha=0.10):
#   AR(1) phi | raw FPR | autocorr-corrected FPR | fraction of pixels significant after BH-FDR
#   0.0       | 4.64%   | 3.93%                  | 0.00%
#   0.3       | 13.4%   | 6.8%                   | 0.03%
#   0.6       | 30.0%   | 9.0%                   | 0.50%
# Known limitation: with phi=0.6 the corrected FPR (9.0%) is still well above the nominal 5%, because
# lag-1 autocorrelation is underestimated (biased low) from only ~40 values. The correction removes
# most of the inflation (30% -> 9%) but not all of it. FDR still leaves ~no false pixels.
# Thresholds below sit a little above the measured values to absorb seed noise.


def _fpr(phi):
    t = np.arange(40.0)
    raw, cor, fdr = [], [], []
    for s in NULL_SEEDS:
        x = _ar1_null(s, phi)
        r_raw = stats.trend(x, t, autocorr=False)
        r_cor = stats.trend(x, t, autocorr=True)
        raw.append((r_raw["p"] < 0.05).mean())
        cor.append((r_cor["p"] < 0.05).mean())
        fdr.append(stats.fdr_bh(r_cor["p"], alpha=0.10)[0].mean())
    return float(np.mean(raw)), float(np.mean(cor)), float(np.mean(fdr))


def test_null_field_white_noise_is_near_nominal():
    raw, cor, fdr = _fpr(0.0)
    assert 0.035 < raw < 0.06  # measured 4.6%
    assert cor <= raw + 1e-12  # correction never makes things worse (measured 3.9%)
    assert fdr < 0.002  # measured 0.0%


def test_null_field_strong_autocorrelation_correction_helps():
    raw, cor, fdr = _fpr(0.6)
    assert raw > 0.25  # measured 30.0%: the uncorrected test is badly miscalibrated
    assert cor < raw - 0.15  # measured gap 21 points
    assert cor < 0.11  # measured 9.0%, still above nominal 5% (see limitation note)
    assert fdr < 0.01  # measured 0.5%
