"""Build the CONUS land mask from the nClimGrid footprint (US-only, 1/24 deg): a cell is inside
where nClimGrid has data. Uses one month (2020-07 prcp; July avoids any winter nodata quirks).
    .\\.venv\\Scripts\\python.exe scripts\\make_mask.py
"""
from pathlib import Path

import numpy as np

from resource_trends.sources import nclimgrid, planetary

OUT = Path(__file__).resolve().parents[1] / "data" / "masks" / "conus_nclimgrid_footprint.nc"
BBOX = dict(lat_min=24.0, lat_max=50.0, lon_min=-125.5, lon_max=-66.0)


def main():
    cat = planetary._catalog()
    it = next(cat.search(collections=["noaa-nclimgrid-monthly"], ids=["nclimgrid-202007"]).items())
    da = nclimgrid.read_cog(it.assets["prcp"].href, BBOX).sortby("lat")
    m = np.isfinite(da).astype("int8")
    m.name = "inside"
    m.attrs = {"description": "1 where nClimGrid (NOAA, CONUS-only) has data, 0 elsewhere",
               "source": "Planetary Computer noaa-nclimgrid-monthly, item nclimgrid-202007, asset prcp"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_netcdf(OUT, encoding={"inside": {"zlib": True, "complevel": 9}})
    print(OUT, m.shape, "inside fraction of bbox", float(m.mean()), OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
