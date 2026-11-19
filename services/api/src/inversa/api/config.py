"""Environment-driven API settings."""
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


class Settings(BaseModel):
    """Frozen API configuration parsed from the environment."""

    model_config = ConfigDict(frozen=True)

    regions: tuple[Region, ...] = ()
    data_dir: Path
    state_cache_ttl_ms: int = 120_000
    agent_model: str = "openai:gpt-4o-mini"
    agent_base_url: str | None = None
    agent_api_key: str | None = None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from a mapping (defaults to os.environ)."""
    source = os.environ if env is None else env
    raw = source.get("DATA_DIR") or "./.local_datalake"
    return Settings(
        regions=_parse_regions(source),
        data_dir=Path(raw),
        state_cache_ttl_ms=int(source.get("STATE_CACHE_TTL_MS") or "120000"),
        agent_model=source.get("AGENT_MODEL") or "openai:gpt-4o-mini",
        agent_base_url=source.get("AGENT_BASE_URL") or None,
        agent_api_key=source.get("AGENT_API_KEY") or None,
    )


def _parse_regions(source: Mapping[str, str]) -> tuple[Region, ...]:
    """Parse REGION_* variables sorted by id; fall back to legacy BBOX as 'default'.

    Mirrors the ingestion parser so both services agree on region ids and
    labels without sharing code across service boundaries.
    """
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
        if not source.get("BBOX"):
            return ()
        return (
            Region(
                id="default",
                label="Default",
                bbox=_parse_bbox(source.get("BBOX", ""), "BBOX"),
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
