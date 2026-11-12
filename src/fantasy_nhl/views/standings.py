"""Season standings views: accumulated round-robin strength, schedule luck,
power rankings over time and the category strength profile."""
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import (
    average_points,
    category_contestedness,
    category_win_rates,
    luck,
    rank_timeline,
    trailing_points,
    weekly_points_timeline,
)
from .common import completed_matchups, ranked, round_robin_week
from .model import (
    WARNING,
    FigureBlock,
    TableView,
    View,
    column_tones,
    diverging,
    heat,
    note,
)

if TYPE_CHECKING:
    from ..espn_data import LeagueData


def _no_completed_weeks() -> View:
    return View([note("No completed weeks yet.", level=WARNING)])


def _accumulated_table(data: "LeagueData") -> pd.DataFrame | None:
    """Accumulated round-robin stats, actual record and luck over completed
    weeks, or None if no week is completed yet."""
    completed_weeks = completed_matchups(data)
    if completed_weeks == 0:
        return None

    stat_cols = ["W", "L", "T", "CatsWon", "Pts"]
    accumulated = round_robin_week(data, 1)
    for week in range(2, completed_weeks + 1):
        accumulated[stat_cols] += round_robin_week(data, week)[stat_cols]
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


def _luck_tones(table: pd.DataFrame) -> pd.DataFrame:
    luck_scale = table["Luck"].abs().max()
    return column_tones(table, {"Luck": lambda v: diverging(v, luck_scale)})


def build_accumulated_scores(data: "LeagueData") -> View:
    """Actual matchup record next to the accumulated round-robin standings
    over all completed weeks."""
    accumulated = _accumulated_table(data)
    if accumulated is None:
        return _no_completed_weeks()

    accumulated = ranked(
        accumulated[["Player", "W", "L", "T", "Pts",
                     "rrW", "rrL", "rrT", "CatsWon", "xPts", "Luck"]],
        by="xPts")
    return View([TableView("Accumulated Scores (matchup vs round-robin)",
                           accumulated, _luck_tones(accumulated))])


def build_luck_ranking(data: "LeagueData") -> View:
    """Teams ranked by accumulated schedule luck (luckiest first)."""
    table = _accumulated_table(data)
    if table is None:
        return _no_completed_weeks()

    table = table.sort_values(by=["Luck"], ascending=False)
    table.index = range(1, len(table) + 1)
    table = table[["Player", "W", "L", "T", "Pts", "xPts", "Luck"]]
    return View([TableView("Luck Ranking (positive = favorable schedule)",
                           table, _luck_tones(table))])


def build_power_rankings(data: "LeagueData", completed: int,
                         window: int) -> View:
    """Round-robin points per completed matchup as a teams-x-matchups
    table, plus the timeline figure (hot-streak rank bump chart over a
    trailing ``window`` of matchups + average points)."""
    timeline = weekly_points_timeline(
        data.weekly_cat_scores[:, :, :completed],
        data.config.categories, data.team_names)
    form_ranks = rank_timeline(trailing_points(timeline, window))
    averages = average_points(timeline)

    matchup_cols = [f"M{w}" for w in timeline.columns]
    table = timeline.set_axis(matchup_cols, axis=1)
    table.insert(0, "Player", timeline.index)
    table["Total"] = timeline.sum(axis=1)
    table = ranked(table.reset_index(drop=True), by="Total")
    max_pts = 2 * (len(data.team_names) - 1)  # neutral color at max_pts/2
    tones = column_tones(table, {
        **{col: lambda v: heat(v / max_pts) for col in matchup_cols},
        "Total": lambda v: heat(v / (max_pts * completed))})
    title = f"{data.config.name} — Power Rankings (through matchup {completed})"
    return View([
        TableView("Power Rankings (round-robin points per completed matchup)",
                  table, tones),
        FigureBlock("power_rankings", "power_rankings",
                    {"form_ranks": form_ranks, "avg_points": averages,
                     "window": window, "title": title})])


def build_category_profile(data: "LeagueData") -> View:
    """Each team's per-category round-robin win% over completed weeks,
    plus how contested each category is league-wide."""
    completed_weeks = completed_matchups(data)
    if completed_weeks == 0:
        return _no_completed_weeks()

    scores = data.weekly_cat_scores[:, :, :completed_weeks]
    cat_names = [cat.name for cat in data.config.categories]
    table = category_win_rates(scores, data.config.categories, data.team_names)
    contested = category_contestedness(table, data.config.categories).round(2)
    table["Overall"] = table[cat_names].mean(axis=1)
    table[cat_names + ["Overall"]] = table[cat_names + ["Overall"]].round(2)
    table = ranked(table[["Player"] + cat_names + ["Overall"]], by="Overall")

    footer = pd.DataFrame(
        [{"Player": "(contested)", **contested.to_dict()}], index=[""])
    return View([TableView(
        "Category Strength Profile (win rate per category, completed weeks)",
        table, column_tones(table, dict.fromkeys(cat_names + ["Overall"], heat)),
        footer=footer)])
