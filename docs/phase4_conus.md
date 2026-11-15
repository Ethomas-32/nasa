# Phase 4: single-variable results, CONUS (sanity record)

Run: `pipeline.run("conus", var, 1981, 2020)`, annual aggregate per variables.yaml, outputs in
`export/conus/<var>.trend.nc` and `<var>.summary.json`. Per-pixel Theil-Sen + Mann-Kendall
(tie-corrected, lag-1 autocorrelation adjusted), BH-FDR alpha 0.10, **CONUS land mask applied**
(nClimGrid footprint; cells >= 50% US land). Run date 2026-11-15.

## Results (masked)

| Variable | Provider | CONUS regional trend 1981-2020 | p | Area sig. up / down | Start 1986 regional | Breakpoint |
|---|---|---|---|---|---|---|
| air_temp_2m | POWER (MERRA-2) | +0.277 degC/decade | 0.003 | 0.68 / 0.00 | +0.236 | none (p=0.91) |
| solar_irradiance | MERRA-2 SWGDN | -0.04 W m-2/decade (-0.02 %/dec) | 0.95 | 0.00 / 0.00 | -0.65 | none (p=0.28) |
| aerosol_optical_depth | MERRA-2 TOTEXTTAU | -0.0105 /decade (-7.1 %/dec) | 0.036 | 0.00 / 0.57 | -0.0066 | none (p=0.23) |
| wind_speed_50m | POWER (MERRA-2) | +0.005 m/s/decade (+0.09 %/dec) | 0.68 | 0.02 / 0.02 | +0.020 | none |
| wind_power_density | derived (daily v^3) | +0.80 W m-2/decade (+0.49 %/dec) | 0.60 | 0.02 / 0.01 | +2.03 | none |
| surface_pressure | POWER (MERRA-2) | +0.015 hPa/decade | 0.79 | 0.00 / 0.00 | -0.04 | none |
| snow_water_equivalent | Daymet (peak monthly-mean) | -2.50 mm/decade (-6.9 %/dec) | 0.074 | 0.00 / 0.06 | -1.16 | none (p=0.83) |
| runoff | TerraClimate | +6.2 mm/decade (+3.5 %/dec) | 0.38 | 0.00 / 0.00 | +9.4 | none |
| soil_moisture | TerraClimate | +0.40 mm/decade (+0.75 %/dec) | 0.71 | 0.00 / 0.03 | +0.94 | none |
| pdsi | TerraClimate | +0.007 /decade | 0.97 | 0.00 / 0.00 | +0.19 | none |
| precipitation | nClimGrid | +5.4 mm/decade (+0.7 %/dec) | 0.69 | 0.00 / 0.00 | +15.6 | none (p=0.45) |

Sub-regional area-weighted mean trend (%/decade for relative variables, units/decade otherwise) and
fraction of the sub-region significant (FDR) up/down:

| Variable | Southwest | Northeast | Pacific NW | Southeast | N. Rockies | Plains |
|---|---|---|---|---|---|---|
| air_temp_2m (degC/dec) | +0.45 (0.99 up) | +0.37 (0.96 up) | +0.23 (0.52 up) | +0.33 (0.95 up) | +0.18 (0.28 up) | +0.19 (0.35 up) |
| aerosol_optical_depth | -6.9 (0.43 dn) | -14.0 (1.00 dn) | +1.8 | -11.2 (1.00 dn) | +0.2 | -6.4 (0.48 dn) |
| snow_water_equivalent | -7.4 (0.11 dn) | -0.6 | -12.7 (0.14 dn) | -5.9 (0.13 dn) | -1.0 (0.07 dn) | +0.1 |
| precipitation | -7.7 | +2.9 | -1.8 | +1.7 | +1.1 | +0.6 |
| runoff | -8.1 | +5.6 | -1.6 | +2.4 | +3.2 | +0.8 |
| soil_moisture | -14.7 (0.22 dn) | +1.7 | -2.6 | +1.8 | -0.7 | -1.7 |
| pdsi (/dec) | -0.70 | +0.59 | -0.45 | +0.34 | +0.12 | +0.16 |
| wind_power_density | +0.4 (0.08 dn) | +0.2 | +0.1 | +0.6 | +2.1 (0.04 up) | +1.1 |

Boxes: Southwest 31-37N 120-103W; Northeast 38-47.5N 85-67W; Pacific NW 42-49N 125-116W;
Southeast 29-36N 92-76W; N. Rockies 42-49N 116-104W; Plains 35-48N 104-95W.

Precipitation was not cross-checked against TerraClimate `ppt` (would need another ~25 min stream).

## Sanity checks
- **Temperature**: broad, significant warming (+0.28 degC/decade, 68% of area significant, none
  cooling), fastest in the Southwest. Close to commonly cited US warming since ~1980 (general
  knowledge, not re-verified here). End-to-end check that pipeline, units and per-decade scaling work.
- **Surface pressure**: no trend (negative control).
- **Southwest drying / Northeast wetting (checked, not assumed)**: the pattern is present IN SIGN in
  every hydro variable (precipitation -7.7 vs +2.9 %/dec; runoff -8.1 vs +5.6 %/dec; soil moisture -14.7 vs +1.7; PDSI -0.70 vs +0.59),
  but it is statistically significant only for Southwest soil moisture (22% of the sub-region).
  Annual precipitation, runoff and PDSI have NO FDR-significant pixels anywhere: interannual variability is large
  relative to 40 years, and FDR over ~8000 spatially correlated 0.25-deg cells is strict. This must
  be reported as "consistent direction, not established at pixel level", not as a detected trend.
- **Snow**: declines everywhere snow matters, strongest in the Pacific Northwest (-12.7 %/dec),
  significant in 6-14% of snowy sub-regions; CONUS regional p=0.074 (not significant at 0.05).
- **Solar: no robust CONUS trend.** Cross-check 2001-2020 (unmasked) against CERES SYN1deg:
  MERRA-2 -0.59 %/decade (p=0.22, 12% of area sig. down) vs CERES +0.37 %/decade (p=0.42, none
  significant). Detrended annual series correlate 0.94; MERRA-2 is 6.3% brighter (12.1 W m-2). The
  sign is product-dependent; MERRA-2's local declines are not corroborated.
- **Aerosol** declines strongly in the East (Northeast -14 %/dec, Southeast -11 %/dec, 100% of area
  significant), consistent with the documented US aerosol reduction; the 1991 Pinatubo spike is
  visible in the regional series and Theil-Sen is robust to it. Open question, NOT tested: AOD falls
  while all-sky solar is flat. Check clear-sky (`SWGDNCLR`) / cloud before stating any cause.
- **Wind**: no robust trend; 1-9% of any sub-region significant. `opposing_trend_score` is high but
  meaningless at such small significant area; always read it with `area_frac_sig_up + down`.

## Issues found and fixed during Phase 4
1. **Pettitt false alarm.** On the raw regional series Pettitt flagged temperature (1998, p=0.0002);
   a smooth trend always yields a Pettitt change point. Now tested on the Sen-detrended series
   (`test_breakpoint_is_not_fooled_by_a_smooth_trend`, `test_breakpoint_flags_a_spliced_series`).
2. **Daymet SWE 30x too small.** The loader trusted Daymet's "monthly total / sum over days"
   metadata and divided by days-in-month. Checked against daymet-daily-na: the monthly value is the
   daily MEAN. Fixed; cache corrected; see docs/sources.md finding 6.
3. **Region = bounding box was wrong.** CONUS statistics included ocean, southern Canada and
   northern Mexico (coverage was always 1.00). Added a CONUS land mask (nClimGrid footprint,
   `data/masks/`), applied in the pipeline. Pre-mask temperature was +0.258 degC/decade, masked +0.277.
