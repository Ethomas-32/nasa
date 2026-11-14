import numpy as np
import pytest
import xarray as xr

from resource_trends import derived


def da(values, units, name="x"):
    return xr.DataArray(np.asarray(values, float), dims=("time",), name=name, attrs={"units": units})


def test_wind_power_density_known_value():
    # Standard atmosphere: 15 C, 101.325 kPa -> rho = 1.2250 kg/m3 ; v=10 -> 0.5*1.225*1000 = 612.5
    out = derived.wind_power_density(da([10.0], "m s-1"), da([15.0], "degC"), da([101.325], "kPa"))
    assert out.values[0] == pytest.approx(612.5, rel=1e-3)
    assert out.attrs["units"] == "W m-2" and out.name == "wind_power_density"
    assert "caveat" in out.attrs


def test_units_are_converted_consistently():
    a = derived.wind_power_density(da([8.0], "m s-1"), da([15.0], "degC"), da([101.325], "kPa"))
    b = derived.wind_power_density(da([8.0], "m/s"), da([288.15], "K"), da([101325.0], "Pa"))
    c = derived.wind_power_density(da([8.0], "m s-1"), da([15.0], "degC"), da([1013.25], "hPa"))
    assert a.values[0] == pytest.approx(b.values[0], rel=1e-9)
    assert a.values[0] == pytest.approx(c.values[0], rel=1e-9)


def test_cubic_dependence_on_speed():
    s = derived.wind_power_density(da([5.0, 10.0], "m s-1"), da([10.0, 10.0], "degC"), da([100.0, 100.0], "kPa"))
    assert s.values[1] / s.values[0] == pytest.approx(8.0)


def test_denser_cold_air_gives_more_power():
    out = derived.wind_power_density(da([8.0, 8.0], "m s-1"), da([-10.0, 30.0], "degC"), da([100.0, 100.0], "kPa"))
    assert out.values[0] > out.values[1]


def test_missing_or_unknown_units_raise():
    no_units = xr.DataArray([10.0], dims=("time",), name="v")
    with pytest.raises(ValueError):
        derived.wind_power_density(no_units, da([15.0], "degC"), da([101.0], "kPa"))
    with pytest.raises(ValueError):
        derived.wind_power_density(da([10.0], "m s-1"), da([15.0], "degF"), da([101.0], "kPa"))
    with pytest.raises(ValueError):
        derived.wind_power_density(da([10.0], "knots"), da([15.0], "degC"), da([101.0], "kPa"))


def test_nan_propagates():
    out = derived.wind_power_density(da([np.nan, 5.0], "m s-1"), da([10.0, 10.0], "degC"), da([100.0, 100.0], "kPa"))
    assert np.isnan(out.values[0]) and np.isfinite(out.values[1])


def test_wind_speed_from_uv():
    out = derived.wind_speed(da([3.0, -6.0], "m s-1"), da([4.0, 8.0], "m s-1"))
    assert out.values.tolist() == [5.0, 10.0]
    assert out.attrs["units"] == "m s-1"


def test_wind_power_density_from_cube_matches_speed_version_for_steady_wind():
    a = derived.wind_power_density(da([10.0], "m s-1"), da([15.0], "degC"), da([101.325], "kPa"))
    b = derived.wind_power_density_from_cube(da([1000.0], "m3 s-3"), da([15.0], "degC"), da([1013.25], "hPa"))
    assert b.values[0] == pytest.approx(a.values[0], rel=1e-9)
    assert b.attrs["units"] == "W m-2"
    with pytest.raises(ValueError):
        derived.wind_power_density_from_cube(da([1000.0], "m s-1"), da([15.0], "degC"), da([1013.25], "hPa"))
