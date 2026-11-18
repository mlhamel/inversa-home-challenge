"""Proto-to-Polars contract: schemas, stable IDs, and row encoding."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Final

import polars as pl
from google.protobuf import timestamp_pb2
from inversa.v1 import telemetry_pb2 as telemetry


class ContractError(ValueError):
    """Raised when a payload or enum value violates the contract."""


DATETIME: Final = pl.Datetime("us", "UTC")


FIRES_SCHEMA: Final[pl.Schema] = pl.Schema({
    "fire_id": pl.String(),
    "observed_at": DATETIME,
    "ingested_at": DATETIME,
    "lat": pl.Float64(),
    "lon": pl.Float64(),
    "frp": pl.Float32(),
    "confidence": pl.String(),
    "satellite": pl.String(),
})


AIR_QUALITY_SCHEMA: Final[pl.Schema] = pl.Schema({
    "measurement_id": pl.String(),
    "station_id": pl.String(),
    "station_name": pl.String(),
    "observed_at": DATETIME,
    "ingested_at": DATETIME,
    "lat": pl.Float64(),
    "lon": pl.Float64(),
    "pm25": pl.Float32(),
    "quality_flag": pl.String(),
})


WEATHER_SCHEMA: Final[pl.Schema] = pl.Schema({
    "grid_id": pl.String(),
    "observed_at": DATETIME,
    "ingested_at": DATETIME,
    "lat": pl.Float64(),
    "lon": pl.Float64(),
    "wind_speed_10m": pl.Float32(),
    "wind_direction_10m": pl.Float32(),
    "boundary_layer_height": pl.Float32(),
})


def stamp(moment: datetime) -> timestamp_pb2.Timestamp:
    """Convert a UTC datetime into a Protobuf Timestamp."""
    value = timestamp_pb2.Timestamp()
    value.FromDatetime(moment)
    return value


def hash16(text: str) -> str:
    """Return the leading 16 hex chars of SHA-256 for stable IDs."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def fire_id(lat: float, lon: float, observed_at: datetime) -> str:
    """Deterministic fire ID from location and observation time."""
    iso = observed_at.astimezone(UTC).isoformat()
    return hash16(f"{lat:.4f}_{lon:.4f}_{iso}")


def measurement_id(station_id: str, observed_at: datetime) -> str:
    """Station-scoped measurement ID with UTC ISO timestamp."""
    iso = observed_at.astimezone(UTC).isoformat()
    return f"{station_id}_{iso}"


def fire_confidence_token(value: int) -> str:
    """Map a FireConfidence enum to its schema token; ContractError on unknown values."""
    token = _FIRE_CONFIDENCE_TOKENS.get(value)
    if token is None:
        raise ContractError(f"FireConfidence value {value} is out of contract bounds")
    return token


def quality_flag_token(value: int) -> str:
    """Map a QualityFlag enum to its schema token; ContractError on unknown values."""
    token = _QUALITY_FLAG_TOKENS.get(value)
    if token is None:
        raise ContractError(f"QualityFlag value {value} is out of contract bounds")
    return token


def fire_rows(detections: Iterable[telemetry.FireDetection]) -> pl.DataFrame:
    """Encode FireDetection messages into a FIRES_SCHEMA DataFrame."""
    rows = []
    for detection in detections:
        if not detection.HasField("observed_at") or not detection.HasField("ingested_at"):
            raise ContractError(f"FireDetection {detection.fire_id!r}: timestamps not set")
        rows.append(
            (
                detection.fire_id,
                detection.observed_at.ToDatetime(tzinfo=UTC),
                detection.ingested_at.ToDatetime(tzinfo=UTC),
                detection.lat,
                detection.lon,
                detection.frp if detection.HasField("frp") else None,
                fire_confidence_token(detection.confidence),
                detection.satellite,
            )
        )
    return pl.DataFrame(rows, schema=FIRES_SCHEMA, orient="row")


def air_quality_rows(readings: Iterable[telemetry.AirQualityReading]) -> pl.DataFrame:
    """Encode AirQualityReading messages into an AIR_QUALITY_SCHEMA DataFrame."""
    rows = []
    for reading in readings:
        if not reading.HasField("observed_at") or not reading.HasField("ingested_at"):
            raise ContractError(f"AirQualityReading {reading.measurement_id!r}: timestamps not set")
        rows.append(
            (
                reading.measurement_id,
                reading.station_id,
                reading.station_name,
                reading.observed_at.ToDatetime(tzinfo=UTC),
                reading.ingested_at.ToDatetime(tzinfo=UTC),
                reading.lat,
                reading.lon,
                reading.pm25 if reading.HasField("pm25") else None,
                quality_flag_token(reading.quality_flag),
            )
        )
    return pl.DataFrame(rows, schema=AIR_QUALITY_SCHEMA, orient="row")


def wind_rows(vectors: Iterable[telemetry.WindVector]) -> pl.DataFrame:
    """Encode WindVector messages into a WEATHER_SCHEMA DataFrame."""
    rows = []
    for vector in vectors:
        if not vector.HasField("observed_at") or not vector.HasField("ingested_at"):
            raise ContractError(f"WindVector {vector.grid_id!r}: timestamps not set")
        rows.append(
            (
                vector.grid_id,
                vector.observed_at.ToDatetime(tzinfo=UTC),
                vector.ingested_at.ToDatetime(tzinfo=UTC),
                vector.lat,
                vector.lon,
                vector.wind_speed_10m,
                vector.wind_direction_10m,
                vector.boundary_layer_height if vector.HasField("boundary_layer_height") else None,
            )
        )
    return pl.DataFrame(rows, schema=WEATHER_SCHEMA, orient="row")


_FIRE_CONFIDENCE_TOKENS: Final[dict[int, str]] = {
    telemetry.FIRE_CONFIDENCE_LOW: "low",
    telemetry.FIRE_CONFIDENCE_NOMINAL: "nominal",
    telemetry.FIRE_CONFIDENCE_HIGH: "high",
}


_QUALITY_FLAG_TOKENS: Final[dict[int, str]] = {
    telemetry.QUALITY_FLAG_VALID: "valid",
    telemetry.QUALITY_FLAG_OUTLIER: "outlier",
    telemetry.QUALITY_FLAG_STALE: "stale",
}
