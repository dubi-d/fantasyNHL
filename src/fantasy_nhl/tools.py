"""CLI tools. Register new tools in the TOOLS list."""
import pandas as pd

from .analysis import round_robin
from .espn_data import LeagueData


def _round_robin_week(data: LeagueData, week: int) -> pd.DataFrame:
    return round_robin(data.weekly_cat_scores[:, :, week - 1],
                       data.config.categories, data.team_names)


def _ranked(table: pd.DataFrame) -> pd.DataFrame:
    """Sort by round-robin points and use the rank as index."""
    table = table.sort_values(by=["Pts"], ascending=False)
    table.index = range(1, len(table) + 1)
    return table


def weekly_scores(data: LeagueData) -> None:
    """Print the round-robin table for every week, including the ongoing one."""
    with pd.option_context('display.max_rows', 20, 'display.max_columns', 20):
        for week in range(1, data.current_week + 1):
            table = _round_robin_week(data, week)
            table["Result"] = [row_results[week - 1] for row_results in data.weekly_results]
            table = table.rename(columns={"W": "rrW", "L": "rrL", "T": "rrT"})
            table["|"] = "|"
            table = _ranked(table[["Player", "Result", "|", "rrW", "rrL", "rrT", "CatsWon", "Pts"]])
            ongoing = " (ongoing)" if week == data.current_week else ""
            print(f"\n-------Week {week}{ongoing}:")
            print(table)


def accumulated_scores(data: LeagueData) -> None:
    """Print actual matchup record and accumulated round-robin standings
    over all completed weeks."""
    completed_weeks = data.current_week - 1
    if completed_weeks == 0:
        print("No completed weeks yet.")
        return

    stat_cols = ["W", "L", "T", "CatsWon", "Pts"]
    accumulated = _round_robin_week(data, 1)
    for week in range(2, completed_weeks + 1):
        accumulated[stat_cols] += _round_robin_week(data, week)[stat_cols]
    accumulated = accumulated.rename(columns={"W": "rrW", "L": "rrL", "T": "rrT"})

    # actual matchup record (completed weeks only)
    for result in ("W", "L", "T"):
        accumulated[result] = [row_results[:completed_weeks].count(result)
                               for row_results in data.weekly_results]
    accumulated["|"] = "|"

    accumulated = _ranked(
        accumulated[["Player", "W", "L", "T", "|", "rrW", "rrL", "rrT", "CatsWon", "Pts"]])
    with pd.option_context('display.max_rows', 20, 'display.max_columns', 20):
        print("\n #### Accumulated Scores (matchup | round-robin):")
        print(accumulated)


# (menu label, callable) — extend here for new tools
TOOLS = [
    ("Show weekly scores", weekly_scores),
    ("Show accumulated scores", accumulated_scores),
]
