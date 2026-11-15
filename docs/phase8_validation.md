# Phase 8: validation against NOAA station data, CONUS

`validate.run("conus")` -> `export/conus/validation.json` / `validation.csv`; solar three-way check
in `export/conus/validation_solar_3way.csv`. Run 2026-11-15. Grid value = nearest grid cell with data
(distance recorded; 0.02-0.28 deg). Metrics: bias and RMSE (model minus obs), r of monthly values,
r_anom of deseasonalized + detrended monthly anomalies, Theil-Sen trend of annual means per decade
over the months both have.

## Sources (verified 2026-11-15)
| Service | Key? | Used for | Result |
|---|---|---|---|
| NCEI Access Data Service v1, `global-summary-of-the-month` | none | TAVG (degC), PRCP (mm), 12 first-order airport stations | 200 OK, 1981-01..2026-10 (latency ~2 weeks), station names/locations returned and matched |
| NCEI CDO API v2 (`cdo-web/api/v2`) | token | not used | `400 "Token parameter is required."` Token page: https://www.ncdc.noaa.gov/cdo-web/token |
| USCRN `products/monthly01/` text files | none | SOLRAD_MONTHLY_AVG (MJ m-2 day-1 -> W m-2 x 11.574), 15 stations (first per state) | records start 2002-2008 |

## Temperature: POWER/MERRA-2 `T2M` vs 12 GSOM stations, 1981-01..2026-09
- Monthly r 0.964-0.998; anomaly r 0.79-0.97 (lowest: Los Angeles, a coastal station in a 0.5-deg cell).
- Bias mostly -1 to -2.5 degC (cell-average vs airport station; cells include higher, cooler terrain);
  Salt Lake City -3.9 degC (cell spans the Wasatch). Dodge City (flat terrain) +0.2.
- **Trends agree**: station 0.04-0.53, grid 0.08-0.50 degC/decade; |difference| median ~0.1, largest
  New York +0.21 (grid warms faster than Central Park), Seattle -0.15, Phoenix +0.14, LA +0.13.
- **Alert check, September 2026** (gridded: strong warm alert, Southeast/Plains): station
  trend-adjusted percentiles: Dallas 100, Dodge City 92, LA 90, Raleigh 77, Atlanta 77, Chicago 60,
  Phoenix 47, Minneapolis 43, Salt Lake 23, NYC 10, Seattle 0, Pendleton 0. Pattern corroborated
  (warm south and plains, cold northwest); the regional "strong alert" reflects the area-weighted
  balance of a warm south.

## Precipitation: nClimGrid vs the same stations, 1981-01..2022-09 (NOT independent)
nClimGrid is interpolated from station networks that include these stations; this is a consistency
check only.
- Monthly r 0.75-0.97. Biases from -11 to +48 mm/month; large relative biases where the 0.25-deg
  cell includes mountains (Pendleton +118%, Salt Lake +43%).
- Trends of monthly-mean precipitation (mm/month per decade) differ by up to +/-3.5 (NYC, Seattle):
  point vs cell precipitation trends differ substantially. Treat single-cell precipitation trends with care.
- **Alert check, September 2022** (gridded: strong dry alert, Plains/Pacific NW): Seattle 0,
  Minneapolis 10, Dallas 17, Pendleton 20, Atlanta 30 (dry), but Dodge City 90, LA 87, Phoenix 80
  (wet, monsoon). Only partly corroborated at stations.

## Solar: MERRA-2 `SWGDN` vs 15 USCRN reference stations (independent)
- Monthly r 0.86-0.99; anomaly r 0.45-0.83.
- **MERRA-2 is too bright: +10 to +29% (median ~+14%).** Do not use MERRA-2 absolute irradiance for
  yield/capacity-factor numbers; this tool uses trends and anomalies.
- **Trend disagreement, unresolved.** Every USCRN station shows a decline (-2 to -17 W m-2/decade)
  that MERRA-2 does not. Three-way check on common months through 2020 (8 stations with enough data):

| | median trend (W m-2/decade) | median bias vs USCRN |
|---|---|---|
| USCRN | -6.3 | - |
| MERRA-2 | -1.5 | +13.6% |
| CERES SYN1deg (satellite, independent) | +0.9 | +4.3% |

  The independent satellite product does not show the station decline (it is closer to MERRA-2 and of
  opposite sign). Two readings: (a) the stations see a real local dimming that both gridded products
  miss, or (b) station instrument drift. (b) is plausible but NOT verified here (no USCRN sensor
  metadata checked). Report the solar trend as "no robust trend; sources disagree", consistent with
  Phase 4.

## Summary
| Variable | Agreement in variability | Agreement in trend | Absolute bias |
|---|---|---|---|
| Temperature | excellent | good (~0.1 degC/decade) | cooler by 1-2 degC (terrain) |
| Precipitation | good (not independent) | weak at point scale | terrain-dependent |
| Solar | good | **disputed** (stations decline, satellite does not) | MERRA-2 ~14% too bright |

Not done: wind (GSOM wind is 10 m and station-siting dependent; no clean comparison chosen), EIA
generation data (stretch goal, needs a key).
