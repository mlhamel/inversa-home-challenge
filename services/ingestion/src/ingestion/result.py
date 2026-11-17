from __future__ import annotations

from dataclasses import dataclass

import polars as pl


class CollectorError(RuntimeError):
    pass


@dataclass(frozen=True)
class CollectorResult:
    df: pl.DataFrame
    rejected: int = 0
