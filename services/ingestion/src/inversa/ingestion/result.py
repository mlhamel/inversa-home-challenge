from __future__ import annotations

import polars as pl
from pydantic import BaseModel, ConfigDict


class CollectorError(RuntimeError):
    pass


class CollectorResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    df: pl.DataFrame
    rejected: int = 0
