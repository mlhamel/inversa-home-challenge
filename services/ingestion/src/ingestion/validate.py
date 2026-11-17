from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from inversa.v1 import telemetry_pb2 as telemetry

from ingestion.contract import (
    fire_confidence_token,
    fire_id,
    hash16,
    measurement_id,
    quality_flag_token,
    stamp,
)


class ValidationError(ValueError):
    pass


STALE_AFTER: Final[timedelta] = timedelta(hours=2)
PM25_MIN: Final[float] = 0.0
PM25_MAX: Final[float] = 1500.0

_CONFIDENCE_BY_SYMBOL: Final[dict[str, telemetry.FireConfidence]] = {
    "h": telemetry.FIRE_CONFIDENCE_HIGH,
    "high": telemetry.FIRE_CONFIDENCE_HIGH,
    "n": telemetry.FIRE_CONFIDENCE_NOMINAL,
    "nominal": telemetry.FIRE_CONFIDENCE_NOMINAL,
    "l": telemetry.FIRE_CONFIDENCE_LOW,
    "low": telemetry.FIRE_CONFIDENCE_LOW,
}

GRID_DEGREE: Final[float] = 0.25


def _require_timestamps(ingested_at: datetime, observed_at: datetime, label: str) -> None:
    if observed_at.tzinfo is None or ingested_at.tzinfo is None:
        raise ValidationError(f"{label}: timestamps must be timezone-aware UTC")


def _require_finite(value: float, label: str) -> float:
    if value != value or value in (float("inf"), float("-inf")):
        raise ValidationError(f"{label}: value must be finite, got {value!r}")
    return value


def fire_confidence_from_symbol(symbol: str) -> telemetry.FireConfidence:
    token = symbol.strip().lower()
    flagged = _CONFIDENCE_BY_SYMBOL.get(token)
    if flagged is None:
        raise ValidationError(f"FIRMS confidence {symbol!r} outside contract enum bounds")
    return flagged


def detect_fire(
    *,
    observed_at: datetime,
    ingested_at: datetime,
    lat: float,
    lon: float,
    frp: float | None,
    confidence_symbol: str,
    satellite: str,
) -> telemetry.FireDetection:
    _require_timestamps(ingested_at, observed_at, "FireDetection")
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        raise ValidationError(f"FireDetection: coordinates ({lat}, {lon}) out of bounds")
    if not satellite.strip():
        raise ValidationError("FireDetection: satellite must be a non-empty string")
    detection = telemetry.FireDetection()
    detection.observed_at.CopyFrom(stamp(observed_at.astimezone(UTC)))
    detection.ingested_at.CopyFrom(stamp(ingested_at.astimezone(UTC)))
    detection.lat = _require_finite(lat, "FireDetection.lat")
    detection.lon = _require_finite(lon, "FireDetection.lon")
    if frp is not None:
        detection.frp = max(0.0, _require_finite(frp, "FireDetection.frp"))
    detection.confidence = fire_confidence_from_symbol(confidence_symbol)
    detection.satellite = satellite.strip()
    detection.fire_id = fire_id(detection.lat, detection.lon, observed_at)
    fire_confidence_token(detection.confidence)
    return detection


def quality_flag(
    *, ingested_at: datetime, observed_at: datetime, pm25: float | None
) -> tuple[telemetry.QualityFlag, float | None]:
    if pm25 is None:
        return telemetry.QUALITY_FLAG_STALE, None
    _require_finite(pm25, "AirQualityReading.pm25")
    if pm25 < PM25_MIN or pm25 > PM25_MAX:
        return telemetry.QUALITY_FLAG_OUTLIER, None
    if ingested_at - observed_at > STALE_AFTER:
        return telemetry.QUALITY_FLAG_STALE, pm25
    return telemetry.QUALITY_FLAG_VALID, pm25


def air_quality(
    *,
    observed_at: datetime,
    ingested_at: datetime,
    station_id: str,
    station_name: str,
    lat: float,
    lon: float,
    pm25: float | None,
) -> telemetry.AirQualityReading:
    _require_timestamps(ingested_at, observed_at, "AirQualityReading")
    if not station_id.strip():
        raise ValidationError("AirQualityReading: station_id must be a non-empty string")
    flag, stored = quality_flag(ingested_at=ingested_at, observed_at=observed_at, pm25=pm25)
    reading = telemetry.AirQualityReading()
    reading.observed_at.CopyFrom(stamp(observed_at.astimezone(UTC)))
    reading.ingested_at.CopyFrom(stamp(ingested_at.astimezone(UTC)))
    reading.station_id = station_id.strip()
    reading.station_name = station_name.strip()
    reading.lat = _require_finite(lat, "AirQualityReading.lat")
    reading.lon = _require_finite(lon, "AirQualityReading.lon")
    if stored is not None:
        reading.pm25 = stored
    reading.quality_flag = flag
    reading.measurement_id = measurement_id(reading.station_id, observed_at)
    quality_flag_token(reading.quality_flag)
    return reading


def grid_point(lat: float, lon: float) -> tuple[float, float]:
    return round(lat / GRID_DEGREE) * GRID_DEGREE, round(lon / GRID_DEGREE) * GRID_DEGREE


def grid_id(lat: float, lon: float) -> str:
    rounded_lat, rounded_lon = grid_point(lat, lon)
    return hash16(f"{rounded_lat:.2f}_{rounded_lon:.2f}")


def wind_vector(
    *,
    observed_at: datetime,
    ingested_at: datetime,
    lat: float,
    lon: float,
    wind_speed_10m: float,
    wind_direction_10m: float,
    boundary_layer_height: float | None,
) -> telemetry.WindVector:
    _require_timestamps(ingested_at, observed_at, "WindVector")
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        raise ValidationError(f"WindVector: coordinates ({lat}, {lon}) out of bounds")
    _require_finite(wind_speed_10m, "WindVector.wind_speed_10m")
    _require_finite(wind_direction_10m, "WindVector.wind_direction_10m")
    if wind_speed_10m < 0.0 or not 0.0 <= wind_direction_10m < 360.0:
        raise ValidationError(
            f"WindVector: wind_speed_10m={wind_speed_10m} "
            f"wind_direction_10m={wind_direction_10m} out of physical bounds"
        )
    vector = telemetry.WindVector()
    vector.observed_at.CopyFrom(stamp(observed_at.astimezone(UTC)))
    vector.ingested_at.CopyFrom(stamp(ingested_at.astimezone(UTC)))
    vector.lat = grid_point(lat, lon)[0]
    vector.lon = grid_point(lat, lon)[1]
    vector.wind_speed_10m = wind_speed_10m
    vector.wind_direction_10m = wind_direction_10m
    if boundary_layer_height is not None:
        boundary = _require_finite(boundary_layer_height, "boundary_layer_height")
        vector.boundary_layer_height = max(0.0, boundary)
    vector.grid_id = grid_id(lat, lon)
    return vector
