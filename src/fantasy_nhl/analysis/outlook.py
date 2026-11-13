"""Projected category totals per roster and their round-robin outlook."""
import numpy as np
import pandas as pd

from ..config import Category
from .models import (
    _GOALIE_SLOT,
    GOALIE_CATEGORIES,
    POSITION_GROUPS,
    RATIO_CATEGORIES,
    PreviewPlayer,
    position_group,
)
from .rates import (
    _player_rate,
    _stat_games,
    blended_per_game,
    blended_ratio,
    min_season_games,
)
from .standings import round_robin


# games a roster spot is filled for over a full season (the replacement-level
# fill tops every player up to this); a starting goalie's workload for G
FULL_SEASON_GP = 82
FULL_SEASON_GS = 60

# position group -> category -> per-game rate (ratio for GAA / SV%)
ReplacementRates = dict[str, dict[str, float]]


def _pace_weight(player: PreviewPlayer, blend_weight: float) -> float:
    """blend_weight for a player with enough season games for a rate,
    else 0 (projections only)."""
    games = _stat_games(player.season_stats)
    return blend_weight if games >= min_season_games(blend_weight) else 0.0


def replacement_rates(players: list[PreviewPlayer],
                      categories: list[Category],
                      blend_weight: float) -> ReplacementRates:
    """
    What a roster spot produces when filled from the waiver wire: the
    median blended per-game rate (see blended_per_game; ratio categories
    blended directly) per position group and category over the given
    players - typically the free agents. Skater categories for F and D,
    goalie categories for G; players without a rate are skipped.
    """
    samples: dict[tuple[str, str], list[float]] = {}
    for player in players:
        group = position_group(player)
        weight = _pace_weight(player, blend_weight)
        for cat in categories:
            if (cat.name in GOALIE_CATEGORIES) != (group == "G"):
                continue
            value = _player_rate(player, cat.name, weight)
            if value is not None:
                samples.setdefault((group, cat.name), []).append(value)
    rates: ReplacementRates = {group: {} for group in POSITION_GROUPS}
    for (group, name), values in samples.items():
        rates[group][name] = float(np.median(values))
    return rates


def projected_category_balance(rosters: list[list[PreviewPlayer]],
                               categories: list[Category],
                               team_names: list[str],
                               blend_weight: float = 0.0,
                               replacement: ReplacementRates | None = None,
                               ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Full-season pace per team and category, and its z-score across the
    league: every player's blended per-game rate (current-season rate
    weighted by blend_weight, projected rate for the rest; see
    blended_per_game) times his projected games - so with blend_weight 0
    these are ESPN's projected totals. Players with fewer season games than
    min_season_games(blend_weight) are rated on projections alone, so a
    handful of games cannot swing a team. Ratio categories (GAA, SV%) are
    goalie-start-weighted means. Inverted categories are flipped so a
    positive z-score always means "good". The whole roster counts: with
    daily lineups the bench plays nearly every night, so lineup seats are
    not the binding constraint.

    With replacement rates (see replacement_rates), the games a player is
    not projected to play - up to FULL_SEASON_GP / FULL_SEASON_GS - are
    filled at his position group's replacement rate: a roster spot does
    not sit empty, it is filled from the waiver wire, so an injured or
    unprojected pick is worth a replacement-level player, not nothing. A
    roster without a goalie counts one replacement goalie.

    :return: (z-scores, pace totals), both teams x categories
    """
    def games_basis(player: PreviewPlayer, w: float) -> float:
        """Games the player's own rate is scaled to (full-season scale)."""
        if w == 0.0:
            return _stat_games(player.projected_stats)
        return (_stat_games(player.projected_stats)
                or _stat_games(player.season_stats))

    def fill(player: PreviewPlayer, stat: str) -> tuple[float | None, float]:
        """(replacement rate, games it covers) for this player and stat."""
        if replacement is None:
            return None, 0.0
        group = position_group(player)
        full = FULL_SEASON_GS if group == "G" else FULL_SEASON_GP
        basis = games_basis(player, _pace_weight(player, blend_weight))
        return replacement[group].get(stat), max(full - basis, 0.0)

    def pace(player: PreviewPlayer, stat: str) -> float:
        """Full-season total of an additive stat at the blended rate."""
        w = _pace_weight(player, blend_weight)
        if w == 0.0:  # projections only: ESPN's projected total as is
            own = player.projected_stats.get(stat, 0) or 0
        else:
            rate = blended_per_game(player, stat, w)
            own = (rate or 0.0) * games_basis(player, w)
        rate, missing = fill(player, stat)
        return own + (rate or 0.0) * missing

    def ratio(player: PreviewPlayer, stat: str) -> tuple[float | None, float]:
        """(blended ratio, goalie starts it is weighted by)."""
        w = _pace_weight(player, blend_weight)
        if w == 0.0:
            return player.projected_stats.get(stat), games_basis(player, w)
        return blended_ratio(player, stat, w), games_basis(player, w)

    names = [cat.name for cat in categories]
    totals = np.full((len(rosters), len(categories)), np.nan)
    for row, players in enumerate(rosters):
        if replacement is not None and not any(
                _GOALIE_SLOT in p.eligible_slots for p in players):
            # the goalie slot does not stay empty: one replacement goalie
            players = [*players, PreviewPlayer("", "", [_GOALIE_SLOT])]
        for i, cat in enumerate(categories):
            if cat.name in RATIO_CATEGORIES:
                weighted = starts = 0.0
                for p in players:
                    if _GOALIE_SLOT not in p.eligible_slots:
                        continue
                    value, gs = ratio(p, cat.name)
                    if value is not None and gs:
                        weighted += value * gs
                        starts += gs
                    value, missing = fill(p, cat.name)
                    if value is not None and missing:
                        weighted += value * missing
                        starts += missing
                totals[row, i] = weighted / starts if starts else np.nan
            else:
                totals[row, i] = sum(pace(p, cat.name) for p in players)
    index = pd.Index(team_names, name="Team")
    totals_df = pd.DataFrame(totals, index=index, columns=names)
    std = totals_df.std(axis=0, ddof=0)
    z = (totals_df - totals_df.mean(axis=0)) / std.where(std > 0, 1.0)
    z = z.where(totals_df.isna() | (std > 0), 0.0)
    for cat in categories:
        if cat.inverted:
            z[cat.name] *= -1
    return z, totals_df


# a category this far below the league mean is as good as conceded
PUNT_Z = -1.0


def category_outlook(z: pd.DataFrame, totals: pd.DataFrame,
                     categories: list[Category]) -> pd.DataFrame:
    """
    How a team's category profile turns into matchup results: RR Pts = the
    round-robin points (2 per win, 1 per tie) it would take from a week
    against every other team at these totals, Cats/M = categories won per
    matchup, Spread = std of its category z-scores (0 = evenly built) and
    Punts = categories at or below PUNT_Z. Winning one category by a mile
    is one win; conceding several is several losses.

    :param z: z-scores from projected_category_balance (teams x categories)
    :param totals: pace totals from projected_category_balance
    :return: teams (in z order) x [RR Pts, Cats/M, Spread, Punts]
    """
    n = len(z)
    rr = round_robin(totals.to_numpy(dtype=float), categories, list(z.index))
    opponents = max(n - 1, 1)
    return pd.DataFrame({
        "RR Pts": rr["Pts"].to_numpy(),
        "Cats/M": rr["CatsWon"].to_numpy() / opponents,
        "Spread": z.std(axis=1, ddof=0).to_numpy(),
        "Punts": (z <= PUNT_Z).sum(axis=1).to_numpy(),
    }, index=z.index)
