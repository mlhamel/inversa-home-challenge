"""Environment-driven ingestion settings."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ConfigError(ValueError):
    """Raised when environment configuration is missing or malformed."""


class Region(BaseModel):
    """One named study area: lowercase id, display label, and ordered bbox corners."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    bbox: tuple[float, float, float, float]

    @property
    def bbox_str(self) -> str:
        """Return bbox as the comma-joined string FIRMS and OpenAQ query params expect."""
        return ",".join(str(value) for value in self.bbox)

    def contains(self, lat: float, lon: float) -> bool:
        """Whether the point falls inside this region, edges inclusive."""
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


class Settings(BaseModel):
    """Frozen ingestion configuration parsed from the environment."""
    model_config = ConfigDict(frozen=True)

    regions: tuple[Region, ...]
    data_dir: Path
    firms_map_key: str | None
    openaq_api_key: str | None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from a mapping (defaults to os.environ)."""
    source = os.environ if env is None else env
    return Settings(
        regions=_parse_regions(source),
        data_dir=Path(source.get("DATA_DIR") or "./.local_datalake"),
        firms_map_key=source.get("FIRMS_MAP_KEY") or None,
        openaq_api_key=source.get("OPENAQ_API_KEY") or None,
    )


def _parse_regions(source: Mapping[str, str]) -> tuple[Region, ...]:
    """Parse REGION_* variables sorted by id; fall back to legacy BBOX as 'default'."""
    raws: dict[str, str] = {}
    labels: dict[str, str] = {}
    for key, value in source.items():
        match = re.fullmatch(r"REGION_([A-Za-z0-9_]+)", key)
        if match is None:
            continue
        name = match.group(1).lower()
        if name.endswith("_label"):
            labels[name[:-6]] = value.strip()
        else:
            raws[name] = value
    for base in labels:
        if base not in raws:
            raise ConfigError(f"REGION_{base.upper()}_LABEL has no matching bbox variable")
    if not raws:
        bbox_raw = source.get("BBOX", "")
        if not bbox_raw.strip():
            raise ConfigError(
                "no study area configured: set REGION_<NAME>='min_lon,min_lat,max_lon,max_lat' "
                "(or legacy BBOX)"
            )
        return (
            Region(
                id="default",
                label="Default",
                bbox=_parse_bbox(bbox_raw, "BBOX"),
            ),
        )
    regions: list[Region] = []
    for region_id in sorted(raws):
        var = f"REGION_{region_id.upper()}"
        if not re.fullmatch(r"[a-z][a-z0-9_]*", region_id):
            raise ConfigError(f"{var} id must be lowercase snake_case, got {region_id!r}")
        label = labels.get(region_id) or region_id.replace("_", " ").title()
        regions.append(Region(id=region_id, label=label, bbox=_parse_bbox(raws[region_id], var)))
    return tuple(regions)


def _parse_bbox(raw: str, var: str) -> tuple[float, float, float, float]:
    """Parse and validate 'min_lon,min_lat,max_lon,max_lat'."""
    parts = raw.split(",")
    if len(parts) != 4:
        raise ConfigError(f"{var} must be 'min_lon,min_lat,max_lon,max_lat', got {raw!r}")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    except ValueError:
        raise ConfigError(f"{var} corners must be numbers, got {raw!r}") from None
    if not (min_lon < max_lon and min_lat < max_lat):
        raise ConfigError(f"{var} corners must be ordered min<max, got {raw!r}")
    if not (-180.0 <= min_lon and max_lon <= 180.0 and -90.0 <= min_lat and max_lat <= 90.0):
        raise ConfigError(f"{var} out of geographic bounds: {raw!r}")
    return (min_lon, min_lat, max_lon, max_lat)
