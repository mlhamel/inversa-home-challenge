"""Scene constants shared by the conftest fixtures and the test modules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

ANALYSIS_TS: datetime = datetime(2026, 11, 17, 14, 0, tzinfo=UTC)
RUN_AT: datetime = datetime(2026, 11, 17, 14, 30, tzinfo=UTC)

STATION_NAMES: dict[str, str] = {
    "STA-DOWN": "Downslope Ridge",
    "STA-SIDE": "Sidewinder Park",
    "STA-FAR": "Faraway Flats",
}


def ts(hour: int, minute: int) -> datetime:
    """Build a scene wall-clock timestamp on 2026-11-17 UTC."""
    base = datetime(2026, 11, 17, tzinfo=UTC)
    return base + timedelta(hours=hour, minutes=minute)
