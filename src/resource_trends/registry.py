"""Load config and resolve which provider serves each (region, variable)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .derived import DERIVED_FUNCTIONS

THEMES = {"hydrology", "cryosphere", "atmospheric_dynamics", "atmospheric_chemistry"}
RESOURCES = {"solar", "wind", "hydro", "none"}
AUDIENCES = {"energy", "agriculture"}
AGGREGATIONS = {"sum", "mean", "max"}
STATUSES = {"unverified", "verified"}

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class RegistryError(ValueError):
    pass


class NoProviderError(LookupError):
    pass


@dataclass(frozen=True)
class Resolution:
    variable: str
    region: str
    provider: str                      # provider name, or "derived"
    spec: dict                         # the matching provider entry (empty for derived)
    status: str
    inputs: dict = field(default_factory=dict)   # derived: input name -> Resolution
    function: str | None = None


class Registry:
    def __init__(self, variables: dict, regions: dict):
        self.variables = variables
        self.regions = regions
        self._validate()

    @classmethod
    def load(cls, config_dir=None) -> "Registry":
        d = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        variables = yaml.safe_load((d / "variables.yaml").read_text(encoding="utf-8"))["variables"]
        regions = yaml.safe_load((d / "regions.yaml").read_text(encoding="utf-8"))["regions"]
        return cls(variables, regions)

    # --- validation -----------------------------------------------------------------------------
    def _validate(self):
        for name, v in self.variables.items():
            def bad(msg):
                raise RegistryError(f"variable {name!r}: {msg}")

            if v.get("theme") not in THEMES:
                bad(f"theme must be one of {sorted(THEMES)}")
            if v.get("resource") not in RESOURCES:
                bad(f"resource must be one of {sorted(RESOURCES)}")
            aud = v.get("audience")
            if not aud or not set(aud) <= AUDIENCES:
                bad(f"audience must be a non-empty subset of {sorted(AUDIENCES)}")
            if v.get("aggregation") not in AGGREGATIONS:
                bad(f"aggregation must be one of {sorted(AGGREGATIONS)}")
            if v.get("status") not in STATUSES:
                bad(f"status must be one of {sorted(STATUSES)}")
            if not isinstance(v.get("relative"), bool):
                bad("relative must be true/false")
            if not v.get("units"):
                bad("units required")
            has_p, has_d = bool(v.get("providers")), "derived" in v
            if has_p == has_d:
                bad("define exactly one of providers / derived")
            for p in v.get("providers", []):
                if not p.get("provider") or not p.get("coverage"):
                    bad("each provider needs a name and a non-empty coverage list")
            if has_d:
                fn = v["derived"].get("function")
                if fn not in DERIVED_FUNCTIONS:
                    bad(f"unknown derived function {fn!r}")
                for inp in v["derived"].get("inputs", []):
                    if inp not in self.variables:
                        bad(f"derived input {inp!r} is not a variable")
                    if "derived" in self.variables[inp]:
                        bad(f"derived input {inp!r} is itself derived (not supported)")
        for res in ("solar", "wind", "hydro"):
            prim = [n for n, v in self.variables.items() if v.get("primary") and v["resource"] == res]
            if len(prim) > 1:
                raise RegistryError(f"resource {res!r} has more than one primary index: {prim}")
        for rname, r in self.regions.items():
            b = r.get("bbox", {})
            if not (-90 <= b.get("lat_min", 99) < b.get("lat_max", -99) <= 90):
                raise RegistryError(f"region {rname!r}: bad latitude range")
            if not (-180 <= b.get("lon_min", 999) < b.get("lon_max", -999) <= 180):
                raise RegistryError(f"region {rname!r}: bad longitude range")
            if not r.get("coverage_tags") or not r.get("provider_preference"):
                raise RegistryError(f"region {rname!r}: coverage_tags and provider_preference required")

    # --- queries --------------------------------------------------------------------------------
    def primary_index(self, resource: str) -> str:
        for name, v in self.variables.items():
            if v.get("primary") and v["resource"] == resource:
                return name
        raise KeyError(f"no primary index for resource {resource!r}")

    def select(self, resource=None, audience=None, theme=None) -> list[str]:
        out = []
        for name, v in self.variables.items():
            if resource and v["resource"] != resource:
                continue
            if audience and audience not in v["audience"]:
                continue
            if theme and v["theme"] != theme:
                continue
            out.append(name)
        return out

    def resolve(self, region: str, variable: str, global_only: bool = False) -> Resolution:
        """Best provider for (region, variable): first entry in the region's provider_preference
        whose coverage intersects the region's tags. global_only restricts to providers tagged
        `global`, for cross-region comparison. Derived variables resolve each input the same way."""
        if region not in self.regions:
            raise KeyError(f"unknown region {region!r}")
        if variable not in self.variables:
            raise KeyError(f"unknown variable {variable!r}")
        v = self.variables[variable]
        if "derived" in v:
            inputs = {i: self.resolve(region, i, global_only) for i in v["derived"]["inputs"]}
            status = "verified" if v["status"] == "verified" and all(
                r.status == "verified" for r in inputs.values()) else "unverified"
            return Resolution(variable, region, "derived", {}, status, inputs, v["derived"]["function"])

        reg = self.regions[region]
        tags = set(reg["coverage_tags"])
        if global_only:
            tags = tags & {"global"}
        candidates = [p for p in v["providers"] if set(p["coverage"]) & tags]
        for pname in reg["provider_preference"]:
            for p in candidates:
                if p["provider"] == pname:
                    return Resolution(variable, region, pname, dict(p), v["status"])
        raise NoProviderError(
            f"no provider for variable {variable!r} in region {region!r}"
            + (" (global products only)" if global_only else "")
        )

    def availability(self, region: str, global_only: bool = False) -> dict[str, Resolution | None]:
        """Every variable -> its Resolution, or None where the region has no provider."""
        out = {}
        for name in self.variables:
            try:
                out[name] = self.resolve(region, name, global_only)
            except NoProviderError:
                out[name] = None
        return out
