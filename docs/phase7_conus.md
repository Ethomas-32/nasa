# Phase 7: anomaly alerts, CONUS (ANOMALY, NOT FORECAST)

`alerts.run("conus", today=2026-11-15)` -> `export/conus/alerts.json` + `<var>.alert.nc`
(per-cell percentile, raw percentile, anomaly, value). CONUS land mask applied.

## Method
- Latest month = the last month with any data for that variable (each variable has its own).
- Baseline = the same calendar month in the 30 previous years (cells need >= 15 valid years),
  detrended with Theil-Sen. The latest month's residual is ranked among the baseline residuals
  (empirical percentile, ties count half). The raw (not detrended) percentile is reported too.
- Adverse direction per variable in variables.yaml (`adverse`): low solar/wind/water/snow, high
  temperature and aerosol, both for pressure.
- Status: **strong alert** = regional (area-weighted) percentile in the adverse 5% tail;
  **alert** = adverse 10% tail; **local alert** = regional mean not extreme but >= 20% of the area in
  the adverse 10% tail; otherwise none. Sub-regions (regions.yaml) list where the adverse cells are.
- Resolution: with 30 baseline years a percentile moves in ~3.3-point steps; "strong alert" means the
  latest month is the most extreme of 31 (after detrending).
- Tested on synthetic data (tests/test_alerts.py): extreme months flagged, on-trend months under
  strong trends NOT flagged (raw percentile would say "record"), same-calendar-month comparison,
  short baselines rejected, adverse direction respected.

## Latency (measured 2026-11-15)
| Source | Latest month | Days behind month end |
|---|---|---|
| MERRA-2 (solar, aerosol), POWER (wind, temperature, pressure) | 2026-09 | 46 |
| nClimGrid on Planetary Computer (precipitation) | 2022-09 | 1507 |
| TerraClimate on Planetary Computer (runoff, soil moisture, PDSI) | 2021-12 | 1780 |
| Daymet on Planetary Computer (SWE) | 2020-12 | 2145 |

Hydrology alerts are therefore historical illustrations, not current conditions. Agreed with the
user: state this when presenting. Current hydro alerts would need a near-real-time source
(e.g. POWER `PRECTOTCORR`, unverified for this use).

## Results
| Variable | Month | Status | Regional pct (trend-adj. / raw) | Area in adverse 10% tail | Where (share of sub-region) |
|---|---|---|---|---|---|
| air_temp_2m | 2026-09 | strong alert (warm) | 96.7 / 100.0 | 0.29 | Southeast 71%, Plains 42%, Southwest 23% |
| solar_irradiance | 2026-09 | local alert (low) | 26.7 / 3.3 | 0.25 | Plains 61%, Southwest 60%, Pacific NW 10% |
| precipitation | 2022-09 | strong alert (dry) | 0.0 / 0.0 | 0.20 | Plains 46%, Pacific NW 31%, Southeast 16% |
| pdsi | 2021-12 | alert (drought) | 10.0 / 10.0 | 0.35 | Plains 80%, N. Rockies 66%, Northeast 23% |
| snow_water_equivalent | 2020-12 | none | 33.3 / 3.3 | 0.10 | |
| runoff | 2021-12 | none | 40.0 / 53.3 | 0.12 | |
| soil_moisture | 2021-12 | none | 53.3 / 46.7 | 0.16 | |
| wind_power_density | 2026-09 | none | 33.3 / 6.7 | 0.12 | |
| wind_speed_50m | 2026-09 | none | 46.7 / 20.0 | 0.14 | |
| aerosol_optical_depth | 2026-09 | none (unusually LOW, not adverse) | 0.0 / 0.0 | 0.00 | |
| surface_pressure | 2026-09 | none | 40.0 / 53.3 | 0.12 | |

## Not verified
These alerts have not been checked against independent reports (e.g. NOAA monthly climate
summaries). Do that for at least the temperature and precipitation alerts in Phase 8 before
presenting them as fact. Trend-adjusted and raw percentiles can differ a lot (solar: 26.7 vs 3.3),
which is intended: the trend-adjusted one asks "unusual for today's climate?", the raw one
"unusual versus history?"; show both.
