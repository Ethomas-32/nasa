"""One loader per data provider (CLAUDE.md section 5). Entry point: `load(...)`.

All heavy sources are STREAMED and cropped; only the region's cropped series is cached under
data/cache/ (git-ignored). Re-running only fetches months not already cached.
"""
from __future__ import annotations

from pathlib import Path

from .. import derived
from ..registry import Registry
from . import _common as C

DEFAULT_START, DEFAULT_END = "1981-01", "2020-12"   # tentative common period; see docs/sources.md


def _provider_loader(provider: str, spec: dict):
    from . import merra2, nasa_power, planetary
    if provider == "merra2":
        return merra2.load
    if provider == "nasa_power":
        return nasa_power.load
    if provider == "terraclimate":
        return planetary.load_terraclimate
    if provider == "daymet":
        return planetary.load_daymet
    if provider == "nclimgrid":
        from . import nclimgrid
        return nclimgrid.load
    raise NotImplementedError(f"no loader for provider {provider!r}")


def load(variable: str, region: str, registry: Registry | None = None, start: str = DEFAULT_START,
         end: str = DEFAULT_END, cache_dir=None, global_only: bool = False, **kw):
    """Load `variable` for `region` following the loader contract. Derived variables are computed from
    their (cached) inputs. Extra kwargs (e.g. workers=) go to the provider loader."""
    reg = registry or Registry.load()
    res = reg.resolve(region, variable, global_only=global_only)
    vdef = reg.variables[variable]
    rdef = reg.regions[region]
    cache_dir = Path(cache_dir) if cache_dir else C.DEFAULT_CACHE

    if res.provider == "derived":
        ins = {n: load(n, region, reg, start, end, cache_dir, global_only, **kw) for n in res.inputs}
        fn = derived.DERIVED_FUNCTIONS[res.function]
        a = [ins[n] for n in vdef["derived"]["inputs"]]
        out = fn(*a)
        out.attrs.update(provider="derived:" + "+".join(sorted({i.attrs["provider"] for i in ins.values()})),
                         units=vdef["units"])
        out.name = variable
        return out.transpose("time", "lat", "lon")

    spec = res.spec
    months = C.month_index(max(start, spec["period"][0]), min(end, spec["period"][1]))
    target = rdef.get("analysis_deg")
    path = cache_dir / f"{spec['provider']}_{variable}_{region}_{target or 'native'}.nc"
    return _provider_loader(res.provider, spec)(variable, vdef["units"], spec, rdef["bbox"], months, path,
                                                target_deg=target, **kw)
