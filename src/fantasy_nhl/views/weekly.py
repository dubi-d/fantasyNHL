"""Weekly views: round-robin scores per matchup and the weekly awards."""
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import luck, matchup_result, pick_weekly_awards
from .common import (
    RESULT_TONES,
    completed_matchups,
    ranked,
    round_robin_week,
)
from .model import HEADING, TableView, TextBlock, View, column_tones, diverging, note

if TYPE_CHECKING:
    from ..sources.espn import LeagueData

# points awarded for a real matchup result ("NA" -> no luck value yet)
RESULT_PTS = {"W": 2, "T": 1, "L": 0}


def week_table(data: "LeagueData", week: int) -> pd.DataFrame:
    """Round-robin table for one week with actual Result and Luck columns;
    index = team row."""
    table = round_robin_week(data, week)
    table["Result"] = [row_results[week - 1] for row_results in data.weekly_results]
    actual_pts = table["Result"].map(RESULT_PTS)
    table["Luck"] = luck(actual_pts, table["Pts"], len(data.team_names) - 1)
    return table


def _scores_table(table: pd.DataFrame, title: str) -> TableView:
    table = table.rename(columns={"W": "rrW", "L": "rrL", "T": "rrT"})
    table["Luck"] = table["Luck"].round(2)
    table = ranked(
        table[["Player", "Result", "rrW", "rrL", "rrT", "CatsWon", "Pts", "Luck"]])
    # weekly luck is bounded by +-2
    return TableView(title, table, column_tones(table, {
        "Result": RESULT_TONES.get, "Luck": lambda v: diverging(v, 2)}))


def build_weekly_scores(data: "LeagueData") -> View:
    """The round-robin table of every week, including the ongoing one."""
    view = View()
    completed = completed_matchups(data)
    for week in range(1, data.current_week + 1):
        ongoing = " (ongoing)" if week > completed else ""
        view.blocks.append(_scores_table(week_table(data, week),
                                         f"Week {week}{ongoing}"))
    return view


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _award_line(emoji: str, label: str, team: str, *clauses: str) -> str:
    return f"{emoji} {label}: {team} — {', '.join(c for c in clauses if c)}"


def build_weekly_awards(data: "LeagueData", week: int,
                        pairings: list[tuple[int, int]]) -> View:
    """A completed matchup's round-robin table and its awards (best/worst
    team, luckiest win, biggest choke) as text for the league chat.

    :param pairings: (home row, away row) of that matchup
    """
    table = week_table(data, week)
    opponents = {row: opp for pair in pairings for row, opp in (pair, pair[::-1])}

    names = data.team_names
    categories = data.config.categories
    scores = data.weekly_cat_scores[:, :, week - 1]
    ranks = table["Pts"].rank(ascending=False, method="min").astype(int)

    def scoreline(row: int, opp: int) -> str:
        won = int(matchup_result(scores[row], scores[opp], categories)[3])
        lost = int(matchup_result(scores[opp], scores[row], categories)[3])
        return f"{won}-{lost}-{len(categories) - won - lost}"

    def versus(row: pd.Series) -> str:
        """'beat <opponent> 6-2-1' clause, empty without a decided matchup."""
        opp = opponents.get(row.name)
        verb = {"W": "beat", "L": "lost to", "T": "tied"}.get(row["Result"])
        if opp is None or verb is None:
            return ""
        return f"{verb} {names[opp]} {scoreline(row.name, opp)}"

    def field_record(row: pd.Series) -> str:
        return f"{int(row['W'])}-{int(row['L'])}-{int(row['T'])} vs the field"

    awards = pick_weekly_awards(table)
    best, worst = awards["best"], awards["worst"]
    dates = (data.week_dates or {}).get(week)
    when = f" ({dates[0]:%b %-d} – {dates[1]:%b %-d})" if dates else ""
    lines = [f"🏒 Matchup {week} Awards{when}",
             _award_line("🏆", "Team of the matchup", best["Player"],
                         f"best stats ({field_record(best)})", versus(best)),
             _award_line("🥶", "Dud of the matchup", worst["Player"],
                         f"worst stats ({field_record(worst)})", versus(worst))]
    lucky = awards.get("luckiest_win")
    if lucky is not None and lucky["Player"] != best["Player"]:
        lines.append(_award_line(
            "🍀", "Luckiest win", lucky["Player"], versus(lucky),
            f"with only the {_ordinal(ranks[lucky.name])}-best stats"))
    choke = awards.get("biggest_choke")
    if choke is not None and choke["Player"] != worst["Player"]:
        lines.append(_award_line(
            "💀", "Biggest choke", choke["Player"], versus(choke),
            f"despite the {_ordinal(ranks[choke.name])}-best stats"))

    return View([_scores_table(table, f"Matchup {week} scores"),
                 note("Copy-paste for the league chat:", level=HEADING),
                 TextBlock("\n".join(lines))])
