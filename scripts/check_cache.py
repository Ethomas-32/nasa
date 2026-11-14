"""Sanity-check cached CONUS series: contract, period, units, coverage and physical plausibility.
Reads only the local cache (no network for variables already cached).
    .\\.venv\\Scripts\\python.exe scripts\\check_cache.py conus
"""
import sys

import numpy as np

from resource_trends import preprocess, sources
from resource_trends.registry import Registry
from resource_trends.sources import _common as C

# Plausible CONUS area-mean ranges for the ANNUAL aggregate (sum or mean per variables.yaml).
# Loose physical bounds to catch unit/scale bugs, not to validate the science.
PLAUSIBLE = {
    "solar_irradiance": (120, 260),      # W m-2 annual mean surface SW
    "aerosol_optical_depth": (0.03, 0.4),
    "air_temp_2m": (5, 18),              # degC
    "surface_pressure": (850, 1000),     # hPa (CONUS mean elevation ~ 750 m)
    "wind_speed_50m": (3, 9),            # m/s
    "wind_speed_cubed_50m": (50, 1500),  # m3 s-3
    "wind_power_density": (30, 900),     # W m-2
    "runoff": (50, 600),                 # mm/yr
    "precipitation": (500, 1100),        # mm/yr
    "soil_moisture": (20, 400),          # mm
    "pdsi": (-6, 6),
    "snow_water_equivalent": (0.5, 100), # mm, peak monthly-mean SWE, area mean incl. snow-free cells
}

ORDER = ["solar_irradiance", "aerosol_optical_depth", "wind_speed_50m", "wind_speed_cubed_50m", "air_temp_2m",
         "surface_pressure", "wind_power_density", "runoff", "precipitation", "soil_moisture", "pdsi",
         "snow_water_equivalent"]


def main(region="conus"):
    reg = Registry.load()
    bbox = reg.regions[region]["bbox"]
    bad = 0
    for v in ORDER:
        try:
            da = sources.load(v, region, reg, start="1981-01", end="2026-12")
        except Exception as e:  # noqa: BLE001 - report and continue
            print(f"{v:24s} NOT AVAILABLE: {type(e).__name__}: {e}")
            bad += 1
            continue
        C.check_contract(da, v, bbox)
        how = reg.variables[v]["aggregation"]
        ann = preprocess.annualize(da, how, min_count=10)
        series = preprocess.area_weighted_mean(ann).values
        full = series[np.isfinite(series)]
        lo, hi = PLAUSIBLE[v]
        ok = lo <= np.nanmean(full) <= hi
        bad += not ok
        nan_frac = float(da.isnull().mean())
        t0, t1 = str(da.time.values[0])[:7], str(da.time.values[-1])[:7]
        print(f"{v:24s} {da.attrs['provider']:28s} {t0}..{t1} n={da.sizes['time']:3d} grid={da.sizes['lat']}x{da.sizes['lon']} "
              f"nan={nan_frac:.2f} annual({how}) CONUS mean={np.nanmean(full):9.3f} {da.attrs['units']:7s} "
              f"range[{np.nanmin(full):.3g},{np.nanmax(full):.3g}] {'OK' if ok else 'IMPLAUSIBLE'}")
    print("all plausible" if bad == 0 else f"{bad} problem(s)")
    return bad


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
