# Phase 4: single-variable results, CONUS (sanity record)

Run: `pipeline.run("conus", var, 1981, 2020)`, annual aggregate per variables.yaml, outputs in
`export/conus/<var>.trend.nc` and `<var>.summary.json`. Per-pixel Theil-Sen + Mann-Kendall
(tie-corrected, lag-1 autocorrelation adjusted), BH-FDR alpha 0.10. Grid 0.5 x 0.625 deg.
Run date 2026-11-15. Hydrology variables are pending (cache still downloading).

| Variable | Provider | CONUS regional trend 1981-2020 | p | Area sig. up / down | Start 1986 regional | Breakpoint (detrended Pettitt) |
|---|---|---|---|---|---|---|
| air_temp_2m | POWER (MERRA-2) | +0.258 degC/decade | 0.0002 | 0.65 / 0.00 | +0.227 | none (p=1) |
| solar_irradiance | MERRA-2 SWGDN | -0.10 W m-2/decade (-0.05 %/dec) | 0.89 | 0.00 / 0.00 | -0.54 | none (p=0.49) |
| wind_speed_50m | POWER (MERRA-2) | +0.010 m/s/decade (+0.17 %/dec) | 0.54 | 0.05 / 0.03 | +0.019 | none (p=0.80) |
| wind_power_density | derived (daily v^3) | +0.64 W m-2/decade (+0.31 %/dec) | 0.63 | 0.02 / 0.01 | +2.36 | none (p=0.80) |
| surface_pressure | POWER (MERRA-2) | -0.0007 hPa/decade | 1.0 | 0.00 / 0.00 | -0.05 | none |

## Sanity checks
- **Temperature** behaves as expected: broad, significant warming of ~0.26 degC/decade with no
  significant cooling anywhere. This is close to the commonly cited US warming rate since ~1980
  (stated from general knowledge, not re-verified here) and is the end-to-end check that the
  pipeline, units and per-decade scaling are right.
- **Surface pressure** shows no trend, as it should (a negative control).
- **Solar: no robust CONUS trend.** Cross-check 2001-2020 against CERES SYN1deg (independent,
  satellite-derived, 1 deg): MERRA-2 -0.59 %/decade (p=0.22, 12% of area significant DOWN) vs CERES
  +0.37 %/decade (p=0.42, 0% of area significant). Detrended annual CONUS series correlate 0.94, so
  interannual variability agrees; MERRA-2 is 6.3% brighter on average (12.1 W m-2). The trend sign
  depends on the product and neither is significant, so MERRA-2's local "significant decline"
  patches are NOT corroborated and must carry that caveat in the export/narrative.
- **Wind:** CONUS-scale wind and power density trends are small and not significant; only 2-8% of
  the area passes FDR. The `opposing_trend_score` is high (0.67-0.90) but meaningless at such small
  significant area; it must always be read together with `area_frac_sig_up + down`.

## Method issue found and fixed
Pettitt on the raw regional series flagged a "breakpoint" in temperature (1998, p=0.0002). That
is an artifact: a smooth trend always produces a Pettitt change point. The pipeline now tests the
Sen-detrended series; a synthetic product splice (+3 units from 2001) is still caught (test
`test_breakpoint_flags_a_spliced_series`) and a pure trend is not (`test_breakpoint_is_not_fooled_by_a_smooth_trend`).

## Still to do in Phase 4
- Precipitation (nClimGrid) check: is the Southwest drying / Northeast wetting pattern present? Check, don't assume.
- Runoff, soil moisture, PDSI, SWE once their caches finish.
