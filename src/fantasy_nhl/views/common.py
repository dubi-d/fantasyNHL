"""Helpers shared by several views."""
from collections.abc import Iterable
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import PreviewPlayer, StatBasis, has_season_games, round_robin
from .model import BAD, EVEN, GOOD, WARNING, Note, note

if TYPE_CHECKING:
    from ..espn_data import LeagueData

RESULT_TONES = {"W": GOOD, "L": BAD, "T": EVEN}


def stat_basis(season_only: bool, season_fraction: float) -> StatBasis:
    return (StatBasis.season(season_fraction) if season_only
            else StatBasis.blended(season_fraction))


def basis_label(basis: StatBasis) -> str:
    if basis.season_only:
        return "this season only"
    season = round(basis.season_fraction * 100)
    return f"blended: {season}% season / {100 - season}% projection"


def with_basis(title: str, basis: StatBasis) -> str:
    return f"{title} — stats: {basis_label(basis)}"


def no_season_stats_note(basis: StatBasis,
                         players: Iterable[PreviewPlayer]) -> Note | None:
    """Warning for season-only stats when nobody has played yet."""
    if basis.season_only and not any(has_season_games(p) for p in players):
        return note("Nobody here has played this season yet, so 'This "
                    "season only' stats are empty - switch Player stats "
                    "to Blended in the main menu to use projections.",
                    level=WARNING)
    return None


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
