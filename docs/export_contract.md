# Export contract v1.0 (for the front end)

Static files under `export/<region>/`, built by `scripts/build_export.py <region>` (from cached data;
~3.5 min for CONUS, 730 files, ~97 MB). Every JSON file is checked against the schemas in
`src/resource_trends/export.py` (`validate_export`); `tests/test_export.py` validates the real export.
No server is needed: serve the directory statically.

## Entry point: `catalog.json`
- `region`: id, name, bbox, land-mask path, analysis grid, named `subregions` (boxes).
- `period`, `method`, `disclaimers` (no forecasts; reanalysis labelled; proxies not generation).
- `variables[]`: name, long_name, theme (hydrology / cryosphere / atmospheric_dynamics /
  atmospheric_chemistry), resource (solar / wind / hydro / none), audience, units, aggregation,
  relative, primary, adverse, provider, dataset, product_type, status, caveats, method, and
  - `annual` and `seasons.{DJF,MAM,JJA,SON}` entries (SWE annual only), each with:
    `trend_nc`, `trend_png`, `summary`, `period`, `subregions` (mean change, area significant up/down),
    `legend`, and for annual only `pixel_series`.
- `files`: run_all, narrative, portfolio, alerts, validation.

## Map overlay: `<var>[.<season>].trend.png` + `legend`
- RGBA, north-up, one pixel per grid cell; place it with `legend.bounds` {south, north, west, east}
  (cell edges, degrees). Use nearest-neighbour scaling to keep cells crisp.
- Colour = `legend.field` (`pct_change_per_decade` for ratio-scale variables, else `slope_per_decade`)
  on a diverging ramp `colors_neg_to_pos` from `vmin` to `vmax` (symmetric, 98th percentile of |value|),
  neutral grey at zero. `positive_color` says which pole an increase gets: "blue" for water variables
  (wetter = blue), "red" otherwise.
- Alpha: 255 = FDR-significant, 89 (`nonsignificant_alpha` 0.35) = not significant, 0 = no data /
  outside the region. Stippling, if wanted, can be drawn from `significant` in `trend_nc`.

## Click-for-series: `pixel_series/<var>/<tile>.json`
Annual values (the aggregate the trend uses) for every valid cell, in 5-degree tiles named
`{floor(lat/5)*5:+06.1f}_{floor(lon/5)*5:+07.1f}.json`, e.g. `+035.0_-100.0.json`. Each tile:
`{variable, units, years[], tile{south, west, size_deg}, cells[{lat, lon, values[]}]}`; null = missing.

## Per-variable numbers: `<var>[.<season>].summary.json`
Regional trend (slope, % per decade, p, rho1, annual series), area fractions significant up/down,
`opposing_trend_score` (read together with the significant area), `coverage_score`, breakpoint check,
start-year sensitivity (+/-5 years), provider/period/method, caveats, notes.

## Other files
- `portfolio.json` / `portfolio.nc`: cross-resource correlations (regional + per cell), joint-low
  frequency vs independent expectation, list of joint-low months, per-resource trend cards.
- `alerts.json` / `<var>.alert.nc`: latest-month anomaly alerts, labelled "anomaly, not forecast",
  with data month and latency (hydrology sources lag by years; show it).
- `validation.json` / `validation.csv` / `validation_solar_3way.csv`: station comparison.
- `narrative.json`: sentences, each with the `numbers` it was built from and its `source` file.
  Show these verbatim; do not paraphrase into stronger claims.
- `run_all.json`: index of every trend run.
