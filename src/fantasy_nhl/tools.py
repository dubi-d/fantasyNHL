"""CLI tools. Register new tools in the TOOLS list."""
import pandas as pd

from .analysis import luck, round_robin
from .espn_data import LeagueData

# points awarded for a real matchup result ("NA" -> no luck value yet)
RESULT_PTS = {"W": 2, "T": 1, "L": 0}


def _round_robin_week(data: LeagueData, week: int) -> pd.DataFrame:
    return round_robin(data.weekly_cat_scores[:, :, week - 1],
                       data.config.categories, data.team_names)


def _ranked(table: pd.DataFrame, by: str = "Pts") -> pd.DataFrame:
    """Sort by the given points column and use the rank as index."""
    table = table.sort_values(by=[by], ascending=False)
    table.index = range(1, len(table) + 1)
    return table


def weekly_scores(data: LeagueData) -> None:
    """Print the round-robin table for every week, including the ongoing one."""
    with pd.option_context('display.max_rows', 20, 'display.max_columns', 20,
                           'display.width', 0):
        for week in range(1, data.current_week + 1):
            table = _round_robin_week(data, week)
            table["Result"] = [row_results[week - 1] for row_results in data.weekly_results]
            table = table.rename(columns={"W": "rrW", "L": "rrL", "T": "rrT"})
            actual_pts = table["Result"].map(RESULT_PTS)
            table["Luck"] = luck(actual_pts, table["Pts"], len(data.team_names) - 1).round(2)
            table["|"] = "|"
            table = _ranked(
                table[["Player", "Result", "|", "rrW", "rrL", "rrT", "CatsWon", "Pts", "Luck"]])
            ongoing = " (ongoing)" if week == data.current_week else ""
            print(f"\n-------Week {week}{ongoing}:")
            print(table)


def accumulated_scores(data: LeagueData) -> None:
    """Print actual matchup record and accumulated round-robin standings
    over all completed weeks."""
    accumulated = _accumulated_table(data)
    if accumulated is None:
        print("No completed weeks yet.")
        return

    accumulated["|"] = "|"
    accumulated = _ranked(
        accumulated[["Player", "W", "L", "T", "Pts", "|",
                     "rrW", "rrL", "rrT", "CatsWon", "xPts", "Luck"]],
        by="xPts")
    with pd.option_context('display.max_rows', 20, 'display.max_columns', 20,
                           'display.width', 0):
        print("\n #### Accumulated Scores (matchup | round-robin):")
        print(accumulated)


def _accumulated_table(data: LeagueData) -> pd.DataFrame | None:
    """Accumulated round-robin stats, actual record and luck over completed
    weeks, or None if no week is completed yet."""
    completed_weeks = data.current_week - 1
    if completed_weeks == 0:
        return None

    stat_cols = ["W", "L", "T", "CatsWon", "Pts"]
    accumulated = _round_robin_week(data, 1)
    for week in range(2, completed_weeks + 1):
        accumulated[stat_cols] += _round_robin_week(data, week)[stat_cols]
    accumulated = accumulated.rename(columns={"W": "rrW", "L": "rrL", "T": "rrT"})

    # actual matchup record (completed weeks only)
    for result in ("W", "L", "T"):
        accumulated[result] = [row_results[:completed_weeks].count(result)
                               for row_results in data.weekly_results]
    num_opponents = len(data.team_names) - 1
    actual_pts = 2 * accumulated["W"] + accumulated["T"]
    accumulated["Luck"] = luck(actual_pts, accumulated["Pts"], num_opponents).round(2)
    # replace rr points with expected points; matchup points take the Pts name
    accumulated["xPts"] = (accumulated["Pts"] / num_opponents).round(2)
    accumulated["Pts"] = actual_pts
    return accumulated


def luck_ranking(data: LeagueData) -> None:
    """Print teams ranked by accumulated schedule luck (luckiest first)."""
    table = _accumulated_table(data)
    if table is None:
        print("No completed weeks yet.")
        return

    table = table.sort_values(by=["Luck"], ascending=False)
    table.index = range(1, len(table) + 1)
    table = table[["Player", "W", "L", "T", "Pts", "xPts", "Luck"]]
    with pd.option_context('display.max_rows', 20, 'display.max_columns', 20,
                           'display.width', 0):
        print("\n #### Luck Ranking (positive = favorable schedule):")
        print(table)


# (menu label, callable) — extend here for new tools
TOOLS = [
    ("Show weekly scores", weekly_scores),
    ("Show accumulated scores", accumulated_scores),
    ("Show luck ranking", luck_ranking),
]
