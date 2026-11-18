"""Environment-driven ingestion settings."""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ConfigError(ValueError):
    """Raised when environment configuration is missing or malformed."""


class Settings(BaseModel):
    """Frozen ingestion configuration parsed from the environment."""
    model_config = ConfigDict(frozen=True)

    bbox: tuple[float, float, float, float]
    data_dir: Path
    firms_map_key: str | None
    openaq_api_key: str | None

    @property
    def bbox_str(self) -> str:
        """Return bbox as the comma-joined string FIRMS and OpenAQ query params expect."""
        return ",".join(str(value) for value in self.bbox)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from a mapping (defaults to os.environ)."""
    source = os.environ if env is None else env
    raw = source.get("BBOX", "")
    parts = raw.split(",")
    if len(parts) != 4:
        raise ConfigError(f"BBOX must be 'min_lon,min_lat,max_lon,max_lat', got {raw!r}")
    min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    if not (min_lon < max_lon and min_lat < max_lat):
        raise ConfigError(f"BBOX corners must be ordered min<max, got {raw!r}")
    if not (-180.0 <= min_lon and max_lon <= 180.0 and -90.0 <= min_lat and max_lat <= 90.0):
        raise ConfigError(f"BBOX out of geographic bounds: {raw!r}")
    return Settings(
        bbox=(min_lon, min_lat, max_lon, max_lat),
        data_dir=Path(source.get("DATA_DIR") or "./.local_datalake"),
        firms_map_key=source.get("FIRMS_MAP_KEY") or None,
        openaq_api_key=source.get("OPENAQ_API_KEY") or None,
    )
