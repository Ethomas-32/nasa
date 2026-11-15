import numpy as np
import xarray as xr

from resource_trends import masks
from resource_trends.registry import Registry


def test_fraction_on_grid_simple():
    # fine grid 0.25 deg, 8x8; left half inside
    lat = np.arange(0.125, 2.0, 0.25)
    lon = np.arange(0.125, 2.0, 0.25)
    fine = xr.DataArray(np.zeros((8, 8)), dims=("lat", "lon"), coords={"lat": lat, "lon": lon})
    fine[:, :4] = 1
    fine[0, 0] = np.nan                       # NaN counts as outside: 7 of the 8 fine cells in target (0,0)
    frac = masks.fraction_on_grid(fine, np.array([0.5, 1.5]), np.array([0.25, 0.75, 1.25, 1.75]))
    np.testing.assert_allclose(frac.values, [[0.875, 1.0, 0.0, 0.0], [1.0, 1.0, 0.0, 0.0]])
    # target cells entirely outside the fine grid -> 0
    assert masks.fraction_on_grid(fine, np.array([10.0]), np.array([10.0])).item() == 0.0


def test_conus_mask_is_us_land_only():
    reg = Registry.load()
    lat = np.arange(24.75, 49.5, 0.5)
    lon = np.arange(-124.75, -66.5, 0.5)
    m = masks.region_mask(reg.regions["conus"], lat, lon)
    at = lambda la, lo: bool(m.sel(lat=la, lon=lo, method="nearest"))
    assert at(39.0, -98.0) and at(40.0, -105.0) and at(33.5, -84.5)   # Kansas, Colorado, Georgia
    assert not at(30.0, -120.0)        # Pacific
    assert not at(27.0, -90.0)         # Gulf of Mexico
    assert not at(47.5, -75.0)         # Quebec
    assert not at(28.0, -105.0)        # Chihuahua, Mexico
    assert 0.45 < float(m.mean()) < 0.7
    assert masks.region_mask(reg.regions["africa"], lat, lon) is None
