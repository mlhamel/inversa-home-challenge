"""Environment-driven API settings."""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    """Frozen API configuration parsed from the environment."""
    model_config = ConfigDict(frozen=True)

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
        data_dir=Path(raw),
        state_cache_ttl_ms=int(source.get("STATE_CACHE_TTL_MS") or "120000"),
        agent_model=source.get("AGENT_MODEL") or "openai:gpt-4o-mini",
        agent_base_url=source.get("AGENT_BASE_URL") or None,
        agent_api_key=source.get("AGENT_API_KEY") or None,
    )
