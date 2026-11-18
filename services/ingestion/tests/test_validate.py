from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from inversa.ingestion.contract import hash16
from inversa.ingestion.validate import (
    ValidationError,
    air_quality,
    detect_fire,
    grid_id,
    grid_point,
    quality_flag,
    wind_vector,
)
from inversa.v1 import telemetry_pb2 as telemetry
from samples import RUN_AT


def test_quality_flag_valid_within_two_hours() -> None:
    assert quality_flag(
        ingested_at=RUN_AT, observed_at=_observed(timedelta(hours=1)), pm25=9.0
    ) == (
        telemetry.QUALITY_FLAG_VALID,
        9.0,
    )


def test_quality_flag_valid_at_exact_bound() -> None:
    assert quality_flag(
        ingested_at=RUN_AT, observed_at=_observed(timedelta(hours=2)), pm25=9.0
    ) == (
        telemetry.QUALITY_FLAG_VALID,
        9.0,
    )


def test_quality_flag_stale_keeps_value() -> None:
    assert quality_flag(
        ingested_at=RUN_AT, observed_at=_observed(timedelta(hours=3)), pm25=9.0
    ) == (
        telemetry.QUALITY_FLAG_STALE,
        9.0,
    )


def test_quality_flag_missing_value_is_stale() -> None:
    assert quality_flag(
        ingested_at=RUN_AT, observed_at=_observed(timedelta(minutes=1)), pm25=None
    ) == (
        telemetry.QUALITY_FLAG_STALE,
        None,
    )


@pytest.mark.parametrize("pm25", [-1.5, 1501.0])
def test_quality_flag_outlier_nulls_value(pm25: float) -> None:
    assert quality_flag(
        ingested_at=RUN_AT, observed_at=_observed(timedelta(hours=1)), pm25=pm25
    ) == (
        telemetry.QUALITY_FLAG_OUTLIER,
        None,
    )


def test_quality_flag_pm25_max_is_within_bounds() -> None:
    assert quality_flag(
        ingested_at=RUN_AT, observed_at=_observed(timedelta(hours=1)), pm25=1500.0
    ) == (
        telemetry.QUALITY_FLAG_VALID,
        1500.0,
    )


def test_air_quality_valid_reading() -> None:
    observed = _observed(timedelta(hours=1))
    reading = _reading(observed_at=observed)
    assert reading.quality_flag == telemetry.QUALITY_FLAG_VALID
    assert reading.pm25 == pytest.approx(9.0)
    assert reading.station_id == "2009"
    assert reading.station_name == "San Francisco"
    assert reading.measurement_id == f"2009_{observed.isoformat()}"


def test_air_quality_outlier_kept_with_null_pm25() -> None:
    reading = _reading(pm25=9999.0)
    assert reading.quality_flag == telemetry.QUALITY_FLAG_OUTLIER
    assert not reading.HasField("pm25")


def test_air_quality_stale_retains_pm25() -> None:
    reading = _reading(observed_at=_observed(timedelta(hours=5)))
    assert reading.quality_flag == telemetry.QUALITY_FLAG_STALE
    assert reading.pm25 == pytest.approx(9.0)


def test_air_quality_requires_station_id() -> None:
    with pytest.raises(ValidationError, match="station_id"):
        _reading(station_id="   ")


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("h", telemetry.FIRE_CONFIDENCE_HIGH),
        ("HIGH", telemetry.FIRE_CONFIDENCE_HIGH),
        ("n", telemetry.FIRE_CONFIDENCE_NOMINAL),
        ("l", telemetry.FIRE_CONFIDENCE_LOW),
    ],
)
def test_detect_fire_confidence_symbols(symbol: str, expected: int) -> None:
    detection = _fire(confidence_symbol=symbol)
    assert detection.confidence == expected
    assert len(detection.fire_id) == 16


def test_detect_fire_passthroughs() -> None:
    detection = _fire(satellite="  VIIRS_SNPP_NRT ")
    assert detection.frp == pytest.approx(8.4)
    assert detection.lat == pytest.approx(38.5816)
    assert detection.satellite == "VIIRS_SNPP_NRT"
    stamp = detection.observed_at.ToDatetime().replace(microsecond=0).isoformat()
    assert stamp == "2026-11-17T16:30:00"


def test_detect_fire_null_and_clamped_frp() -> None:
    assert not _fire(frp=None).HasField("frp")
    assert _fire(frp=-3.0).frp == 0.0


def test_detect_fire_unknown_confidence_symbol() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        _fire(confidence_symbol="x")


@pytest.mark.parametrize("coords", [(95.0, 0.0), (0.0, -200.0)])
def test_detect_fire_coordinate_bounds(coords: tuple[float, float]) -> None:
    with pytest.raises(ValidationError, match="coordinates"):
        _fire(lat=coords[0], lon=coords[1])


def test_detect_fire_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _fire(ingested_at=datetime(2026, 11, 17, 18, 0))


def test_grid_point_rounds_to_quarter_degree() -> None:
    assert grid_point(37.7658, -122.3978) == (37.75, -122.5)
    assert grid_point(38.5816, -121.4944) == (38.5, -121.5)


def test_grid_id_hashes_formatted_cell() -> None:
    assert grid_id(37.7658, -122.3978) == hash16("37.75_-122.50")


def test_wind_vector_snaps_to_grid_and_keeps_raw_values() -> None:
    vector = wind_vector(
        observed_at=_observed(timedelta(hours=1)),
        ingested_at=RUN_AT,
        lat=37.7658,
        lon=-122.3978,
        wind_speed_10m=6.0,
        wind_direction_10m=180.0,
        boundary_layer_height=510.0,
    )
    assert vector.lat == pytest.approx(37.75)
    assert vector.lon == pytest.approx(-122.5)
    assert vector.wind_speed_10m == pytest.approx(6.0)
    assert vector.wind_direction_10m == pytest.approx(180.0)
    assert vector.grid_id == hash16("37.75_-122.50")


def test_wind_vector_null_and_negative_boundary_layer() -> None:
    base: dict[str, Any] = {
        "observed_at": _observed(timedelta(hours=1)),
        "ingested_at": RUN_AT,
        "lat": 37.75,
        "lon": -122.5,
        "wind_speed_10m": 6.0,
        "wind_direction_10m": 180.0,
    }
    assert not wind_vector(**base, boundary_layer_height=None).HasField("boundary_layer_height")
    assert wind_vector(**base, boundary_layer_height=-5.0).boundary_layer_height == 0.0


@pytest.mark.parametrize(
    "overrides",
    [{"wind_speed_10m": -1.0}, {"wind_direction_10m": 360.0}, {"wind_direction_10m": -10.0}],
)
def test_wind_vector_rejects_physics_bounds(overrides: dict[str, float]) -> None:
    kwargs: dict[str, Any] = {
        "observed_at": _observed(timedelta(hours=1)),
        "ingested_at": RUN_AT,
        "lat": 37.75,
        "lon": -122.5,
        "wind_speed_10m": 6.0,
        "wind_direction_10m": 180.0,
        "boundary_layer_height": None,
    }
    kwargs.update(overrides)
    with pytest.raises(ValidationError, match="physical bounds"):
        wind_vector(**kwargs)


def _observed(lag: timedelta) -> datetime:
    return RUN_AT - lag


def _fire(**overrides: Any) -> telemetry.FireDetection:
    kwargs: dict[str, Any] = {
        "observed_at": _observed(timedelta(minutes=90)),
        "ingested_at": RUN_AT,
        "lat": 38.5816,
        "lon": -121.4944,
        "frp": 8.4,
        "confidence_symbol": "h",
        "satellite": "VIIRS_SNPP_NRT",
    }
    kwargs.update(overrides)
    return detect_fire(**kwargs)


def _reading(**overrides: Any) -> telemetry.AirQualityReading:
    kwargs: dict[str, Any] = {
        "observed_at": _observed(timedelta(hours=1)),
        "ingested_at": RUN_AT,
        "station_id": "2009",
        "station_name": "San Francisco",
        "lat": 37.7658,
        "lon": -122.3978,
        "pm25": 9.0,
    }
    kwargs.update(overrides)
    return air_quality(**kwargs)
