"""Stream + cache cropped series for a region. Usage (PowerShell):
    .\\.venv\\Scripts\\python.exe scripts\\build_cache.py conus solar_irradiance aerosol_optical_depth
Optional: --start 1981-01 --end 2026-12 --workers 4
"""
import argparse
import time

from resource_trends import sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region")
    ap.add_argument("variables", nargs="+")
    ap.add_argument("--start", default=sources.DEFAULT_START)
    ap.add_argument("--end", default=sources.DEFAULT_END)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    for v in a.variables:
        t = time.time()
        kw = {"workers": a.workers}
        da = sources.load(v, a.region, start=a.start, end=a.end, **kw)
        print(f"{v}: {dict(da.sizes)} {str(da.time.values[0])[:7]}..{str(da.time.values[-1])[:7]} "
              f"units={da.attrs['units']} provider={da.attrs['provider']} ({time.time()-t:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
