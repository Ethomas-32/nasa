# Resource Trends

Decision support for renewable-energy providers (solar, wind, hydropower), also useful to farmers:
**is the resource my portfolio depends on changing here, by how much, can I trust the signal, and do my
resources cover for each other?** Per-pixel trend detection with significance testing on NASA and NOAA
Earth-science data, a cross-resource (portfolio) analysis, anomaly alerts, station validation, and a
static web front end (globe + dashboard). Trends and anomalies only; **no forecasts**.

Current coverage: contiguous US (CONUS), 1981-2020. Africa and a global view are configured but not run.

## Contents
- [Quick start: run the demo from a fresh clone](#quick-start-run-the-demo-from-a-fresh-clone)
- [Install the Python package](#install-the-python-package)
- [Rebuild the results](#rebuild-the-results)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)

## Before you clone: get the repo onto the other device
This repository has **no remote yet**. Push it somewhere first, e.g. a new (private) GitHub repo:
```powershell
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```
Then on the other device: `git clone https://github.com/<you>/<repo>.git` and `cd` into it.

**What a clone does NOT contain:** the analysis results (`export/`, ~112 MB) and the downloaded data cache
(`data/cache/`, ~305 MB) are git-ignored. Everything else (code, config, tests, test fixtures, the CONUS land
mask) is in the repo. Pick one of the routes below to get results onto the new device.

| Route | You need | Time |
|---|---|---|
| **A. Copy the prebuilt results** (recommended for a demo) | the demo zip or the `export/` folder from the original machine; Python 3 | ~5 min |
| **B. Rebuild from a copied data cache** | `data/cache/` from the original machine; the Python package | ~10 min |
| **C. Rebuild from scratch** | internet, a free NASA Earthdata login, the Python package | ~4-6 h of downloads (unattended) |

## Quick start: run the demo from a fresh clone
Route A needs **only Python 3** (no packages) and an internet connection in the browser (map libraries,
basemap and globe texture come from the web; all results are local).

1. Get the results onto the new device, either way:
   - **From the demo zip** (13 MB, made on the original machine with `scripts\package_demo.py`, found in
     `dist\resource-trends-demo.zip`): unzip it and copy its `export` folder into the repo root, so you have
     `<repo>\export\index.json` and `<repo>\export\conus\catalog.json`.
   - **Or** copy the whole `export\` folder from the original machine into the repo root.
2. From the repo root, start a static web server:
   ```powershell
   python -m http.server 8000          # macOS/Linux: python3 -m http.server 8000
   ```
3. Open http://localhost:8000/web/ (globe) or http://localhost:8000/web/dashboard.html?region=conus.

Serve the **repo root**, not `web/`: the pages read `../export/<region>/`.
Stop the server with Ctrl+C. (The demo zip on its own also works without a clone: unzip, double-click
`START-DEMO.bat` on Windows or `start-demo.command` on macOS.)

## Install the Python package
Needed for routes B and C, tests, and any change to the analysis. Python 3.10+ (developed on 3.12).

Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,data]"
.\.venv\Scripts\python.exe -m pytest -q          # ~135 tests, ~1-2 min, all offline
```
macOS/Linux:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev,data]"
.venv/bin/python -m pytest -q
```
`.[dev,data]` = core analysis + pytest + data-access libraries (earthaccess, Planetary Computer, Zarr/S3,
rasterio...). The tests use small real fixtures in `tests/fixtures/`; no network or login needed.
One test validates the real CONUS export and is skipped if `export/conus/` is absent.

Below, `python` means the venv interpreter (`.\.venv\Scripts\python.exe` on Windows, `.venv/bin/python`
elsewhere).

## Rebuild the results
### Route B: from a copied data cache (~10 min, no network for the analysis)
Copy `data\cache\` from the original machine into the repo, then:
```powershell
python scripts\build_export.py conus
```
This runs every trend (annual + seasons), the portfolio analysis, alerts, station validation and the export
(PNGs, pixel series, narrative, catalog) and validates every file against the export schema. Station data
for validation is also in the cache (`validation_*.csv`). It may fetch a few new months from NASA POWER or
MERRA-2 if they have been published since; that needs internet (and the Earthdata login for MERRA-2).

### Route C: from scratch (downloads; run unattended)
1. **NASA Earthdata login** (free; needed for MERRA-2 solar and aerosol):
   - Register at https://urs.earthdata.nasa.gov and verify your email.
   - Under *Applications > Authorized Apps > Approve More Applications*, approve
     **NASA GESDISC DATA ARCHIVE** (without this, downloads fail with 401/403).
   - Save the credentials once (prompts for username/password, writes `~/.netrc` or `%USERPROFILE%\_netrc`):
     ```powershell
     python -c "import earthaccess; earthaccess.login(strategy='interactive', persist=True)"
     ```
   NASA POWER, Planetary Computer and NOAA need no account.
2. **Stream and cache the CONUS series.** Only cropped, coarsened series are written to disk (~300 MB in
   total); nothing is downloaded whole. Runs resume where they stopped if interrupted. Measured times on the
   original machine (they run fine in parallel in separate terminals):
   ```powershell
   python scripts\build_cache.py conus wind_speed_50m air_temp_2m surface_pressure wind_speed_cubed_50m --end 2026-12   # ~5 min
   python scripts\build_cache.py conus solar_irradiance aerosol_optical_depth --end 2026-12 --workers 4             # ~1.5-2 h
   python scripts\build_cache.py conus runoff soil_moisture pdsi precipitation --end 2021-12                         # ~2-3 h
   python scripts\build_cache.py conus snow_water_equivalent --end 2020-12                                           # ~1-1.5 h
   ```
3. **Build the export:** `python scripts\build_export.py conus` (~4 min), then serve as in the quick start.
4. Optional: `python scripts\check_cache.py conus` prints each cached series with plausibility checks.

Source details, verified ids, units and known quirks are in [docs/sources.md](docs/sources.md).

### Host it online (GitHub Pages)
Live site: **https://ethomas-32.github.io/nasa/web/** (no install needed; hosted by GitHub, so the build
machine can be off).
```powershell
python scripts\deploy_pages.py        # publishes web/ + export/ (no NetCDF, ~68 MB) to the gh-pages branch
```
One-time setup on GitHub: *Settings > Pages > Build and deployment > Source: Deploy from a branch >
Branch `gh-pages`, folder `/ (root)` > Save*. Re-run the script after rebuilding results to update the site
(it force-pushes a single fresh commit to `gh-pages`; `main` is untouched). The repository must be public
for Pages on a free account. The OpenStreetMap basemap is fine for light (demo) traffic; heavy traffic would
need a tile provider with an account.

### Make a demo zip for another device
```powershell
python scripts\package_demo.py        # -> dist\resource-trends-demo.zip (web + results, ~13 MB)
```

## Repository layout
```
config/            regions.yaml (bbox, mask, sub-regions, provider preference), variables.yaml (verified sources)
src/resource_trends/
  stats.py         Theil-Sen, Mann-Kendall (tie + autocorrelation corrected), BH-FDR, Pettitt
  preprocess.py    annual / seasonal aggregation, cos(lat) area weighting
  registry.py      config loading, provider resolution per region
  sources/         streaming loaders: MERRA-2 (earthaccess), NASA POWER (AWS Zarr), TerraClimate,
                   Daymet, nClimGrid (Planetary Computer); incremental cache
  derived.py       wind power density
  masks.py         region land masks
  pipeline.py      run(region, variable) and run_all(region)
  portfolio.py     cross-resource correlation, joint-low frequency
  alerts.py        latest-month anomaly alerts vs trend-adjusted baseline
  validate.py      NOAA station comparison
  export.py        export contract + schema validation
scripts/           build_cache, build_export, check_cache, make_fixtures, make_mask, package_demo
tests/             offline tests (synthetic ground truth + small real fixtures)
web/               static front end (globe + dashboard); see web/README.md
docs/              sources, phase results, export contract
data/masks/        CONUS land mask (committed); data/cache/ and export/ are generated (git-ignored)
```

## Documentation
- [docs/sources.md](docs/sources.md): verified data sources and the findings that shaped the design
- [docs/phase4_conus.md](docs/phase4_conus.md), [docs/phase5_conus.md](docs/phase5_conus.md): trend results
- [docs/phase6_conus.md](docs/phase6_conus.md): portfolio (complementarity) results
- [docs/phase7_conus.md](docs/phase7_conus.md): anomaly alerts
- [docs/phase8_validation.md](docs/phase8_validation.md): station validation
- [docs/export_contract.md](docs/export_contract.md): the files the front end reads
- [web/README.md](web/README.md): the front end
- [claude.md](claude.md): project plan and method requirements
