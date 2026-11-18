"""Collector result contract."""
from __future__ import annotations

import polars as pl
from pydantic import BaseModel, ConfigDict


class CollectorError(RuntimeError):
    """Raised when a collector cannot complete."""


class CollectorResult(BaseModel):
    """Frozen collector output: validated frame and rejected-row count."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    df: pl.DataFrame
    rejected: int = 0
