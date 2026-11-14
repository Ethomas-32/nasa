"""Offline loader tests: real raw subsets (tests/fixtures, made by scripts/make_fixtures.py) pushed
through each provider's pure `standardize` step, plus synthetic tests for shared helpers."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from resource_trends import sources
from resource_trends.registry import Registry
from resource_trends.sources import _common as C
from resource_trends.sources import merra2, nasa_power, nclimgrid, planetary

FIX = Path(__file__).parent / "fixtures"
BOX = dict(lat_min=38.0, lat_max=43.0, lon_min=-109.0, lon_max=-104.0)
REG = Registry.load()


def spec(var, provider):
    return next(p for p in REG.variables[var]["providers"] if p["provider"] == provider)


def raw(name):
    with xr.open_dataarray(FIX / name) as d:
        return d.load()


# --- MERRA-2 ------------------------------------------------------------------------------------
def test_merra2_solar_fixture_meets_contract():
    out = merra2.standardize(raw("merra2_swgdn_raw.nc"), "solar_irradiance", "W m-2", spec("solar_irradiance", "merra2"), BOX)
    C.check_contract(out, "solar_irradiance", BOX)
    assert out.attrs["units"] == "W m-2" and out.attrs["provider"] == "merra2"
    assert out.attrs["native_variable"] == "SWGDN"
    assert out["time"].dt.strftime("%Y-%m").values.tolist() == ["2020-01", "2020-02", "2020-03"]
    jan, mar = float(out.isel(time=0).mean()), float(out.isel(time=2).mean())
    assert 60 < jan < 200 and 120 < mar < 300 and mar > jan  # Colorado: winter < early spring, W m-2
    assert out.isnull().sum() == 0
    # native 0.5 x 0.625 grid is kept (nothing finer than the target, so no coarsening)
    assert np.allclose(np.diff(out["lat"].values), 0.5)
    assert np.allclose(np.diff(out["lon"].values), 0.625)


# --- POWER --------------------------------------------------------------------------------------
def test_power_month_end_stamps_become_month_starts():
    out = nasa_power.standardize(raw("power_ws50m_2020_raw.nc"), "wind_speed_50m", "m s-1", spec("wind_speed_50m", "nasa_power"), BOX)
    C.check_contract(out, "wind_speed_50m", BOX)
    assert out["time"].dt.strftime("%Y-%m").values.tolist() == ["2019-12", "2020-01", "2020-02", "2020-03", "2020-04"]
    assert out.attrs["units"] == "m s-1"
    assert 1 < float(out.mean()) < 15


def test_power_preallocated_future_months_are_dropped():
    r = raw("power_ws50m_raw.nc")  # axis runs to 2029-12 but data stop at the latest published month
    assert r.sizes["time"] > 100 and bool(r.isel(time=-1).isnull().all())
    out = nasa_power.standardize(r, "wind_speed_50m", "m s-1", spec("wind_speed_50m", "nasa_power"), BOX)
    assert out["time"].max() < pd.Timestamp("2027-01-01")
    assert out.notnull().all()
    assert out["time"].min() == pd.Timestamp("2021-01-01")


def test_power_pressure_hpa_stays_hpa_and_converts_to_kpa():
    da = xr.DataArray(np.full((1, 2, 2), 840.0), dims=("time", "lat", "lon"),
                      coords={"time": pd.to_datetime(["2020-01-31"]), "lat": [39.0, 40.0], "lon": [-107.0, -106.0]})
    s = dict(spec("surface_pressure", "nasa_power"))
    assert nasa_power.standardize(da, "surface_pressure", "hPa", s, BOX).values.max() == pytest.approx(840.0)
    assert nasa_power.standardize(da, "surface_pressure", "kPa", s, BOX).values.max() == pytest.approx(84.0)


# --- TerraClimate -------------------------------------------------------------------------------
def test_terraclimate_descending_lat_float64_becomes_contract():
    r = raw("terraclimate_q_raw.nc")
    assert r["lat"].values[0] > r["lat"].values[-1] and r.dtype == np.float64  # as the provider ships it
    out = planetary.standardize_terraclimate(r, "runoff", "mm", spec("runoff", "terraclimate"), BOX)
    C.check_contract(out, "runoff", BOX)
    assert out.dtype == np.float32 and out.attrs["units"] == "mm"
    assert float(out.min()) >= 0
    assert out.sizes["lat"] > 100  # 1/24 deg native grid kept by standardize (coarsening is a separate step)
    c = C.coarsen_to(out, 0.25)
    assert c.sizes["lat"] < out.sizes["lat"] / 5 and abs(float(c.mean()) - float(out.mean())) < 0.5 * float(out.mean()) + 1


# --- Daymet -------------------------------------------------------------------------------------
def test_daymet_monthly_sum_becomes_mean_swe():
    # Daymet monthly swe is a sum of daily values: constant 1 mm SWE all month -> total = days.
    t = pd.to_datetime(["2020-01-16T12:00", "2020-02-15T12:00", "2020-03-16T12:00"])
    total = np.array([31.0, 29.0, 31.0])[:, None, None] * np.ones((3, 2, 2))
    da = xr.DataArray(total, dims=("time", "lat", "lon"), coords={"time": t, "lat": [39.0, 40.0], "lon": [-107.0, -106.0]})
    out = planetary.standardize_daymet(da, "snow_water_equivalent", "mm", spec("snow_water_equivalent", "daymet"), BOX)
    C.check_contract(out, "snow_water_equivalent", BOX)
    np.testing.assert_allclose(out.values, 1.0)  # leap-year February handled
    assert (out["time"].dt.day == 1).all()


def test_daymet_lambert_to_latlon_fixture():
    r = raw("daymet_swe_raw.nc")
    assert set(("x", "y")) <= set(r.dims) and r["y"].values[0] > r["y"].values[-1]
    lat = np.arange(38.0, 43.0 + 1e-9, 0.25)
    lon = np.arange(-109.0, -104.0 + 1e-9, 0.25)
    out = planetary.daymet_to_latlon(r, lat, lon, f=25)
    assert out.dims == ("time", "lat", "lon") and out.shape == (3, lat.size, lon.size)
    assert float(out.max()) <= float(r.max()) + 1e-3 and float(out.min()) >= 0
    # Colorado Rockies in Jan hold far more SWE than the Utah/Wyoming-basin average in Mar's dry cells;
    # the strongest check: the January field has a real spatial gradient (mountains vs plains)
    jan = out.isel(time=0)
    assert float(jan.max()) > 5 * max(float(jan.quantile(0.1)), 1.0)
    # cells outside the Daymet grid are NaN, not an exception
    far = planetary.daymet_to_latlon(r, np.array([60.0]), np.array([-20.0]), f=25)
    assert np.isnan(far.values).all()
    full = planetary.standardize_daymet(out, "snow_water_equivalent", "mm", spec("snow_water_equivalent", "daymet"), BOX)
    C.check_contract(full, "snow_water_equivalent", BOX)


# --- nClimGrid ----------------------------------------------------------------------------------
def test_read_cog_orientation_and_window(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    data = np.arange(100, dtype="float32").reshape(10, 10)   # row 0 = northernmost
    data[0, 0] = np.nan
    p = tmp_path / "t.tif"
    with rasterio.open(p, "w", driver="GTiff", height=10, width=10, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(-110.0, 45.0, 0.5, 0.5), nodata=np.nan) as dst:
        dst.write(data, 1)
    box = dict(lat_min=41.0, lat_max=43.0, lon_min=-108.0, lon_max=-106.0)
    out = nclimgrid.read_cog(str(p), box)
    # cell centres are at ...-107.75 etc.; lat centres 44.75 (row 0) ... 40.25 (row 9)
    assert out["lat"].values[0] > out["lat"].values[-1]         # raw is north-up; finalize flips it
    row = int(round((45.0 - 0.25 - float(out["lat"].values[0])) / 0.5))
    col = int(round((float(out["lon"].values[0]) - (-110.0 + 0.25)) / 0.5))
    assert out.values[0, 0] == data[row, col]
    assert float(out["lat"].min()) >= box["lat_min"] - 0.6 and float(out["lat"].max()) <= box["lat_max"] + 0.6


def test_nclimgrid_fixture_meets_contract():
    out = nclimgrid.standardize(raw("nclimgrid_prcp_raw.nc"), "precipitation", "mm", spec("precipitation", "nclimgrid"), BOX)
    C.check_contract(out, "precipitation", BOX)
    assert out.attrs["provider"] == "nclimgrid" and float(out.min()) >= 0
    assert 1 < float(out.mean()) < 200  # mm / month


# --- shared helpers -----------------------------------------------------------------------------
def test_unit_conversion_and_refusal():
    da = xr.DataArray([101.325], dims="x")
    assert C.convert_units(da.copy(), "kPa", "hPa").item() == pytest.approx(1013.25)
    assert C.convert_units(xr.DataArray([5.0]), "C", "degC").attrs["units"] == "degC"
    with pytest.raises(ValueError):
        C.convert_units(xr.DataArray([1.0]), "mm", "W m-2")


def test_coarsen_to_is_nan_aware_and_noop_when_not_finer():
    lat, lon = np.arange(4) * 0.25, np.arange(4) * 0.25
    a = np.arange(16, dtype=float).reshape(4, 4)
    a[0, 0] = np.nan
    da = xr.DataArray(a, dims=("lat", "lon"), coords={"lat": lat, "lon": lon})
    c = C.coarsen_to(da, 0.5)
    assert c.shape == (2, 2)
    assert c.values[0, 0] == pytest.approx(np.mean([1, 4, 5]))
    assert C.coarsen_to(da, 0.25).shape == (4, 4) and C.coarsen_to(da, None).shape == (4, 4)


def test_contract_checker_rejects_violations():
    good = xr.DataArray(np.zeros((1, 2, 2)), dims=("time", "lat", "lon"), name="v",
                        coords={"time": pd.to_datetime(["2020-01-01"]), "lat": [1.0, 2.0], "lon": [1.0, 2.0]},
                        attrs={"units": "x", "provider": "p"})
    C.check_contract(good, "v")
    with pytest.raises(AssertionError):
        C.check_contract(good.isel(lat=slice(None, None, -1)))
    with pytest.raises(AssertionError):
        C.check_contract(good.assign_coords(time=pd.to_datetime(["2020-01-31"])))
    with pytest.raises(AssertionError):
        C.check_contract(good.assign_coords(lon=[100.0, 200.0]))
    with pytest.raises(AssertionError):
        C.check_contract(good.drop_attrs() if hasattr(good, "drop_attrs") else xr.DataArray(good.values, dims=good.dims, coords=good.coords))


def test_cached_series_is_incremental_and_resumable(tmp_path):
    calls = []

    def make(months):
        return xr.DataArray(np.ones((len(months), 2, 2)) * months.month.values[:, None, None], dims=("time", "lat", "lon"),
                            coords={"time": months, "lat": [1.0, 2.0], "lon": [1.0, 2.0]}, attrs={"units": "x", "provider": "p"}, name="v")

    def fetch(missing):
        calls.append(list(missing))
        for y in sorted(set(missing.year)):
            yield make(missing[missing.year == y])

    path = tmp_path / "c.nc"
    first = C.cached_series(path, C.month_index("2019-11", "2020-02"), fetch)
    assert first.sizes["time"] == 4 and len(calls[0]) == 4
    again = C.cached_series(path, C.month_index("2019-11", "2020-02"), fetch)
    assert len(calls) == 1 and again.sizes["time"] == 4          # nothing refetched
    ext = C.cached_series(path, C.month_index("2019-11", "2020-04"), fetch)
    assert len(calls) == 2 and [m.strftime("%Y-%m") for m in calls[1]] == ["2020-03", "2020-04"]
    assert ext.sizes["time"] == 6 and ext.attrs["provider"] == "p"
    sub = C.cached_series(path, C.month_index("2020-01", "2020-02"), fetch)
    assert sub.sizes["time"] == 2 and len(calls) == 2


def test_cached_series_provider_without_data_raises(tmp_path):
    with pytest.raises(LookupError):
        C.cached_series(tmp_path / "x.nc", C.month_index("2030-01", "2030-03"), lambda m: iter(()))


def test_load_computes_derived_wind_power_density(tmp_path, monkeypatch):
    def fake(units_by_var):
        def loader(variable, units, spec, bbox, months, path, target_deg=None, **_):
            val = {"wind_speed_cubed_50m": 1000.0, "air_temp_2m": 15.0, "surface_pressure": 1013.25}[variable]
            return xr.DataArray(np.full((len(months), 2, 2), val, "float32"), dims=("time", "lat", "lon"), name=variable,
                                coords={"time": months, "lat": [30.0, 31.0], "lon": [-100.0, -99.0]},
                                attrs={"units": units, "provider": "fake"})
        return loader

    monkeypatch.setattr(sources, "_provider_loader", lambda provider, spec: fake({}))
    out = sources.load("wind_power_density", "conus", REG, start="2000-01", end="2000-03", cache_dir=tmp_path)
    assert out.attrs["units"] == "W m-2" and out.name == "wind_power_density"
    assert out.dims == ("time", "lat", "lon")
    np.testing.assert_allclose(out.values, 612.5, rtol=1e-3)


def test_monthly_mean_of_daily_cube():
    t = pd.date_range("2020-01-01", "2020-03-31", freq="D")
    v = np.full((t.size, 1, 1), 2.0)
    v[t.month == 2] = 4.0
    v[(t.month == 3) & (t.day <= 5)] = np.nan            # March: 26/31 valid = 84% < 90% -> NaN
    da = xr.DataArray(v, dims=("time", "lat", "lon"), coords={"time": t, "lat": [40.0], "lon": [-100.0]})
    out = nasa_power.monthly_mean_of_daily_cube(da)
    # March fails the 90%-of-days rule everywhere, so it is NaN in every cell and dropped entirely
    # (the same path drops an incomplete latest month and POWER's pre-allocated future months)
    assert out["time"].dt.strftime("%Y-%m").values.tolist() == ["2020-01", "2020-02"]
    assert out.sel(time="2020-01-01").item() == pytest.approx(8.0)
    assert out.sel(time="2020-02-01").item() == pytest.approx(64.0)


def test_monthly_mean_of_daily_cube_is_not_cube_of_mean():
    t = pd.date_range("2020-01-01", "2020-01-31", freq="D")
    v = np.where(np.arange(t.size) % 2 == 0, 0.0, 10.0)[:, None, None]   # alternating calm / 10 m/s
    da = xr.DataArray(v, dims=("time", "lat", "lon"), coords={"time": t, "lat": [40.0], "lon": [-100.0]})
    out = nasa_power.monthly_mean_of_daily_cube(da).item()
    assert out == pytest.approx(1000.0 * 15 / 31)          # mean of cubes
    assert out > float(v.mean()) ** 3 * 3                  # far above cube of mean (~125)
