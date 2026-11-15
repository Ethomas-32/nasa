# Phase 6: portfolio (cross-resource) results, CONUS

`portfolio.run("conus", "1981-01", "2020-12")` -> `export/conus/portfolio.json` + `portfolio.nc`.
Primary indices: solar = `solar_irradiance` (MERRA-2), wind = `wind_power_density` (POWER daily v^3),
hydro = `runoff` (TerraClimate). Common grid 0.5 x 0.625 deg (runoff area-averaged onto it), CONUS
land mask, 480 months. Method: Pearson r of detrended, deseasonalized monthly anomalies; p-values
from a t-test with effective sample size (Bretherton et al. 1999). "Low" = below the calendar-month
20th percentile of anomalies; "joint low" = >= 2 of 3 resources low in the same month.

## Method validation (synthetic, tests/test_portfolio.py)
- Shared seasonality + shared trend with independent noise: raw r > 0.9, anomaly r ~ 0.
- Known correlations -0.6, 0, 0.3, 0.7 recovered within 0.03.
- Independent AR(1) pairs (phi=0.7, 480 months): naive t-test false-positive rate 25.3%,
  effective-n test 5.2% (nominal 5%). Measured 2026-11-15.
- Joint lows: independent -> 10.4% (theory 0.104); r=0.95 -> >3x independence; anticorrelated -> ~0.

## Regional (CONUS area-weighted series)
| Pair | r | p (n_eff) | n_eff / n |
|---|---|---|---|
| solar - hydro | **-0.42** | 5e-19 | 404 / 480 |
| solar - wind | +0.19 | 6e-05 | 463 / 480 |
| wind - hydro | +0.11 | 0.018 | 470 / 480 |

Joint-low frequency 11.5% of months vs 10.4% expected if independent (ratio 1.10, 55 months; most
regional joint lows are solar + wind).

## Per grid cell
| Pair | Area-mean r | Area significant + / - (p<0.05, n_eff) |
|---|---|---|
| solar - hydro | -0.36 | 0.00 / **1.00** |
| solar - wind | +0.07 | 0.44 / 0.17 |
| wind - hydro | +0.04 | 0.28 / 0.18 |

Joint-low ratio, area mean 0.95 (frequency 9.9%).

| Sub-region | r(solar, wind) | r(solar, hydro) | r(wind, hydro) | joint-low ratio |
|---|---|---|---|---|
| Southwest | +0.25 | -0.45 | -0.06 | 1.00 |
| Northeast | -0.04 | -0.26 | +0.04 | 0.93 |
| Pacific NW | -0.24 | -0.28 | +0.24 | 0.93 |
| Southeast | +0.07 | -0.37 | +0.14 | 0.99 |
| N. Rockies | +0.00 | -0.34 | -0.00 | 0.89 |
| Plains | +0.17 | -0.40 | -0.01 | 0.96 |

## Reading
- **Solar and hydro are complementary everywhere** in CONUS: months with above-normal sunshine tend
  to have below-normal runoff and vice versa (cloudy/wet vs clear/dry months). Significant in every
  grid cell.
- **Solar-wind co-variability changes sign by region**: positive in the Southwest and Plains (they
  tend to be low together), negative in the Pacific Northwest (they offset). This is the brief's
  "different direction in different places" at the portfolio level.
- **Joint lows occur at about the independent rate** (ratio ~0.9-1.1): the three resources neither
  protect strongly against nor amplify simultaneous shortfalls at monthly scale.

## Limitations (state these in any output)
- Contemporaneous monthly correlation only. Runoff lags precipitation and snowmelt by weeks to months,
  so lagged relationships (e.g. sunny spring, high summer runoff) are not captured. Not tested.
- Resource proxies, not generation; reanalysis/model products; no transmission or storage.
- The 20th-percentile "low" is relative to each calendar month's own distribution of anomalies, so
  it measures unusual shortfalls, not absolute scarcity.
