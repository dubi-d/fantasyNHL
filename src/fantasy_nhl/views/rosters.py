"""Roster views: how rosters were assembled, the projected category
outlook, acquired players, one team's roster and its drop candidates."""
import pandas as pd

from ..analysis import (
    ACQUIRED_ADD,
    FULL_SEASON_GP,
    FULL_SEASON_GS,
    PUNT_Z,
    RATIO_CATEGORIES,
    acquisition_summary,
    category_outlook,
    drafted_rosters,
    market_gaps,
    min_season_games,
    player_table,
    projected_category_balance,
    replacement_rates,
    roster_origins,
)
from .common import PLAYER_TONES, player_view, ranked, score_tone, with_basis
from .model import (
    INFO,
    WARNING,
    TableView,
    View,
    column_tones,
    diverging,
    heat,
    note,
)
from .review import ReviewContext

GAPS_N = 10  # drop candidates / FA skater targets listed
GAPS_GOALIES = 5  # FA goalie targets listed


def _summary_tones(table: pd.DataFrame) -> pd.DataFrame:
    return column_tones(table, {"Avg Score": score_tone,
                                "Avg Own%": lambda v: heat(v / 100)})


def _empty_roster(name: str) -> View:
    return View([note(f"{name} has an empty roster.", level=WARNING)])


def build_origins(ctx: ReviewContext) -> View:
    """Per team: how its roster was assembled and how good it is."""
    table = roster_origins(ctx.review.rosters, ctx.values,
                           ctx.data.team_names, ctx.review.counters)
    table["Avg Own%"] = table["Avg Own%"].round(1)
    table["Avg Score"] = table["Avg Score"].round(2)
    table = ranked(table, by="Avg Score")
    return View([TableView(with_basis(
        "Roster Origins (composition today; Adds/Drops/Trades "
        "= season counters)", ctx.basis), table, _summary_tones(table)),
        *ctx.score_legend()])


def build_outlook(ctx: ReviewContext, source: str) -> View:
    """Projected full-season category totals per roster, ranked by the
    round-robin points they would earn; always on blended stats.

    :param source: "draft" (rosters as drafted) or "current"
    """
    review, cats = ctx.review, ctx.cats
    n_teams = ctx.n_teams
    if source == "draft":
        rosters = drafted_rosters(review.picks, n_teams)
        weight = 0.0  # draft-day expectation: projections only
    else:
        rosters = review.rosters
        weight = review.blend_weight
    names = [cat.name for cat in cats]
    replacement = replacement_rates(review.free_agents, cats, weight)
    z, totals = projected_category_balance(rosters, cats, ctx.data.team_names,
                                           weight, replacement)
    outlook = category_outlook(z, totals, cats)
    table = pd.concat([outlook, z], axis=1)
    table["Cats/M"] = table["Cats/M"].round(1)
    table["Spread"] = table["Spread"].round(2)
    table[names] = table[names].round(2)
    table.insert(0, "Player", table.index)
    table = table.sort_values(["RR Pts", "Cats/M"], ascending=False)
    table.index = range(1, len(table) + 1)
    league_avg = pd.DataFrame([{"Player": "(league avg)", **{
        name: (f"{avg:.3f}" if name in RATIO_CATEGORIES else f"{avg:.0f}")
        for name, avg in totals.mean(axis=0).items()}}], index=[""])
    if source == "draft":
        label, stats = "draft-day rosters, projections", (
            "ESPN season projections summed per roster")
    else:
        required = min_season_games(weight)
        label = "current rosters, blended pace"
        stats = (f"per-game rates blending {weight:.0%} season stats "
                 f"with projections, times projected games"
                 + (f"; players under {required} GP on projections only"
                    if required else ""))
    opponents = max(n_teams - 1, 1)
    blocks = [
        TableView(f"Category Outlook ({label}; sorted by projected "
                  "round-robin points)", table,
                  column_tones(table, {
                      "RR Pts": lambda v: heat(v / (2 * opponents)),
                      "Cats/M": lambda v: heat(v / len(cats)),
                      "Punts": lambda v: diverging(-v, 3),
                      **{col: lambda v: diverging(v, 2) for col in names}}),
                  footer=league_avg),
        note(f"RR Pts = round-robin points (2 W / 1 T) from a week against every "
             f"other team at these totals (max {2 * opponents}); Cats/M = "
             f"categories won per matchup; Spread = std of the team's category "
             f"z-scores (0 = evenly built); Punts = categories at z <= "
             f"{PUNT_Z:g}. Whole roster counts; "
             f"{stats}; games a player is not projected to play (up to "
             f"{FULL_SEASON_GP} GP / {FULL_SEASON_GS} GS) filled at replacement "
             f"level = median free agent of his position group (ratio "
             f"categories weighted by goalie starts); inverted categories "
             f"flipped; + = good.", level=INFO)]
    if source == "draft":
        blocks.append(note(
            "A projection snapshot, not a forecast: in a league with heavy "
            "waiver activity the drafted roster has little bearing on the "
            "standings - see Draft hits & busts and Waiver pickups for "
            "what actually happened.", level=INFO))
    if ctx.basis.season_only:
        blocks.append(note(
            "Not affected by the 'This season only' setting: "
            + ("draft-day rosters are ESPN's projections by definition."
               if source == "draft" else
               "a full-season pace needs projected games, so the outlook "
               "stays on blended stats."), level=WARNING))
    return View(blocks)


def build_acquired(ctx: ReviewContext, acquisition: str, label: str) -> View:
    """Players acquired by pickup (ACQUIRED_ADD) or trade (ACQUIRED_TRADE)
    still on rosters, with a per-team summary; ``label`` names them."""
    review, basis = ctx.review, ctx.basis
    summary, players = acquisition_summary(
        review.rosters, ctx.values, ctx.data.team_names, acquisition)
    summary["Avg Own%"] = summary["Avg Own%"].round(1)
    summary["Avg Score"] = summary["Avg Score"].round(2)
    # season-long counters include players since dropped or traded away
    if acquisition == ACQUIRED_ADD:
        summary["Season adds"] = [c.adds for c in review.counters]
    else:
        summary["Season trades"] = [c.trades for c in review.counters]
    summary = ranked(summary.fillna({"Best": ""}), by="Avg Score")
    blocks = [TableView(with_basis(
        f"{label} by team (Count = still on roster)", basis), summary,
        _summary_tones(summary))]
    if players.empty:
        blocks.append(note(f"No {label.lower()} on any roster.",
                           level=WARNING))
    else:
        view = player_view(players, ["Player", "Pos", "Team", "Slot", "GP",
                                     "Own%", "Score", "Gap", "Inj"])
        blocks.append(TableView(with_basis(f"{label} (all, by Score)", basis),
                                view, column_tones(view, PLAYER_TONES)))
    return View(blocks + ctx.score_legend(players, gap=not players.empty))


def build_gaps(ctx: ReviewContext, row: int) -> View:
    """A team's lowest-scoring players next to the best free agents."""
    review, basis = ctx.review, ctx.basis
    name = ctx.data.team_names[row]
    if not review.rosters[row]:
        return _empty_roster(name)
    drops, skaters, goalies = market_gaps(
        review.rosters[row], review.free_agents, ctx.values,
        ctx.data.team_names, GAPS_N, GAPS_GOALIES)
    cols = ["Player", "Pos", "Slot", "Acq", "GP", "Own%", "Chg", "Score",
            "Gap", "Inj"]
    fa_cols = [c for c in cols if c not in ("Slot", "Acq")]
    pool_note = f"of the {len(review.free_agents)} most-owned free agents"
    blocks = []
    for table, columns, title in (
            (drops, cols, f"{name} — lowest-scoring players (drop candidates)"),
            (skaters, fa_cols, f"Free-agent skaters by Score (top "
                               f"{len(skaters)} {pool_note})"),
            (goalies, fa_cols, f"Free-agent goalies by Score (top "
                               f"{len(goalies)} {pool_note})")):
        view = player_view(table, columns)
        blocks.append(TableView(with_basis(title, basis), view,
                                column_tones(view, PLAYER_TONES)))
    return View(blocks + ctx.score_legend(drops, skaters, goalies, gap=True))


def build_team_roster(ctx: ReviewContext, row: int) -> View:
    """A team's current roster, best Score first."""
    name = ctx.data.team_names[row]
    roster = ctx.review.rosters[row]
    if not roster:
        return _empty_roster(name)
    table = player_table(roster, ctx.values, ctx.data.team_names)
    # where the player was drafted (by anyone); blank for undrafted
    drafted_at = {p.player_id: p.overall for p in ctx.review.picks}
    table["Overall"] = pd.array([drafted_at.get(p.player_id)
                                 for p in roster], dtype="Int64")
    table = table.sort_values("Score", ascending=False, na_position="last",
                              kind="stable")
    view = player_view(table, ["Player", "Pos", "Slot", "Acq", "Overall",
                               "GP", "Own%", "Chg", "Score", "Gap", "Inj"])
    return View([TableView(with_basis(
        f"{name} — current roster (by Score; Overall = draft position)",
        ctx.basis), view, column_tones(view, PLAYER_TONES)),
        *ctx.score_legend(table, gap=True)])
