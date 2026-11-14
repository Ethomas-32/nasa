"""Fetch tiny REAL raw subsets (5x5 deg box over Colorado, 3 months) into tests/fixtures/.
Each fixture is the provider's raw layout BEFORE standardisation, so tests exercise the real code.
Needs network (+ Earthdata login for MERRA-2). Run once; fixtures are committed.
    .\\.venv\\Scripts\\python.exe scripts\\make_fixtures.py
"""
import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path

from resource_trends.registry import Registry
from resource_trends.sources import merra2, nasa_power, planetary, nclimgrid

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
BOX = dict(lat_min=38.0, lat_max=43.0, lon_min=-109.0, lon_max=-104.0)
MONTHS = pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"])


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    reg = Registry.load()
    spec = lambda var, prov: next(p for p in reg.variables[var]["providers"] if p["provider"] == prov)

    # MERRA-2: three granules streamed, same raw assembly as merra2.load
    import earthaccess
    earthaccess.login(strategy="netrc")
    s = spec("solar_irradiance", "merra2")
    gs = earthaccess.search_data(short_name=s["dataset"], temporal=("2020-01-01", "2020-03-28"))
    by = {g["umm"]["GranuleUR"].split(".")[-2]: g for g in gs}
    res = [merra2._fetch_one((by[f"{m:%Y%m}"], s["variable"], BOX, f"{m:%Y%m}")) for m in MONTHS]
    raw = xr.DataArray(np.stack([r[1] for r in res]), dims=("time", "lat", "lon"),
                       coords={"time": MONTHS, "lat": res[0][2], "lon": res[0][3]}, name="SWGDN")
    raw.to_netcdf(OUT / "merra2_swgdn_raw.nc")

    # POWER: whole (tiny) time axis incl. the pre-allocated all-NaN future months, month-END stamps
    p = spec("wind_speed_50m", "nasa_power")
    v = nasa_power._open(p["dataset"])[p["variable"]]
    v = v.sel(lat=slice(BOX["lat_min"] - 1, BOX["lat_max"] + 1), lon=slice(BOX["lon_min"] - 1, BOX["lon_max"] + 1))
    v.isel(time=slice(480, None)).load().to_netcdf(OUT / "power_ws50m_raw.nc")   # 2021-01 .. 2029-12 axis
    v.sel(time=slice("2019-12-01", "2020-04-30")).load().to_netcdf(OUT / "power_ws50m_2020_raw.nc")

    # TerraClimate: lat descending, float64
    t = spec("runoff", "terraclimate")
    tv = planetary._open_zarr_asset("terraclimate")[t["variable"]]
    tv = tv.sel(lat=slice(BOX["lat_max"], BOX["lat_min"]), lon=slice(BOX["lon_min"], BOX["lon_max"]),
                time=slice("2020-01-01", "2020-03-01")).load()
    tv.to_netcdf(OUT / "terraclimate_q_raw.nc")

    # Daymet: raw Lambert block covering the box (x/y in metres), 3 months
    d = spec("snow_water_equivalent", "daymet")
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", " ".join(f"+{k}={val}" for k, val in planetary.LCC.items()) + " +units=m +no_defs", always_xy=True)
    X, Y = tr.transform(*np.meshgrid(np.linspace(BOX["lon_min"], BOX["lon_max"], 30), np.linspace(BOX["lat_min"], BOX["lat_max"], 30)))
    pad = 30e3
    dv = planetary._open_zarr_asset("daymet-monthly-na")[d["variable"]]
    dv = dv.sel(x=slice(X.min() - pad, X.max() + pad), y=slice(Y.max() + pad, Y.min() - pad)).isel(time=slice(480 - 12 * 0, None))
    dv = dv.sel(time=slice("2020-01-01", "2020-03-31")).load()
    dv = dv.drop_vars([c for c in ("lat", "lon") if c in dv.coords])   # 2-D aux coords; not needed, large
    dv.to_netcdf(OUT / "daymet_swe_raw.nc", encoding={dv.name: {"zlib": True, "complevel": 6, "dtype": "float32"}})

    # nClimGrid: one month window read through the real COG reader
    n = spec("precipitation", "nclimgrid")
    cat = planetary._catalog()
    arrs = []
    for m in MONTHS:
        it = next(cat.search(collections=[n["dataset"]], ids=[f"nclimgrid-{m:%Y%m}"]).items())
        arrs.append(nclimgrid.read_cog(it.assets["prcp"].href, BOX).expand_dims(time=[m]))
    xr.concat(arrs, "time").to_netcdf(OUT / "nclimgrid_prcp_raw.nc")
    for f in sorted(OUT.glob("*.nc")):
        print(f.name, f.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
