"""Export contract: build a full synthetic export end to end and validate every file; validate the
real CONUS export if it has been built."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from resource_trends import alerts, export, pipeline, portfolio
from resource_trends.registry import Registry
from test_stats import make_field

REG = Registry.load()
VARS = ["solar_irradiance", "precipitation", "wind_power_density", "runoff"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("export")
    da, truth = make_field(seed=31, n_years=40)          # 1984-2023, west +, east -, NaN block

    def loader(variable, region, registry, start, end, **kw):
        x = da.sel(time=slice(start, end)).copy()
        x.name = variable
        x.attrs = {"units": REG.variables[variable]["units"], "provider": "synthetic", "dataset": "unit-test",
                   "product_type": "model"}
        return x

    pipeline.run_all("conus", 1985, 2020, registry=REG, loader=loader, out_dir=out, variables=VARS,
                     seasons=("JJA",), apply_mask=False)
    portfolio.run("conus", "1985-01", "2020-12", registry=REG, loader=loader, out_dir=out, apply_mask=False)
    alerts.run("conus", REG, loader=loader, out_dir=out, variables=VARS, today=pd.Timestamp("2026-11-15"), apply_mask=False)
    cat = export.build("conus", out, REG, loader=loader, apply_mask=False)
    return out, cat, truth


def test_build_is_valid_and_complete(built):
    out, cat, _ = built
    assert export.validate_export(out) == []
    assert {v["name"] for v in cat["variables"]} == set(VARS)
    assert set(cat["files"]) >= {"run_all", "narrative", "portfolio", "alerts"}
    solar = next(v for v in cat["variables"] if v["name"] == "solar_irradiance")
    assert solar["annual"]["trend_png"] == "solar_irradiance.trend.png" and "JJA" in solar["seasons"]
    assert solar["theme"] == "atmospheric_chemistry" and solar["provider"] == "synthetic"
    assert "no forecasts" in " ".join(cat["disclaimers"]).lower()


def test_png_orientation_colors_and_alpha(built):
    out, cat, truth = built
    for name, positive in (("solar_irradiance", "red"), ("precipitation", "blue")):
        v = next(x for x in cat["variables"] if x["name"] == name)
        leg = v["annual"]["legend"]
        assert leg["positive_color"] == positive
        img = np.array(Image.open(out / v["annual"]["trend_png"]))
        h, w, _ = img.shape
        assert (w, h) == (leg["width"], leg["height"])
        # west third has a significant POSITIVE trend: red for solar, blue for water variables
        px = img[h // 2, 2]
        assert px[3] == 255
        assert (px[0] > px[2]) if positive == "red" else (px[2] > px[0])
        # east third negative: opposite colour
        px = img[h // 2, w - 3]
        assert (px[2] > px[0]) if positive == "red" else (px[0] > px[2])
        # NaN block sits at the SOUTH edge (rows 0-4 of the ascending-lat grid) -> bottom rows, transparent
        assert img[h - 1, 20, 3] == 0 and img[0, 20, 3] > 0
        # some non-significant cells in the null middle are faded, not hidden
        mid = img[: h - 6, w // 3 + 2: 2 * w // 3 - 2, 3]
        assert (mid == round(255 * export.NONSIG_ALPHA)).any()
        b = leg["bounds"]
        assert b["south"] < 30 and b["north"] > 49 and b["west"] < -120 and b["east"] > -75


def test_pixel_series_round_trip(built):
    out, cat, _ = built
    v = next(x for x in cat["variables"] if x["name"] == "precipitation")
    ps = v["annual"]["pixel_series"]
    tile = json.loads((out / "pixel_series" / ps["dir"] / ps["tiles"][0]).read_text())
    assert tile["years"][0] == 1985 and tile["years"][-1] == 2020 and len(tile["cells"]) > 0
    c = tile["cells"][0]
    assert tile["tile"]["south"] <= c["lat"] < tile["tile"]["south"] + 5
    assert len(c["values"]) == len(tile["years"])


def test_narrative_is_built_from_the_numbers(built):
    out, _, _ = built
    nar = json.loads((out / "narrative.json").read_text())
    ids = {s["id"] for s in nar["sentences"]}
    assert {"solar_irradiance.regional", "solar_irradiance.opposing", "portfolio.joint_low"} <= ids
    s = next(x for x in nar["sentences"] if x["id"] == "solar_irradiance.regional")
    summ = json.loads((out / "solar_irradiance.summary.json").read_text())
    assert f"{summ['area_frac_sig_up']:.0%}" in s["text"] and s["numbers"]["p"] == summ["regional"]["p_value"]
    assert "forecast" not in " ".join(x["text"] for x in nar["sentences"] if x["topic"] != "alerts").lower()
    for a in (x for x in nar["sentences"] if x["topic"] == "alerts"):
        assert "anomaly, not forecast" in a["text"]


def test_validation_catches_problems(built, tmp_path):
    import shutil
    out, _, _ = built
    bad = tmp_path / "bad"
    shutil.copytree(out, bad)
    (bad / "precipitation.trend.png").unlink()
    a = json.loads((bad / "alerts.json").read_text())
    a["label"] = "forecast"
    (bad / "alerts.json").write_text(json.dumps(a))
    problems = export.validate_export(bad)
    assert any("precipitation.trend.png" in p for p in problems)
    assert any("alerts.json" in p for p in problems)


REAL = Path(__file__).resolve().parents[1] / "export" / "conus"


@pytest.mark.skipif(not (REAL / "catalog.json").exists(), reason="real CONUS export not built")
def test_real_conus_export_validates():
    assert export.validate_export(REAL) == []
