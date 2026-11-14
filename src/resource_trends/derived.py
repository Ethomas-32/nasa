"""Derived variables computed from base variables (xarray in, xarray out)."""
from __future__ import annotations

import numpy as np
import xarray as xr

R_DRY_AIR = 287.058  # J kg-1 K-1


def _units(da: xr.DataArray) -> str:
    u = da.attrs.get("units")
    if u is None:
        raise ValueError(f"{da.name!r} has no 'units' attribute; refusing to guess")
    return str(u).strip().lower().replace("°", "deg")


def to_kelvin(temp: xr.DataArray) -> xr.DataArray:
    u = _units(temp)
    if u in ("k", "kelvin"):
        return temp
    if u in ("degc", "c", "celsius", "deg_c"):
        return temp + 273.15
    raise ValueError(f"unsupported temperature units {temp.attrs['units']!r}")


def to_pascal(pressure: xr.DataArray) -> xr.DataArray:
    u = _units(pressure)
    factors = {"pa": 1.0, "hpa": 100.0, "mbar": 100.0, "mb": 100.0, "kpa": 1000.0}
    if u not in factors:
        raise ValueError(f"unsupported pressure units {pressure.attrs['units']!r}")
    return pressure * factors[u]


def to_ms(speed: xr.DataArray) -> xr.DataArray:
    u = _units(speed)
    if u in ("m s-1", "m/s", "m s**-1", "ms-1"):
        return speed
    raise ValueError(f"unsupported speed units {speed.attrs['units']!r}")


def wind_speed(u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
    """Speed from eastward/northward components (both must be in m/s)."""
    out = np.hypot(to_ms(u), to_ms(v))
    out.name = "wind_speed"
    out.attrs = {"units": "m s-1"}
    return out


def air_density(temp: xr.DataArray, pressure: xr.DataArray) -> xr.DataArray:
    """Dry-air density rho = p / (R_d * T), kg m-3 (humidity ignored)."""
    return to_pascal(pressure) / (R_DRY_AIR * to_kelvin(temp))


def wind_power_density(speed: xr.DataArray, temp: xr.DataArray, pressure: xr.DataArray) -> xr.DataArray:
    """Wind power density proxy 0.5 * rho * v^3 in W m-2.

    CAVEAT: if `speed` is a time mean (e.g. monthly), v^3 of the mean is lower than the mean of v^3,
    so this underestimates the true mean power density. It is a proxy for trend analysis.
    """
    out = 0.5 * air_density(temp, pressure) * to_ms(speed) ** 3
    out.name = "wind_power_density"
    out.attrs = {
        "units": "W m-2",
        "long_name": "Wind power density proxy (0.5*rho*v^3, dry air)",
        "caveat": "computed from time-mean speed; underestimates mean power density",
    }
    return out


DERIVED_FUNCTIONS = {
    "wind_power_density": wind_power_density,
}
