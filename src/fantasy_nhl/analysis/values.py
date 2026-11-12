"""Player value: Score, category rates, percentiles and profiles."""
import numpy as np
import pandas as pd

from ..config import Category
from .models import (
    GOALIE_CATEGORIES,
    POSITION_GROUPS,
    PreviewPlayer,
    RosterPlayer,
    position_group,
)
from .ranking import _rank_pct, _rank_z, percentile_ranks
from .rates import StatBasis, _stat_games, has_projection, player_rate


def player_value_scores(players: list[PreviewPlayer], categories: list[Category],
                        basis: StatBasis) -> list[float | None]:
    """
    Stat-based value of every player in a pool: the mean, over categories,
    of the normal quantile of the player's percentile rank in the per-game
    rate of that category (see player_rate), within the pool and within the
    player's position group - forwards and defensemen separately over the
    skater categories, goalies over the goalie categories - with inverted
    categories flipped so higher is always better. Grouping by position
    keeps defense-only categories (DEF, BLK) from inflating every
    defenseman relative to forwards; ranking (rather than z-scoring the
    raw rates) keeps one runaway category from dominating the score.
    Players with fewer season games than basis.min_games get no Score: too
    few games for a rate, and falling back to the projection would credit
    them for games they did not play.

    :return: one score per player (None without enough games)
    """
    pct = category_percentiles(
        category_rates(players, categories, basis),
        [position_group(p) for p in players], categories)
    scores = _rank_z(pct).mean(axis=1)
    return [None if pd.isna(s) else float(s) for s in scores]


def category_rates(players: list[PreviewPlayer], categories: list[Category],
                   basis: StatBasis) -> pd.DataFrame:
    """
    Per-game rate (ratio categories: the ratio; see player_rate) of every
    player in every category of his kind (skater or goalie categories), one
    row per player in input order, one column per category name. NaN for
    the other kind's categories and for players with fewer season games
    than basis.min_games.
    """
    required = basis.min_games
    names = [cat.name for cat in categories]
    rates = pd.DataFrame(np.nan, index=range(len(players)), columns=names)
    for i, player in enumerate(players):
        if _stat_games(player.season_stats) < required:
            continue
        is_goalie = position_group(player) == "G"
        for cat in categories:
            if (cat.name in GOALIE_CATEGORIES) != is_goalie:
                continue
            value = player_rate(player, cat.name, basis)
            if value is not None:
                rates.loc[i, cat.name] = value
    return rates


def category_percentiles(rates: pd.DataFrame, groups: list[str],
                         categories: list[Category]) -> pd.DataFrame:
    """Percentile (0-100, higher = better) of each rate within its row's
    position group; NaN where the rate is missing."""
    groups = np.asarray(groups)
    pct = pd.DataFrame(np.nan, index=rates.index, columns=rates.columns)
    for group in POSITION_GROUPS:
        members = groups == group
        if members.any():
            pct.loc[members] = _rank_pct(rates.loc[members], categories)
    return pct


def season_totals(players: list[PreviewPlayer],
                  categories: list[Category]) -> pd.DataFrame:
    """Raw season totals (ratio categories: season value) per player and
    category of his kind, indexed by player id; NaN without games."""
    rows = []
    for player in players:
        stats = player.season_stats
        is_goalie = position_group(player) == "G"
        has_games = bool(_stat_games(stats))
        rows.append({
            cat.name: (stats.get(cat.name, 0.0)
                       if has_games and (cat.name in GOALIE_CATEGORIES) == is_goalie
                       else np.nan)
            for cat in categories})
    return pd.DataFrame(
        rows, columns=[cat.name for cat in categories], dtype=float,
        index=pd.Index([p.player_id for p in players], name="player_id"))


# category profile: Peak = mean percentile of the best PEAK_CATS categories,
# Breadth = mean percentile of the rest, Spec = Peak - Breadth (shape)
PEAK_CATS = 2
ELITE_PCT = 90
HOLE_PCT = 25
# Type = tier by Level (Score percentile in group) + shape by Spec; Spec
# quartiles in the 2025-26 pool ~27 / 35 / 45 for F and D alike
TIER_ELITE = 90
TIER_SOLID = 60
SPEC_HIGH = 40
SPEC_LOW = 25


def _player_type(level: float, spec: float) -> str:
    if pd.isna(level):
        return ""
    # classify on the displayed (whole-number) values
    level = round(level)
    tier = ("Elite" if level >= TIER_ELITE
            else "Solid" if level >= TIER_SOLID else "Depth")
    if pd.isna(spec):
        return tier
    spec = round(spec)
    if spec >= SPEC_HIGH:
        return f"{tier} specialist"
    return f"{tier} all-rounder" if spec <= SPEC_LOW else tier


def category_profiles(pool: list[PreviewPlayer], categories: list[Category],
                      basis: StatBasis
                      ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Per-category strength of every player in a pool, within his position
    group (see category_rates / category_percentiles).

    :return: (rates, pcts, summary), all indexed by player id; summary has
        Group, Score (as player_value_scores), Level (Score percentile in
        the group), Peak, Breadth, Spec (Peak - Breadth; NaN with at most
        PEAK_CATS cats), Elite (cats at or above ELITE_PCT), Holes (cats at
        or below HOLE_PCT), Best (names of the top PEAK_CATS cats) and Type
        (Elite / Solid / Depth by Level, + specialist / all-rounder by Spec)
    """
    index = pd.Index([p.player_id for p in pool], name="player_id")
    groups = [position_group(p) for p in pool]
    rates = category_rates(pool, categories, basis)
    pct = category_percentiles(rates, groups, categories)
    scores = _rank_z(pct).mean(axis=1)
    levels = pd.Series(np.nan, index=scores.index)
    for group in POSITION_GROUPS:
        members = np.asarray(groups) == group
        if members.any():
            levels[members] = pd.array(percentile_ranks(scores[members]),
                                       dtype=float)
    rows = []
    for i in range(len(pool)):
        ranked = pct.iloc[i].dropna().sort_values(ascending=False, kind="stable")
        top, rest = ranked.iloc[:PEAK_CATS], ranked.iloc[PEAK_CATS:]
        peak = top.mean() if len(top) else np.nan
        breadth = rest.mean() if len(rest) else np.nan
        rows.append({
            "Level": levels.iloc[i],
            "Peak": peak,
            "Breadth": breadth,
            "Spec": peak - breadth,
            "Elite": int((ranked >= ELITE_PCT).sum()) if len(ranked) else None,
            "Holes": int((ranked <= HOLE_PCT).sum()) if len(ranked) else None,
            "Best": "/".join(top.index),
            "Type": _player_type(levels.iloc[i], peak - breadth),
        })
    summary = pd.DataFrame(
        rows, index=index,
        columns=["Level", "Peak", "Breadth", "Spec", "Elite", "Holes", "Best",
                 "Type"]).astype(
        {"Level": float, "Peak": float, "Breadth": float, "Spec": float,
         "Elite": "Int64", "Holes": "Int64"})
    summary.insert(0, "Group", groups)
    summary.insert(1, "Score", scores.to_numpy())
    rates.index = index
    pct.index = index
    return rates, pct, summary


def player_values(pool: list[RosterPlayer], categories: list[Category],
                  basis: StatBasis) -> pd.DataFrame:
    """
    Value table of a player pool indexed by player id: position Group,
    Score (see player_value_scores), percentile ranks of roster% (OwnPct)
    and Score (ScorePct) within the pool's position group,
    Gap = OwnPct - ScorePct (positive: the crowd rosters the player more
    than the stats justify), and NoProj: a blended Score that rests on
    season stats alone because ESPN has no projection for the player.
    """
    scores = player_value_scores(pool, categories, basis)
    table = pd.DataFrame({
        "Group": [position_group(p) for p in pool],
        "Score": pd.array(scores, dtype=float),
        "OwnPct": pd.array([p.pct_owned for p in pool], dtype=float),
        "ScorePct": np.nan,
    }, index=pd.Index([p.player_id for p in pool], name="player_id"))
    for group in POSITION_GROUPS:
        members = table["Group"] == group
        if members.any():
            table.loc[members, "ScorePct"] = pd.array(
                percentile_ranks(table.loc[members, "Score"]), dtype=float)
            table.loc[members, "OwnPct"] = pd.array(
                percentile_ranks(table.loc[members, "OwnPct"]), dtype=float)
    table["Gap"] = table["OwnPct"] - table["ScorePct"]
    table["NoProj"] = [
        not basis.season_only and score is not None and not has_projection(p)
        for p, score in zip(pool, scores)]
    return table
