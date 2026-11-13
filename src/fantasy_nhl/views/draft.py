"""Draft views: grades against ADP, hits and busts, one team's picks."""
import pandas as pd

from ..analysis import (
    draft_extremes,
    draft_return,
    draft_team_summary,
    draft_value_grid,
)
from .common import PLAYER_TONES, player_view, points_tone, ranked, with_basis
from .model import (
    INFO,
    WARNING,
    TableView,
    Tone,
    View,
    column_tones,
    diverging,
    note,
)
from .review import ReviewContext

EXTREMES = 10  # league-wide steals/reaches listed
RETURN_N = 15  # draft hits / busts listed


def not_drafted() -> View:
    return View([note("The league has not drafted yet.", level=WARNING)])


def _value_tone(ctx: ReviewContext):
    def tone(value: float) -> Tone:
        # a full round of pick value is a strong signal; colour saturates there
        return diverging(value, ctx.n_teams)
    return tone


def build_draft_grades(ctx: ReviewContext) -> View:
    """Pick value against ESPN's ADP: per-team summary, value by round and
    the league-wide biggest steals and reaches."""
    pick_table, n_teams = ctx.pick_table, ctx.n_teams
    value_tone = _value_tone(ctx)
    blocks = []
    if pick_table["ADP"].nunique() <= 1:
        # ESPN replaces ADP with a single placeholder once a season is over
        blocks.append(note("ESPN reports the same ADP for every player "
                           "(season archived?) - pick values are meaningless.",
                           level=WARNING))
    summary = draft_team_summary(pick_table)
    summary["Avg value"] = summary["Avg value"].round(1)
    summary["Total"] = summary["Total"].round(0).astype(int)
    summary["Kept"] = [f"{k}/{n}" for k, n in
                       zip(summary["Kept"], summary["Picks"])]
    summary = ranked(summary.drop(columns="Picks"), by="Avg value")
    n_rounds = int(pick_table["Rd"].max())
    blocks.append(TableView(
        "Draft Grades (pick value = pick − ESPN ADP; positive = later than "
        "ADP)", summary, column_tones(summary, {
            "Avg value": value_tone,
            "Total": lambda v: diverging(v, n_teams * n_rounds / 4)})))

    grid = draft_value_grid(pick_table).round(0).astype("Int64")
    grid.insert(0, "Player", grid.index)
    grid.index = range(1, len(grid) + 1)
    blocks.append(TableView("Pick value by round", grid, column_tones(
        grid, {col: value_tone for col in grid.columns if col != "Player"})))

    steals, reaches = draft_extremes(pick_table, EXTREMES)
    cols = ["Player", "Pos", "Team", "Rd.Pk", "Overall", "ADP", "Value",
            "Own%", "NowOn"]
    for label, rows in (("steals", steals), ("reaches", reaches)):
        view = player_view(rows, cols)
        blocks.append(TableView(f"Biggest {label} (top {len(rows)})", view,
                                column_tones(view, {"Value": value_tone})))
    blocks.append(note("ADP and roster% are ESPN's values as of today; "
                       "players ESPN has no ADP for count as pick "
                       f"{int(pick_table['Overall'].max()) + 1}.", level=INFO))
    return View(blocks)


def build_draft_return(ctx: ReviewContext) -> View:
    """How the picks panned out: league-wide hits and busts and the
    average Return per drafting team."""
    data, basis = ctx.data, ctx.basis
    table = draft_return(ctx.review.picks, ctx.values, data.team_names,
                         ctx.pool)
    cols = ["Player", "Pos", "Team", "Rd.Pk", "Overall", "GP", "Own%",
            "Score", "Return", "NowOn"]
    ranked_picks = table.dropna(subset=["Return"])
    hits = ranked_picks.nlargest(RETURN_N, "Return")
    busts = ranked_picks.nsmallest(RETURN_N, "Return")
    blocks = []
    for label, rows in (("hits", hits), ("busts", busts)):
        view = player_view(rows, cols)
        blocks.append(TableView(
            with_basis(f"Draft {label} (top {len(rows)})", basis), view,
            column_tones(view, PLAYER_TONES)))
    per_team = ranked_picks.groupby("TeamRow")["Return"].agg(["mean", "sum"])
    summary = pd.DataFrame({"Player": [data.team_names[r]
                                       for r in per_team.index],
                            "Avg Return": per_team["mean"].round(0)
                            .astype(int).to_numpy(),
                            "Total": per_team["sum"].round(0)
                            .astype(int).to_numpy()})
    summary = ranked(summary, by="Avg Return")
    blocks.append(TableView(
        with_basis("Draft return by team", basis), summary,
        column_tones(summary, {"Avg Return": points_tone,
                               "Total": lambda v: diverging(v, 500)})))
    blocks.append(note("Return = Score percentile within the position group "
                       "minus the draft-slot percentile (pick 1 = 100), in "
                       "percentage points; roster% is informational only.",
                       level=INFO))
    return View(blocks + ctx.score_legend(hits, busts))


def build_team_draft(ctx: ReviewContext, row: int) -> View:
    """A team's picks in draft order with their value and Return."""
    data, pick_table = ctx.data, ctx.pick_table
    picks = draft_return(ctx.review.picks, ctx.values, data.team_names,
                         ctx.pool)
    picks = picks[picks["TeamRow"] == row]
    extra = pick_table.loc[pick_table["TeamRow"] == row,
                           ["Overall", "ADP", "Value", "ValueRd", "Rank"]]
    table = picks.merge(extra, on="Overall").sort_values("Overall")
    view = player_view(table, ["Rd.Pk", "Overall", "Player", "Pos", "ADP",
                               "Value", "Rounds", "Rank", "GP", "Own%",
                               "Score", "Return", "NowOn"])
    return View([TableView(with_basis(
        f"{data.team_names[row]} — draft picks (Value = pick − ADP, Rounds = "
        f"Value / {ctx.n_teams})", ctx.basis), view,
        column_tones(view, {**PLAYER_TONES, "Value": _value_tone(ctx),
                            "Rounds": lambda v: diverging(v, 1)})),
        *ctx.score_legend(table)])
