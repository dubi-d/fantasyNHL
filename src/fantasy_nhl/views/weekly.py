"""Weekly views: round-robin scores per matchup and the weekly awards."""
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ..analysis import (
    category_leaders,
    category_win_rates,
    luck,
    matchup_result,
    pick_weekly_awards,
)
from .common import RESULT_TONES, completed_matchups, round_robin_week
from .model import (
    HEADING,
    TableView,
    TextBlock,
    View,
    cell_text,
    column_tones,
    diverging,
    heat,
    note,
)

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


def _shown(totals: pd.Series) -> pd.Series:
    """A category's totals as displayed: blank where ESPN has no value
    yet (a GAA before the first goalie start is infinite)."""
    totals = totals.where(np.isfinite(totals))
    if (totals.dropna() % 1 == 0).all():
        return totals.astype("Int64")
    return totals.round(3)


def _category_columns(data: "LeagueData",
                      week: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A week's category totals as displayed and their strength, the
    round-robin win rate within that week (missing for a blank total);
    both teams x categories, index = team row."""
    categories = data.config.categories
    names = [cat.name for cat in categories]
    scores = data.weekly_cat_scores[:, :, week - 1:week]
    values = pd.DataFrame(scores[:, :, 0], columns=names).apply(_shown)
    rates = category_win_rates(scores, categories, data.team_names)[names]
    return values, rates.where(values.notna())


def _scores_table(table: pd.DataFrame, values: pd.DataFrame,
                  rates: pd.DataFrame, title: str) -> TableView:
    """
    :param table: a week's round-robin table as built by week_table
    :param values: its category totals, as built by _category_columns
    :param rates: their win rates, which color them
    """
    table = table.rename(columns={"W": "rrW", "L": "rrL", "T": "rrT"})
    table["Luck"] = table["Luck"].round(2)
    # joined after the rename: a league may score goalie wins as "W"
    table = table[["Player", "Result", "rrW", "rrL", "rrT", "CatsWon", "Pts",
                   "Luck"]].join(values).sort_values(by=["Pts"], ascending=False)
    # weekly luck is bounded by +-2
    tones = column_tones(table, {
        "Result": RESULT_TONES.get, "Luck": lambda v: diverging(v, 2)}).join(
        column_tones(rates.loc[table.index], dict.fromkeys(rates, heat)))
    table.index = tones.index = range(1, len(table) + 1)
    return TableView(title, table, tones)


def build_weekly_scores(data: "LeagueData") -> View:
    """The round-robin table of every week, including the ongoing one,
    with the category totals behind it."""
    view = View()
    completed = completed_matchups(data)
    for week in range(1, data.current_week + 1):
        ongoing = " (ongoing)" if week > completed else ""
        view.blocks.append(_scores_table(
            week_table(data, week), *_category_columns(data, week),
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
    team, luckiest win, biggest choke, the leader of each category) as
    text for the league chat.

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

    values, rates = _category_columns(data, week)
    # a category everybody tied in has no king
    kings = [f"{cat} {' & '.join(names[row] for row in rows)} "
             f"({cell_text(values.loc[rows[0], cat])})"
             for cat, rows in category_leaders(scores, categories).items()
             if len(rows) < len(names)]
    if kings:
        lines.append(f"👑 Category kings: {', '.join(kings)}")

    return View([_scores_table(table, values, rates, f"Matchup {week} scores"),
                 note("Copy-paste for the league chat:", level=HEADING),
                 TextBlock("\n".join(lines))])
