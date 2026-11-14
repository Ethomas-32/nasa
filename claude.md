# resource-trends: project plan and context for Claude Code

(Project name is a placeholder. This is a FRESH repo built from scratch: no code is carried over
from any earlier prototype. See section 11 for what that means and how to test it.)

## 1. What we are building (hackathon entry)
The challenge: build a tool that selects variables measured by Earth science missions or
produced by Earth science models, visualizes how they change over time, and determines
WHAT is changing, WHERE, HOW MUCH, and whether the change is statistically SIGNIFICANT.
The brief stresses that a variable can trend one way in one region and the opposite way in
another, so analysis must be spatial (per-pixel), not just area averages.

**Our angle:** decision support for **renewable energy providers** across **solar, wind and
hydropower**, with the same data also useful to **farmers** (secondary audience).
- Customer question: "Is the resource my portfolio depends on changing in this region, by how
  much, can I trust the signal, and do my resources cover for each other?"
- Farmers: same variables (precip, soil moisture, temperature, solar, wind, snow) answer
  "is growing-season water/heat changing here?" Do not build a second product for them.
- Competition focus themes (must be visible in the tool): **hydrology, cryosphere,
  atmospheric dynamics, atmospheric chemistry.** Mapping: wind = dynamics; smoke/dust/aerosol
  reducing solar = chemistry; snowpack feeding hydro = cryosphere; runoff/soil moisture = hydrology.

**Scope discipline:** trend detection is the core. "Early warning" means ANOMALY ALERTS
(latest data vs a trend-adjusted baseline, e.g. soil moisture below its 10th percentile for the
season). It does NOT mean weather forecasting. Never claim forecasting.

## 2. Decisions already made
- **Primary region: contiguous US (CONUS)**, most data-dense, North America is a competition
  requirement. **Secondary: Africa** (proves generalization; sparse stations, so state
  uncertainty). A coarse **global** run feeds the later globe overview.
- **Region is configuration, not code.** Variables list providers with a coverage tag; each
  region lists its tags and provider preferences; the registry resolves the best provider.
- **Backend first, visualisation later.** Precompute everything offline into static files.
  The front end (later) only reads files. Nothing heavy at demo time.
- Main sources: **NASA POWER** (energy-oriented, free, no account), **Microsoft Planetary
  Computer** public STAC API (no key; the Hub was retired in 2024, the catalog/API remain),
  **NASA Earthdata via `earthaccess`** (MERRA-2 etc., free login), NOAA station data for
  validation. Giovanni is for EXPLORATION ONLY, not a backend dependency.
- News API is optional and last (see section 9).

## 3. The three resource indices (+ supporting variables)
| Resource | Primary index | Supporting | Candidate source (ALL UNVERIFIED) |
|---|---|---|---|
| Solar | surface shortwave irradiance (all-sky) | aerosol optical depth, cloud, air temp | NASA POWER `ALLSKY_SFC_SW_DWN`; MERRA-2 aerosol (`M2TMNXAER`, `TOTEXTTAU`) |
| Wind | wind speed at 50 m AND wind power density proxy (rho * v^3 / 2) | air density (T2M, PS) | NASA POWER `WS50M`, `T2M`, `PS`; or MERRA-2 |
| Hydro | runoff (annual sum) | precipitation, snow water equivalent, soil moisture, PDSI | TerraClimate `q`, `ppt`, `soil`, `PDSI` (Planetary Computer); Daymet `swe` (CONUS); NClimGrid precip |

Notes:
- Power density trends can be much larger than speed trends (cubic). Report both.
- Runoff is a RESOURCE proxy, not generation (dams/reservoirs/operations are not modeled).
  Solar and wind indices are REANALYSIS/model-assimilated, not site measurements. State this.
- All three need a COMMON PERIOD for cross-resource analysis. Tentatively 1984 to latest full
  year (POWER solar starts 1984; POWER meteorology 1981; TerraClimate 1958). Verify.
- Seasonality matters: solar peaks summer, wind often winter, hydro spring melt. Support
  per-season trends, not only annual.

## 4. Statistical method (do not weaken)
- Per-pixel Theil-Sen slope + Mann-Kendall test, tie-corrected, NaN-aware, vectorized in numpy.
- Autocorrelation: inflate Mann-Kendall variance by (1+rho1)/(1-rho1) for positive lag-1
  autocorrelation of Sen residuals.
  Expected limitation (seen in an earlier throwaway prototype, so RE-MEASURE it in this repo's own
  tests, don't assume): on null data with strong autocorrelation the corrected false-positive rate
  stays somewhat above the nominal 5% because lag-1 is underestimated from ~40 annual values.
  Measure it, document the number, and don't hide it.
- Field significance: Benjamini-Hochberg FDR across pixels, alpha_fdr = 0.10 (Wilks 2016 suggests
  ~2x the desired global level for spatially correlated grids).
- Magnitudes: slope per decade, total change, percent change per decade (only where a ratio scale
  makes sense, i.e. `relative: true`).
- Area weighting with cos(latitude) for any average.
- Always report the period used. Add a start-year sensitivity check (does the trend survive
  moving the start year by +/- 5 years?).
- Cross-resource analysis (new): correlation of DETRENDED, DESEASONALIZED monthly anomalies
  between resources; frequency of joint low-resource periods (>=2 resources below their own
  20th percentile in the same month). Test with synthetic data with known correlation.

## 5. Backend architecture
```
config/regions.yaml        region bbox, coverage tags, provider preference
config/variables.yaml      variables: theme, resource, audience, units, aggregation, providers
src/<pkg>/registry.py      load config, resolve provider per (region, variable)
src/<pkg>/sources/         one loader per provider; contract below
src/<pkg>/derived.py       derived variables (wind power density, speed from u/v)
src/<pkg>/preprocess.py    annualize/seasonalize, quality filter, area weights
src/<pkg>/stats.py         trend + significance (written from scratch; spec in sections 4 and 11)
src/<pkg>/portfolio.py     cross-resource correlation, joint-low frequency
src/<pkg>/alerts.py        anomaly percentile alerts vs trend-adjusted baseline
src/<pkg>/validate.py      compare gridded data to station observations
src/<pkg>/export.py        write the export contract (section 7)
src/<pkg>/pipeline.py      run(region, variable) and run_all(region)
tests/                     synthetic ground-truth tests + small cached real-data fixtures
```
**Loader contract:** return an xarray DataArray named after the variable, dims (time, lat, lon),
ascending lat, lon in [-180, 180], cropped to the region bbox, with `units` attr and `provider` attr.
Provider-specific awkwardness (projections, hourly->monthly, u/v->speed) is handled INSIDE the loader.

## 6. Backend phases (do in order; each has an acceptance test)
**Phase 0: repo setup.** New folder, git, venv, `requirements.txt`, `pyproject.toml` (src layout,
pytest pythonpath), empty package skeleton, one passing smoke test. Done when: pytest green and
`pip install -e .` works on Windows/PowerShell.

**Phase 0b: statistics engine from scratch, test-first.** Write the tests described in section 11
BEFORE `stats.py` and `preprocess.py`, then implement until they pass. This is the foundation
everything else trusts, so do not move on until it is green. Done when: all section-11 tests pass.

**Phase 1: registry with resource tags + derived variables.** Add `resource: solar|wind|hydro|none`
and `audience: [energy, agriculture]` to variables. Implement `derived.py`. Done when: tests resolve
providers per region and compute wind power density from a synthetic speed/temp/pressure.

**Phase 2: VERIFY SOURCES FIRST (needs network; do this before coding loaders).** For each
provider, make a real request, record exact collection ids / asset keys / variable names / units /
time coverage / grid resolution, and flip `status: unverified` to `verified` in variables.yaml.
- Planetary Computer: `catalog.get_collection(id).assets.keys()`. Daymet is on a Lambert conformal
  grid (needs reprojection). Check whether NClimGrid is Zarr or COG.
- NASA POWER: decide HOW to get a CONUS grid. The API is point-based; options are (a) batched point
  calls on a coarse grid (mind rate limits), (b) check for a cloud-hosted analysis-ready/Zarr copy,
  (c) take the underlying MERRA-2 directly via `earthaccess`. Pick empirically and write down why.
- Earthdata: set up `earthaccess` login; confirm MERRA-2 collection short names and variable names.
Done when: a table of verified facts is committed (docs/sources.md) and no "unverified" remains for
the providers we use.

**Phase 3: real-data loaders, one resource at a time.** Order: solar irradiance -> wind (50 m, T,
pressure) -> hydro (TerraClimate runoff, precip) -> SWE (Daymet) -> aerosol (MERRA-2).
Cache a SMALL real subset (e.g. 5x5 degree box) as test fixtures so tests run offline.
Done when: each loader returns the contract shape for CONUS and a loader test passes on the fixture.

**Phase 4: single-variable pipeline on real data.** `run("conus", "<var>")` writes trend maps +
summary. Sanity-check against known physical behavior (e.g. Southwest drying, Northeast wetting
for precipitation; check, don't assume). Done when: results are plausible and the period/provider
are recorded in the output.

**Phase 5: three-resource run.** `run_all("conus")` over the common period, annual and per-season.
Done when: outputs exist for solar, wind (speed and power), hydro (runoff) and supporting variables.

**Phase 6: portfolio module.** Cross-resource correlation and joint-low frequency per region and per
grid cell. Synthetic tests with known correlation. Done when: tests pass and CONUS output exists.

**Phase 7: anomaly alerts.** Latest available data vs trend-adjusted seasonal baseline; percentile
thresholds. POWER is documented as being within about a week of real time; verify actual latency.
Done when: an alert list is produced for the latest month and clearly labeled "anomaly, not forecast".

**Phase 8: validation.** Compare a handful of sites against NOAA station data. Note: the NCEI v2
Climate Data Online endpoint may be deprecated in favor of the Access Data Service
(`https://www.ncei.noaa.gov/access/services/data/v1`); sources conflicted, so test both.
Optional stretch: compare resource indices against actual US generation data by state/fuel
(EIA publishes this, UNVERIFIED, needs a key). Done when: a validation table with errors is produced.

**Phase 9: export contract + catalog (section 7).** Done when: a script emits a complete export
for CONUS and a schema test validates every file.

**Phase 10: Africa + coarse global.** Same pipeline, new region entries and global-product providers.
Done when: Africa runs end to end for the variables that have global providers, and the tool says
which variables are unavailable or lower-confidence there.

## 7. Export contract (this decouples the later front end)
Static files per region under `export/<region>/`:
- `catalog.json`: all variables with theme, resource, audience, units, provider, status,
  period, caveats, and file paths.
- `<var>.trend.*`: slope/decade, total change, pct change, p-value, q-value, significant mask,
  direction (as NetCDF/Zarr and as PNG overlay with geographic bounds for the map/globe).
- `<var>.summary.json`: area fractions significant up/down, `opposing_trend_score`, `coverage_score`,
  regional mean trend + p-value, period, method strings, and the regional annual series.
- `<var>.pixel_series.*`: a way to fetch a pixel's time series on click (coarse JSON chunks or Zarr).
- `portfolio.json`: cross-resource correlations, joint-low frequency, per-resource trend cards.
- `alerts.json`: current anomaly alerts with variable, location, percentile, baseline definition.
- `narrative.json`: auto-generated plain-language summary sentences (templated from the numbers; no
  invented claims).
No server required for the hackathon. If one is needed later, serve these files statically.

## 8. Visualisation phase (AFTER the backend passes Phase 9)
- Entry: a globe; click a region -> dashboard. Teaser layer on the globe from the coarse global run.
- Dashboard: variable/resource selector, trend map with significance stippling, click-for-series,
  resource cards (solar/wind/hydro side by side), complementarity view, alert list, variable ranking,
  data-caveat badges (reanalysis vs measurement, record length, provider).
- Likely stack: globe.gl or deck.gl for the globe; a light framework for the dashboard. Decide then.
- Do not start this until the export contract exists and has a schema test.

## 9. News API (optional, last)
- NewsAPI.org free plan is development-only (not allowed in production) with a ~24 h delay; business
  plan is expensive. For a demo use GDELT (no key) or another source whose terms allow our use.
- Purpose: show headlines near a detected anomaly (drought, heat wave, curtailment) as context only.
- Adds noise and scope. Only after Phase 9.

## 10. Honesty rules (important)
- Nothing in variables.yaml is trusted until Phase 2 verifies it. Never invent collection ids, asset
  keys, variable names or dataset start years; check them and record the evidence.
- Do not claim forecasting, generation forecasts or financial outcomes.
- Every output carries its provider, period and method. Label reanalysis/model products as such.
- Different products are not directly comparable; use global products for cross-region comparison,
  regional products only for in-region depth, and say which was used.
- If a test threshold has to change, explain why from measured behavior; do not loosen silently.

## 11. Starting from scratch: what must be built, and how to prove it works
Everything is new. An earlier throwaway prototype existed; do NOT assume anything from it is
correct, and do not copy its provider names (they were guesses). The design lessons below are what
carried over, as REQUIREMENTS to satisfy with fresh code and fresh tests.

**Statistics engine requirements (`stats.py`, `preprocess.py`):**
- Input is plain numpy shaped (n_time, n_pixels) with NaN for missing; output arrays per pixel.
  A thin xarray wrapper builds map Datasets. Chunk over pixels so memory stays bounded for long
  records (pairwise differences grow with n^2).
- Theil-Sen slope: median of pairwise slopes, computed with the real time coordinate, skipping pairs
  with a NaN.
- Mann-Kendall: S statistic, tie-corrected variance, continuity-corrected z, two-sided p-value.
  A constant series must return p = 1 and slope 0, not NaN or an error.
- Data-quality rule: pixel is NaN unless it has >= 80% valid values and a minimum count.
- Autocorrelation variance inflation and BH-FDR as in section 4. The FDR function returns both the
  significance mask and q-values, leaves NaN p-values as NaN/False.
- `annualize(da, how in {sum, mean, max}, min_count)`: a year is NaN if too few months are valid.
  Also build a seasonal variant. Area weights use cos(latitude), zero where data is NaN.

**Tests to write FIRST (these define "correct"):**
1. Compare Mann-Kendall S, z and p against a deliberately simple pure-python reference
   implementation on random data, to 1e-9.
2. Compare Theil-Sen slope against `scipy.stats.theilslopes` to 1e-10, including a series with gaps.
3. Heavy-ties data (small integers): tie correction matches the reference.
4. Missing-data rules: 10% missing is kept, 40% missing becomes NaN; constant series gives p = 1.
5. BH-FDR on a hand-computed example (include a NaN), q-values monotone in sorted p.
6. Synthetic field with KNOWN truth: west third +trend, east third -trend, middle null, AR(1)
   annual noise, seasonal cycle, a NaN block. Assert mean recovered slope within tolerance per
   region, high detection rate in trending regions, and correct signs (this proves the
   "opposite trends in different places" case works).
7. Pure-null field: measure the raw vs autocorrelation-corrected false-positive rate over several
   seeds, assert corrected < raw by a clear margin, assert FDR leaves ~no significant pixels, and
   WRITE DOWN the measured numbers in the test comment. Pick thresholds from the measurement.

**Everything else is also new:** registry (resource/audience tags, derived variables), all real
loaders, portfolio, alerts, validation, export. Write each with its own synthetic-data test first
where possible, then check against real data once Phase 2 has verified the sources.

## 12. Conventions and environment
- User is on Windows / PowerShell. Do NOT give `VAR=value cmd` syntax; use `$env:VAR="value"` or
  `pip install -e .`.
- Network is available on the user's machine; verify against live services there.
- Keep stats functions source-agnostic (numpy in, numpy out). Sources and regions live in YAML.
- Commit small, working steps; run pytest before every commit.

## 13. Open questions to settle early
1. Which resource headlines the pitch? (Hydro best fits cryosphere/hydrology themes; solar/wind have
   the easiest data via POWER.)
2. POWER grid access method (Phase 2).
3. Exact common period across the three resources.
4. Whether to attempt generation-data validation (EIA) or stay with station validation.