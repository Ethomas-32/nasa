import copy

import pytest

from resource_trends.registry import NoProviderError, Registry, RegistryError


@pytest.fixture(scope="module")
def reg():
    return Registry.load()


def test_config_loads_and_every_variable_is_tagged(reg):
    assert {"solar", "wind", "hydro"} <= {v["resource"] for v in reg.variables.values()}
    assert set(reg.regions) >= {"conus", "africa", "global"}
    for v in reg.variables.values():
        assert v["audience"] and v["theme"]


def test_all_four_competition_themes_are_covered(reg):
    assert {v["theme"] for v in reg.variables.values()} == {
        "hydrology", "cryosphere", "atmospheric_dynamics", "atmospheric_chemistry"}


def test_nothing_is_marked_verified_before_phase_2(reg):
    assert all(v["status"] == "unverified" for v in reg.variables.values())


def test_select_by_resource_audience_theme(reg):
    assert "wind_power_density" in reg.select(resource="wind")
    assert "pdsi" in reg.select(audience="agriculture")
    assert reg.select(theme="cryosphere") == ["snow_water_equivalent"]


def test_conus_prefers_regional_product_where_available(reg):
    assert reg.resolve("conus", "snow_water_equivalent").provider == "daymet"
    assert reg.resolve("conus", "precipitation").provider == "nclimgrid"
    assert reg.resolve("conus", "runoff").provider == "terraclimate"


def test_global_only_forces_global_product(reg):
    assert reg.resolve("conus", "precipitation", global_only=True).provider == "terraclimate"
    with pytest.raises(NoProviderError):
        reg.resolve("conus", "snow_water_equivalent", global_only=True)


def test_africa_has_no_conus_only_products(reg):
    assert reg.resolve("africa", "precipitation").provider == "terraclimate"
    with pytest.raises(NoProviderError):
        reg.resolve("africa", "snow_water_equivalent")
    avail = reg.availability("africa")
    assert avail["snow_water_equivalent"] is None and avail["runoff"] is not None


def test_derived_variable_resolves_inputs(reg):
    r = reg.resolve("conus", "wind_power_density")
    assert r.provider == "derived" and r.function == "wind_power_density"
    assert set(r.inputs) == {"wind_speed_50m", "air_temp_2m", "surface_pressure"}
    assert r.inputs["wind_speed_50m"].provider == "nasa_power"
    assert r.status == "unverified"


def test_unknown_names_raise_keyerror(reg):
    with pytest.raises(KeyError):
        reg.resolve("mars", "runoff")
    with pytest.raises(KeyError):
        reg.resolve("conus", "nope")


def test_adding_a_region_is_config_only(reg):
    regions = copy.deepcopy(reg.regions)
    regions["alps"] = {
        "bbox": {"lat_min": 43.0, "lat_max": 48.0, "lon_min": 5.0, "lon_max": 17.0},
        "coverage_tags": ["global"],
        "provider_preference": ["terraclimate"],
    }
    r2 = Registry(reg.variables, regions)
    assert r2.resolve("alps", "runoff").provider == "terraclimate"


@pytest.mark.parametrize("mutate", [
    lambda v: v["runoff"].update(theme="vibes"),
    lambda v: v["runoff"].update(resource="coal"),
    lambda v: v["runoff"].update(audience=[]),
    lambda v: v["runoff"].update(aggregation="median"),
    lambda v: v["runoff"].update(status="maybe"),
    lambda v: v["runoff"].update(derived={"function": "wind_power_density", "inputs": []}),  # both defined
    lambda v: v["wind_power_density"]["derived"].update(function="nope"),
    lambda v: v["wind_power_density"]["derived"].update(inputs=["missing_var"]),
    lambda v: v["runoff"]["providers"][0].update(coverage=[]),
])
def test_invalid_config_is_rejected(reg, mutate):
    variables = copy.deepcopy(reg.variables)
    mutate(variables)
    with pytest.raises(RegistryError):
        Registry(variables, reg.regions)
