"""Emit the complete export contract for a region (CLAUDE.md section 7), from cached data.
    .\\.venv\\Scripts\\python.exe scripts\\build_export.py conus
    .\\.venv\\Scripts\\python.exe scripts\\build_export.py conus --skip-validation --start 1981 --end 2020
Steps: run_all (annual + seasons) -> portfolio -> alerts -> station validation -> PNGs, pixel series,
narrative, catalog -> schema validation of every file.
"""
import argparse
import time
from pathlib import Path

import pandas as pd

from resource_trends import alerts, export, pipeline, portfolio, validate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region")
    ap.add_argument("--start", type=int, default=1981)
    ap.add_argument("--end", type=int, default=2020)
    ap.add_argument("--out", default=None)
    ap.add_argument("--skip-validation", action="store_true", help="skip NOAA station validation (needs network once)")
    a = ap.parse_args()
    out = Path(a.out or f"export/{a.region}")
    t0 = time.time()

    def step(name, fn):
        t = time.time()
        r = fn()
        print(f"[{time.time() - t0:6.0f}s] {name} done ({time.time() - t:.0f}s)", flush=True)
        return r

    idx = step("trends (run_all)", lambda: pipeline.run_all(a.region, a.start, a.end, out_dir=out))
    for f in idx["failures"]:
        print("   FAILED:", f["variable"], f["season"], f["error"])
    step("portfolio", lambda: portfolio.run(a.region, f"{a.start}-01", f"{a.end}-12", out_dir=out))
    step("alerts", lambda: alerts.run(a.region, out_dir=out, today=pd.Timestamp.today().normalize()))
    if not a.skip_validation and a.region == "conus":
        step("station validation", lambda: validate.run(a.region, out_dir=out))
    cat = step("export + schema validation", lambda: export.build(a.region, out))
    n_files = sum(1 for _ in out.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    print(f"export OK: {len(cat['variables'])} variables, {n_files} files, {size:.0f} MB in {out}")


if __name__ == "__main__":
    main()
