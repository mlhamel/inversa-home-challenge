from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from inversa.ingestion.config import Settings, load_settings
from samples import RUN_AT, TEST_BBOX


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return load_settings(
        {
            "BBOX": TEST_BBOX,
            "DATA_DIR": str(tmp_path),
            "FIRMS_MAP_KEY": "test-map-key",
            "OPENAQ_API_KEY": "test-openaq-key",
        }
    )


@pytest.fixture
def run_at() -> datetime:
    return RUN_AT
