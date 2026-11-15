# Verified data sources (Phase 2)

All facts below were obtained by live requests on **2026-11-14** (scripts were throwaway probes; the
numbers are the evidence). Anything not in this file is NOT verified. Re-check "latest month" values
before relying on them; they move.

## Summary table

| Provider | Dataset / store | Variable (our name) | Native name, units | Grid | Time coverage (checked) | Access |
|---|---|---|---|---|---|---|
| merra2 | Earthdata `M2TMNXRAD` v5.12.4 | solar_irradiance | `SWGDN`, W m-2 | 0.5 x 0.625 deg (361x576) | 1980-01 to 2026-09 | `earthaccess` (login OK, GES DISC approved) |
| merra2 | Earthdata `M2TMNXAER` v5.12.4 | aerosol_optical_depth | `TOTEXTTAU` (AOT 550 nm), unitless | same | 1980-01 to 2026-09 | `earthaccess` |
| nasa_power | `s3://nasa-power/merra2/temporal/power_merra2_monthly_temporal_utc.zarr` | wind_speed_50m, air_temp_2m, surface_pressure | `WS50M` m/s, `T2M` C, `PS` **hPa** | 0.5 x 0.625 deg | 1981-01 to 2026-09 | anonymous S3 (s3fs), no key |
| nasa_power | `s3://nasa-power/syn1deg/temporal/power_syn1deg_monthly_temporal_utc.zarr` | solar_irradiance (cross-check only) | `ALLSKY_SFC_SW_DWN`, W m-2 | 1 deg (180x360) | **2001-01** to 2026-08 | anonymous S3 |
| terraclimate | Planetary Computer `terraclimate`, asset `zarr-abfs` | runoff, precipitation, soil_moisture, pdsi, snow_water_equivalent | `q`, `ppt`, `soil`, `pdsi`, `swe` (all mm except pdsi unitless) | 1/24 deg (4320x8640) | 1958-01 to **2021-12** | pystac-client + planetary-computer signing |
| nclimgrid | PC `noaa-nclimgrid-monthly`, one COG per month, asset `prcp` | precipitation (CONUS) | `prcp`, mm, float32, NaN nodata | 1/24 deg, EPSG:4326 | 1895-01 to **2022-09** | PC STAC items |
| daymet | PC `daymet-monthly-na`, asset `zarr-abfs` | snow_water_equivalent (CONUS) | `swe`, mm ("monthly total snow water equivalent") | 1 km Lambert conformal conic (x 7814, y 8075), lat/lon are 2-D | 1980-01 to **2020-12** | pystac-client + signing |

## Findings that change the plan

1. **POWER solar is a spliced product; do not use the POWER API 1984-present series for trends.**
   The monthly SRB store has ALLSKY_SFC_SW_DWN 1984-01..2000-12 and SYN1deg has 2001-01..; they do not
   overlap. CONUS annual mean: 1991-2000 = 187.4 W m-2, 2001-2010 = 190.2 (step +2.8 W m-2, 1.5%);
   interannual sd 3.5 before vs 1.5 after. A trend over the splice would partly measure the product
   change. **Decision:** primary solar = MERRA-2 `SWGDN` (single reanalysis, 1980-), cross-check =
   SYN1deg 2001-. Caveat to test in Phase 4: MERRA-2 also assimilates observing systems that changed
   over time (aerosol), so check for discontinuities rather than assume homogeneity.
2. **POWER grid access (open question 2): use the AWS Zarr copy** (option b). The point API works
   (v2.10.0, no key) but is one call per pixel; the regional endpoint needs hyphenated parameter
   names (`latitude-min`, ...) and was not pursued. The Zarr stores are instant to subset. Note the
   Zarr units differ from the API: PS is hPa (API: kPa) and solar is W m-2 (API: kWh m-2 day-1).
   Time axes are pre-allocated to 2029; the last populated month must be found by data, not axis.
3. **Planetary Computer hydrology is stale:** TerraClimate ends 2021-12, Daymet 2020-12, NClimGrid
   2022-09. Consequences: (a) hydro trend period ends 2020/2021; (b) Phase 7 anomaly alerts cannot use
   these for the latest month. Candidates for alerts (unverified): POWER `PRECTOTCORR` (in the merra2
   Zarr, current to 2026-09) and MERRA-2 land diagnostics via earthaccess.
4. **Latency measured:** MERRA-2 monthly and POWER-MERRA-2 meteorology: through 2026-09 (about 6
   weeks behind 2026-11-14). SYN1deg solar: 2026-08. The Zarr axes alone are misleading (see 2).
5. **Candidate common period:** 1981-2020 (wind starts 1981-01; Daymet ends 2020-12). The earlier
   tentative 1984 start came from POWER solar, which we no longer use. Decision pending.
6. **TerraClimate also has `swe`**, so snow water equivalent has a global provider (Africa/global
   runs). **Daymet monthly `swe` semantics (verified empirically 2026-11-15):** the metadata says
   long_name "monthly total snow water equivalent" and `cell_methods: "area: mean time: sum within
   days time: sum over days"`, which suggests a SUM of daily SWE. **It is not.** Comparing
   `daymet-monthly-na` with the mean and sum of `daymet-daily-na` (Jan-Apr 2010):
   Colorado Rockies (-106.0, 39.6) monthly 84.6/106.3/134.0/142.4 = daily MEAN exactly (sum 2622-4273);
   Sierra Nevada (-119.6, 37.8) 150.6/203.3/237.3/288.9 = daily mean; Minnesota (-93, 47)
   53.2/58.1/36.6/0.6 = daily mean. The monthly value is the monthly MEAN SWE (mm = kg m-2) and is
   used as-is. A first loader version trusted the metadata and divided by days-in-month (SWE ~30x
   too small); the error surfaced as an implausible CONUS mean in Phase 4 and the cache was
   corrected by multiplying back by days-in-month. The annual `max` is peak monthly-mean SWE, a
   lower bound on true daily peak SWE. Lesson: verify semantics against data, not only metadata.
7. **MERRA-2 cost:** a global monthly file is 60-84 MB. Full download of one variable (~560 months)
   is ~35 GB, so do not download. Streaming a CONUS subset via `earthaccess.open` + `h5netcdf` works:
   ~10 s per file (3 files in 32 s), so ~1.5 h per variable single-threaded, cached after that.
8. **Wind power density (evaluated Phase 3):** daily store `power_merra2_daily_temporal_utc.zarr`
   has `WS50M` daily from 1981, chunks (5844 days, 15, 15), so the CONUS stream is ~450 MB.
   Kansas/Oklahoma box (35-40N, 102-96W), 2010-2019: monthly mean of daily v^3 / (monthly mean v)^3
   = 1.29 median (5-95%: 1.17-1.51); Sen slope of the annual box mean -0.96 %/yr (monthly cube) vs
   -0.65 %/yr (daily cube), annual-series correlation 0.94. The bias is not a constant factor, so it
   changes trends. **Decision:** `wind_power_density` = 0.5 * rho * monthly mean of daily v^3
   (variable `wind_speed_cubed_50m`). Still below an hourly-based value (not evaluated; the hourly
   store exists but was not opened).

9. **Streaming costs (Phase 3, measured on this connection):** TerraClimate chunks are
   (12 months, 1024, 1024) float64, so a CONUS year reads 4 chunks (~400 MB uncompressed): ~2 min/year
   with other jobs running. Daymet chunks (12, 2000, 2000) float32. MERRA-2 ~1 year/min with 4 worker
   processes. Only the cropped, 0.25-deg block-averaged series is written to disk (~3-10 MB/variable).

## Other facts observed
- Planetary Computer: 139 collections; no key needed, SAS tokens are issued by `planetary_computer.sign`.
- TerraClimate on PC has lowercase names (`pdsi`, not `PDSI`), plus aet, def, pet, srad, tmax, tmin, vap, vpd, ws.
- NClimGrid on PC is COG per month (not Zarr); items also carry `tavg`, `tmax`, `tmin`.
- Earthdata: MERRA-2 collections found by short name: M2TMNXAER, M2T1NXAER, M2TMNXSLV, M2T1NXSLV, M2TMNXRAD (all v5.12.4, from 1980-01).
- MERRA-2 June 2020 CONUS mean SWGDN from the streamed subset: 290 W m-2 (plausible for June).

## Not verified
- NOAA station endpoints (Phase 8). EIA data (stretch). GDELT (Phase 9+).
- POWER `PRECTOTCORR` quality vs gauges; MERRA-2 land/soil variables for alerts.
- CONUS bounding box vs any boundary dataset.
