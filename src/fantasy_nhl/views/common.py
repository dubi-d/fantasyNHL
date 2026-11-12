"""Helpers shared by several views."""
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import round_robin
from .model import BAD, EVEN, GOOD

if TYPE_CHECKING:
    from ..espn_data import LeagueData

RESULT_TONES = {"W": GOOD, "L": BAD, "T": EVEN}


def completed_matchups(data: "LeagueData") -> int:
    """Number of completed matchups; the current one counts once it has a
    decided result (season over)."""
    if any(results[data.current_week - 1] != "NA"
           for results in data.weekly_results):
        return data.current_week
    return data.current_week - 1


def ranked(table: pd.DataFrame, by: str = "Pts") -> pd.DataFrame:
    """Sort by the given points column and use the rank as index."""
    table = table.sort_values(by=[by], ascending=False)
    table.index = range(1, len(table) + 1)
    return table


def round_robin_week(data: "LeagueData", week: int) -> pd.DataFrame:
    return round_robin(data.weekly_cat_scores[:, :, week - 1],
                       data.config.categories, data.team_names)
