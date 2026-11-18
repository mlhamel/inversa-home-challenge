from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

TEST_BBOX: Final[str] = "-124.4,36.0,-115.4,42.0"
RUN_AT: Final[datetime] = datetime(2026, 11, 17, 18, 0, tzinfo=UTC)

FIRMS_HEADER: Final[str] = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight"
)
FIRMS_ROW_A: Final[str] = (
    "37.7749,-122.4194,337.1,1.2,1.0,2026-11-14,1830,N20,VIIRS,h,2.0NRT,328.7,12.3,night"
)
FIRMS_ROW_A_DUP: Final[str] = (
    "37.7749,-122.4194,337.1,1.2,1.0,2026-11-14,1830,N20,VIIRS,h,2.0NRT,328.7,15.0,night"
)
FIRMS_ROW_D: Final[str] = (
    "38.5816,-121.4944,321.0,1.1,1.2,2026-11-14,630,N20,VIIRS,n,2.0NRT,315.2,8.4,day"
)
FIRMS_ROW_BAD_CONFIDENCE: Final[str] = (
    "37.7749,-122.4194,337.1,1.2,1.0,2026-11-14,1830,N20,VIIRS,x,2.0NRT,328.7,12.3,night"
)
FIRMS_ROW_BAD_LAT: Final[str] = (
    "95.0000,-122.4194,337.1,1.2,1.0,2026-11-14,1830,N20,VIIRS,h,2.0NRT,328.7,12.3,night"
)
EMPTY_FIRMS_CSV: Final[str] = FIRMS_HEADER
INVALID_DAY_RANGE_CSV: Final[str] = "Invalid day range. Expects [1..5]."

FRESH_UTC: Final[str] = "2026-11-17T17:00:00Z"
OLDER_UTC: Final[str] = "2026-11-17T15:00:00Z"

METEO_TIMES: Final[tuple[str, ...]] = (
    "2026-11-17T16:00",
    "2026-11-17T17:00",
    "2026-11-17T19:00",
)
METEO_SPEEDS: Final[tuple[float, ...]] = (4.0, 6.0, 9.0)
METEO_DIRECTIONS: Final[tuple[float, ...]] = (270.0, 180.0, 45.0)
METEO_HEIGHTS: Final[tuple[float, ...]] = (500.0, 510.0, 700.0)


def openaq_location(
    *,
    identifier: int = 2009,
    name: str = "San Francisco",
    lat: float = 37.7658,
    lon: float = -122.3978,
    sensor_id: int = 3569,
) -> dict[str, object]:
    return {
        "id": identifier,
        "name": name,
        "coordinates": {"latitude": lat, "longitude": lon},
        "sensors": [
            {
                "id": 25672,
                "name": "co ppm",
                "parameter": {"id": 8, "name": "co", "units": "ppm", "displayName": None},
            },
            {
                "id": sensor_id,
                "name": "pm2.5 µg/m³",
                "parameter": {"id": 2, "name": "pm25", "units": "µg/m³", "displayName": None},
            },
        ],
    }


def openaq_latest_entry(*, sensors_id: int, value: float | None, utc: str) -> dict[str, object]:
    return {
        "datetime": {"utc": utc, "local": utc},
        "value": value,
        "coordinates": {"latitude": 37.7658, "longitude": -122.3978},
        "sensorsId": sensors_id,
        "locationsId": 2009,
    }


def openaq_hours_entry(*, value: float, utc: str) -> dict[str, object]:
    return {
        "value": value,
        "flagInfo": {"hasFlags": False},
        "parameter": {"id": 2, "name": "pm25", "units": "µg/m³", "displayName": None},
        "period": {
            "label": "1hour",
            "interval": "01:00:00",
            "datetimeFrom": {"utc": utc, "local": utc},
            "datetimeTo": {"utc": utc, "local": utc},
        },
    }


def meteo_batch(lat: float, lon: float) -> dict[str, object]:
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": {
            "time": list(METEO_TIMES),
            "wind_speed_10m": list(METEO_SPEEDS),
            "wind_direction_10m": list(METEO_DIRECTIONS),
            "boundary_layer_height": list(METEO_HEIGHTS),
        },
    }


def now_utc() -> datetime:
    return RUN_AT
