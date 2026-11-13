"""NHL schedule per fantasy matchup: games, off-nights and scores."""
from collections.abc import Callable

import numpy as np
import pandas as pd

from .models import PreviewPlayer
from .seats import open_seat_counts


# a night with at most this many NHL teams playing counts as an off-night
OFF_NIGHT_MAX_TEAMS = 16


def off_night_periods(playing_by_period: dict[int, set[str]],
                      max_teams: int = OFF_NIGHT_MAX_TEAMS) -> set[int]:
    """Scoring periods where few enough teams play to count as an off-night."""
    return {p for p, teams in playing_by_period.items()
            if 0 < len(teams) <= max_teams}


def team_week_schedule(playing_by_period: dict[int, set[str]],
                       week_periods: dict[int, list[int]],
                       off_periods: set[int],
                       ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Games and off-night games per NHL team and matchup week.

    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param week_periods: matchup week -> its scoring periods
    :param off_periods: periods classified as off-nights
    :return: (games, off_nights) DataFrames, index = team names sorted,
        one int column per matchup week
    """
    considered = {p for ps in week_periods.values() for p in ps}
    teams = sorted(set().union(*(playing_by_period.get(p, set())
                                 for p in considered), set()))
    weeks = sorted(week_periods)
    games = pd.DataFrame(0, index=teams, columns=weeks)
    off = pd.DataFrame(0, index=teams, columns=weeks)
    for week in weeks:
        for p in week_periods[week]:
            for team in playing_by_period.get(p, set()):
                games.loc[team, week] += 1
                if p in off_periods:
                    off.loc[team, week] += 1
    return games, off


# open seats beyond this add no streaming value (weekly add limits)
SEAT_CAP = 3
# score bonus of a game on a fully streamable night vs a normal game
SCHEDULE_ALPHA = 1.0
# default weight given to the playoff-only score in the Combined blend
COMBINED_PLAYOFF_WEIGHT = 0.4


def calibrate_night_value(rosters: list[list[PreviewPlayer]],
                          slot_counts: dict[str, int],
                          playing_by_period: dict[int, set[str]],
                          ) -> dict[int, float]:
    """
    Empirical night-value curve: mean open skater seats (capped at SEAT_CAP)
    per count of NHL teams playing, over all rosters and nights of a season.

    :param rosters: fantasy rosters of the calibration season
    :param slot_counts: active lineup slots of that league
    :param playing_by_period: scoring period -> NHL teams with a game that day
    :return: teams playing -> mean capped open skater seats
    """
    periods = [p for p, teams in playing_by_period.items() if teams]
    samples: dict[int, list[int]] = {}
    for roster in rosters:
        seats = open_seat_counts(roster, slot_counts, playing_by_period,
                                 periods)
        for p in periods:
            n = len(playing_by_period[p])
            samples.setdefault(n, []).append(min(seats[p][0], SEAT_CAP))
    return {n: float(np.mean(vals)) for n, vals in sorted(samples.items())}


def night_seat_curve(curve: dict[int, float] | None,
                     ) -> Callable[[int], float]:
    """Expected capped open seats for a night with n teams playing:
    interpolated calibration curve, or a linear proxy when uncalibrated."""
    if not curve:
        return lambda n: SEAT_CAP * max(1.0 - n / 32, 0.0)
    xs = sorted(curve)
    ys = [curve[n] for n in xs]
    return lambda n: float(np.interp(n, xs, ys))


def effective_games(playing_by_period: dict[int, set[str]],
                    week_periods: dict[int, list[int]],
                    seats_by_period: dict[int, float],
                    alpha: float = SCHEDULE_ALPHA) -> pd.Series:
    """
    Effective games per matchup per NHL team: a game counts
    1 + alpha * min(seats, SEAT_CAP) / SEAT_CAP, so games on streamable
    nights are worth up to (1 + alpha) regular games.

    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param week_periods: matchup week -> its scoring periods (the scope)
    :param seats_by_period: period -> (expected) open seats that night
    :return: Series indexed by team name, sorted index
    """
    considered = {p for ps in week_periods.values() for p in ps}
    teams = sorted(set().union(*(playing_by_period.get(p, set())
                                 for p in considered), set()))
    value = dict.fromkeys(teams, 0.0)
    for p in considered:
        bonus = alpha * min(seats_by_period.get(p, 0.0), SEAT_CAP) / SEAT_CAP
        for team in playing_by_period.get(p, set()):
            if team in value:
                value[team] += 1.0 + bonus
    matchups = max(len(week_periods), 1)
    return pd.Series(value).sort_index() / matchups


def schedule_summary(games: pd.DataFrame, off: pd.DataFrame,
                     playoff_weeks: set[int],
                     near_weeks: list[int] | None = None,
                     scores: dict[str, pd.Series] | None = None,
                     ) -> pd.DataFrame:
    """
    Per-team schedule totals, best score (or off-night rate) first.

    :param games: games per team (rows) and matchup week (columns)
    :param off: off-night games, same shape
    :param playoff_weeks: fantasy playoff matchup weeks
    :param near_weeks: near-term matchup weeks; adds games- and
        off-nights-per-matchup columns over just those weeks
    :param scores: score columns (name -> Series by team), shown after Team;
        the first one leads the sort
    :return: DataFrame with Team, scores, Games, G/M, Off, Off/M and (when in
        scope) the near-term G/M, Off/M and PO G, PO Off
    """
    po_cols = [w for w in games.columns if w in playoff_weeks]
    weeks = len(games.columns)
    table = pd.DataFrame({
        "Team": games.index,
        "Games": games.sum(axis=1).to_numpy(),
        "Off": off.sum(axis=1).to_numpy(),
        "G/M": (games.sum(axis=1) / weeks).round(2).to_numpy(),
        "Off/M": (off.sum(axis=1) / weeks).round(2).to_numpy(),
    })
    for i, (name, series) in enumerate((scores or {}).items()):
        table.insert(1 + i, name,
                     series.reindex(games.index).round(2).to_numpy())
    near_col = None
    near_cols = [w for w in games.columns if w in set(near_weeks or [])]
    if near_cols:
        n = len(near_cols)
        table[f"G/M next {n}"] = (games[near_cols].sum(axis=1)
                                  / n).round(2).to_numpy()
        near_col = f"Off/M next {n}"
        table[near_col] = (off[near_cols].sum(axis=1) / n).round(2).to_numpy()
    if po_cols:
        table["PO G"] = games[po_cols].sum(axis=1).to_numpy()
        table["PO Off"] = off[po_cols].sum(axis=1).to_numpy()
    sort_cols = (list(scores or []) + ([near_col] if near_col else [])
                 + ["Off/M", "Off", "Games"])
    return table.sort_values(sort_cols, ascending=False, kind="stable",
                             ignore_index=True)
