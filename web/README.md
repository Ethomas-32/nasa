# Resource Trends web front end

Plain HTML + JS modules, no build step. Libraries load from jsDelivr (pinned: globe.gl 2.46.2,
maplibre-gl 5.24.0, three-globe 2.44.0 textures); the basemap is OpenStreetMap raster tiles
(attribution shown). Needs an internet connection for those; all analysis data is local.

## Run (PowerShell, from the repository root)
```powershell
.\.venv\Scripts\python.exe scripts\build_export.py conus      # only if export/conus is missing or stale
.\.venv\Scripts\python.exe -m http.server 8000
```
Open http://localhost:8000/web/ (globe) or http://localhost:8000/web/dashboard.html?region=conus.
Serve the repository ROOT, not `web/`: the pages read `../export/<region>/`.

## Pages
- `index.html`: globe; regions from `export/index.json` (available ones open the dashboard, others say
  "coming soon"); three headline sentences from the region's `narrative.json`; a teaser layer drapes an
  exported CONUS overlay (temperature trend, precipitation trend, solar-hydro complementarity) onto the
  Earth texture. Both are equirectangular, so it is placed by its bounds without reprojection.
  `?teaser=trend:precipitation` (or `portfolio:r_solar_hydro`, `none`) picks the initial layer.
- `dashboard.html?region=<id>`: map layers (trend by season, latest-month anomaly, complementarity),
  variable list grouped by resource, resource cards, narrative + caveats + sub-region table,
  click-for-series (tested per-cell trend from the pixel tiles), portfolio table, alert list (with data
  age), variable ranking. State is kept in the URL hash, so views can be bookmarked or shared.

## Notes
- Overlays are lat/lon grids re-sampled row by row into Web Mercator (`js/overlay.js`), so cells line up
  with coastlines; MapLibre's image source would otherwise misplace rows by up to ~1 degree.
- Colours: diverging blue/grey/red from the dataviz reference palette; for water variables an increase
  is blue. Faded cells are not significant (FDR 10%). Status alerts carry an icon and a text label.
- Checked in headless Chrome: dashboard (trend, complementarity, anomaly layers) and globe render.
  Not checkable headless: map clicks (the tile lookup was verified separately) and a vector basemap
  (which is why the raster OSM basemap is used).
