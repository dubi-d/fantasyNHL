"""Rank-based statistics: percentiles and their normal scores."""
from collections.abc import Iterable
from statistics import NormalDist

import numpy as np
import pandas as pd

from ..config import Category


def _rank_pct(table: pd.DataFrame,
              categories: list[Category]) -> pd.DataFrame:
    """Midpoint percentile rank (0-100, ties averaged) of each column,
    inverted categories flipped so higher is always better."""
    n = table.notna().sum(axis=0)
    pct = (table.rank(axis=0) - 0.5) / n * 100
    for cat in categories:
        if cat.inverted and cat.name in pct:
            pct[cat.name] = 100 - pct[cat.name]
    return pct


def _rank_z(pct: pd.DataFrame) -> pd.DataFrame:
    """Normal quantile of percentile ranks: median 0, 84th percentile +1,
    98th +2. Rank-based, so a runaway leader in one category is not
    credited beyond his rank."""
    normal = NormalDist()
    return pct.map(lambda p: np.nan if pd.isna(p) else normal.inv_cdf(p / 100))


def percentile_ranks(values: Iterable[float | None]) -> list[float | None]:
    """Percentile rank (0-100, ties averaged) of each value among the
    non-missing ones; missing values stay None."""
    series = pd.Series(list(values), dtype=float)
    ranks = series.rank(pct=True) * 100
    return [None if pd.isna(r) else float(r) for r in ranks]
