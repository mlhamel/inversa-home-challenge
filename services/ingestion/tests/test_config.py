from __future__ import annotations

from pathlib import Path

import pytest
from inversa.ingestion.config import ConfigError, Region, load_settings


def test_load_settings_falls_back_to_legacy_bbox(tmp_path: Path) -> None:
    settings = load_settings({"BBOX": "-124.4,36.0,-115.4,42.0", "DATA_DIR": str(tmp_path)})

    assert len(settings.regions) == 1
    region = settings.regions[0]
    assert (region.id, region.label) == ("default", "Default")
    assert region.bbox == (-124.4, 36.0, -115.4, 42.0)
    assert region.bbox_str == "-124.4,36.0,-115.4,42.0"


def test_load_settings_parses_region_vars_sorted_with_labels(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "DATA_DIR": str(tmp_path),
            "REGION_CALIFORNIA": "-124.4,36.0,-115.4,42.0",
            "REGION_NW_INDIA": "74.0,28.2,77.8,31.5",
            "REGION_NW_INDIA_LABEL": "Punjab-Haryana-Delhi NCR",
        }
    )

    assert [region.id for region in settings.regions] == ["california", "nw_india"]
    assert [region.label for region in settings.regions] == [
        "California",
        "Punjab-Haryana-Delhi NCR",
    ]


def test_load_settings_rejects_label_without_bbox(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="_LABEL has no matching bbox"):
        load_settings({"DATA_DIR": str(tmp_path), "REGION_CALIFORNIA_LABEL": "California"})


def test_load_settings_rejects_missing_study_area(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"no study area configured: set REGION_"):
        load_settings({"DATA_DIR": str(tmp_path)})


def test_load_settings_rejects_invalid_region_id(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="lowercase snake_case"):
        load_settings(
            {"DATA_DIR": str(tmp_path), "REGION_9BAD_ID": "-124.4,36.0,-115.4,42.0"}
        )


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ("-124.4,36.0,-115.4", "min_lon,min_lat,max_lon,max_lat"),
        ("abc,36.0,-115.4,42.0", "corners must be numbers"),
        ("-115.4,36.0,-124.4,42.0", "ordered min<max"),
        ("-200.0,36.0,-115.4,42.0", "geographic bounds"),
    ],
)
def test_load_settings_rejects_bad_bbox(tmp_path: Path, raw: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        load_settings(
            {"DATA_DIR": str(tmp_path), "REGION_CALIFORNIA": raw},
        )


def test_region_contains_is_edge_inclusive() -> None:
    region = Region(id="x", label="X", bbox=(-125.0, 35.0, -115.0, 42.0))

    assert region.contains(35.0, -125.0)
    assert region.contains(41.9, -115.1)
    assert not region.contains(42.1, -120.0)
    assert not region.contains(36.0, -114.9)
