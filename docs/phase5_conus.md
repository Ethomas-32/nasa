# Phase 5: three-resource run, CONUS, annual + seasonal

`pipeline.run_all("conus", 1981, 2020)` -> `export/conus/` (56 runs, 0 failures, ~2 min from cache;
index in `export/conus/run_all.json`). CONUS land mask applied. Snow water equivalent is annual only
(`seasonal: false`). DJF for POWER-based variables starts 1982 (the record begins 1981-01, so the
first full winter is Dec 1981-Feb 1982); this is recorded in each summary's notes.

CONUS regional trend (%/decade for relative variables, otherwise units/decade), regional p, and
cos-lat area fraction of FDR-significant pixels up / down:

| Variable | ANN | DJF | MAM | JJA | SON |
|---|---|---|---|---|---|
| **Solar** solar_irradiance (%) | -0.02 (p .95) 0/0 | +0.14 (.86) 0/0 | -0.29 (.47) 0/0 | -0.17 (.61) 0/0 | +0.39 (.37) 0/0 |
| aerosol_optical_depth (%) | -7.0 (.036) 0/.57 | -10.4 (.001) 0/.84 | -5.6 (.003) 0/.58 | -6.5 (.032) 0/.51 | -10.4 (.004) 0/.65 |
| **Wind** wind_speed_50m (%) | +0.09 (.68) .02/.02 | +0.38 (.36) 0/.01 | +0.01 (.94) 0/0 | -0.32 (.29) 0/.01 | +0.14 (.55) .04/.02 |
| wind_power_density (%) | +0.49 (.60) .02/.01 | +1.37 (.37) 0/0 | -0.54 (.76) 0/0 | -0.71 (.41) 0/.01 | +1.05 (.27) .02/.01 |
| air_temp_2m (degC) | +0.28 (.003) .68/0 | +0.35 (.029) 0/0 | +0.14 (.18) .08/0 | +0.32 (.002) .40/0 | +0.35 (.003) .40/0 |
| surface_pressure (%) | +0.00 (.79) 0/0 | -0.01 (.37) 0/0 | +0.02 (.11) 0/0 | -0.01 (.23) 0/.30 | +0.00 (.79) 0/0 |
| **Hydro** runoff (%) | +3.5 (.38) 0/0 | +0.9 (.82) 0/0 | +3.3 (.35) 0/0 | +3.7 (.33) 0/0 | -1.7 (.66) 0/0 |
| precipitation (%) | +0.7 (.69) 0/0 | +2.5 (.35) 0/0 | +2.2 (.25) 0/0 | +1.5 (.38) 0/0 | -2.0 (.23) 0/0 |
| soil_moisture (%) | +0.8 (.71) 0/.03 | -0.8 (.73) 0/.04 | +1.3 (.22) 0/.03 | +2.0 (.37) 0/.03 | +0.6 (.89) 0/.03 |
| pdsi (/dec) | +0.01 (.97) 0/0 | +0.07 (.81) 0/0 | +0.10 (.67) 0/0 | +0.06 (.71) 0/0 | -0.06 (.79) 0/0 |
| snow_water_equivalent (%) | -6.9 (.074) 0/.06 | | | | |

(`wind_speed_cubed_50m`, the input to power density, is in run_all.json and tracks power density.)

## Reading the table
- **CONUS-wide numbers hide regional opposites** (Phase 4 sub-region table): hydro variables dry in
  the Southwest and wet in the Northeast, which nearly cancels in the CONUS mean. The per-pixel maps
  in `<var>[.<season>].trend.nc` are the primary output, not this regional column.
- **Robust signals**: warming (annual, JJA, SON; DJF warms fastest regionally, +0.35 degC/decade,
  p=0.03, but no pixel survives FDR because winter variability is large); aerosol decline in every
  season (strongest in DJF and SON, 84% and 65% of the area); snow decline (regionally, Phase 4).
- **Not robust**: solar and wind in every season; seasonal hydro (at most 4% of the area significant).
- **Unexplained, flagged**: JJA surface pressure has 30% of the area significant DOWN with a
  negligible regional trend (-0.01 %/decade, p=0.23). Not investigated; could be real circulation
  change or a reanalysis artifact. Do not interpret without checking.

## Common period
1981-2020 for everything (open question 3, agreed with the user). Wind/temperature/pressure DJF
use 1982-2020 as explained above. Hydro caches extend to 2021; MERRA-2 and POWER to 2026-09.
