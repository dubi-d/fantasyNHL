"""CLI tools. Register new tools in the TOOLS list."""
import pandas as pd

from .analysis import round_robin
from .espn_data import LeagueData


def _weekly_tables(data: LeagueData) -> list[pd.DataFrame]:
    return [
        round_robin(data.weekly_cat_scores[:, :, week],
                    data.config.categories, data.team_names)
        for week in range(data.current_week - 1)
    ]


def weekly_scores(data: LeagueData) -> None:
    """Print the round-robin table for every completed week."""
    with pd.option_context('display.max_rows', 20, 'display.max_columns', 20):
        for week, table in enumerate(_weekly_tables(data), start=1):
            print(f"\n-------Week {week}:")
            print(table)


def accumulated_scores(data: LeagueData) -> None:
    """Print the accumulated round-robin standings over all completed weeks."""
    tables = _weekly_tables(data)
    if not tables:
        print("No completed weeks yet.")
        return

    stat_cols = ["W", "L", "T", "CatsWon", "Pts"]
    accumulated = tables[0].copy()
    for table in tables[1:]:
        accumulated[stat_cols] += table[stat_cols]

    accumulated.sort_values(by=["Pts"], ascending=False, inplace=True)
    accumulated = accumulated[["Player"] + stat_cols]
    with pd.option_context('display.max_rows', 20, 'display.max_columns', 20):
        print("\n #### Accumulated Scores:")
        print(accumulated)


# (menu label, callable) — extend here for new tools
TOOLS = [
    ("Show weekly scores", weekly_scores),
    ("Show accumulated scores", accumulated_scores),
]
