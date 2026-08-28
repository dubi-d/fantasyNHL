"""Pure analysis logic for round-robin category scoring."""
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .config import Category

# categories that are per-game ratios (averaged by goalie games, not summed)
RATIO_CATEGORIES = frozenset({"GAA", "SV%"})

# categories only goalies produce (ESPN stat labels)
GOALIE_CATEGORIES = frozenset(
    {"GA", "GAA", "SA", "SV", "SV%", "SO", "GS", "W", "L", "OTL", "MIN ?"})

_GOALIE_SLOT = "Goalie"


@dataclass
class PreviewPlayer:
    """Roster player input for matchup previews (active players only).

    Stat dicts are raw season/projection totals keyed by ESPN stat name,
    including games played ('GP' for skaters, 'GS' for goalies).
    """
    name: str
    pro_team: str
    eligible_slots: list[str]  # active lineup slots only (no Bench/IR)
    season_stats: dict[str, float] = field(default_factory=dict)
    projected_stats: dict[str, float] = field(default_factory=dict)
    injury: str = ""  # ESPN injuryStatus (empty = fine/unknown)


def matchup_result(player_stats: np.ndarray, opponent_stats: np.ndarray,
                   categories: list[Category]) -> np.ndarray:
    """
    Given accumulated stats of a player and his opponent in a week,
    compute W, L, T, CatsWon.

    :param player_stats: 1D numpy array containing category scores
    :param opponent_stats: 1D numpy array containing category scores
    :param categories: category definitions (order matching the stat arrays)
    :return: 1D numpy array [W, L, T, CatsWon]
    """
    cats_won = 0
    cats_tied = 0

    for i, cat in enumerate(categories):
        if cat.inverted:
            cats_won += int(player_stats[i] < opponent_stats[i])
        else:
            cats_won += int(player_stats[i] > opponent_stats[i])
        cats_tied += int(player_stats[i] == opponent_stats[i])

    cats_lost = len(categories) - cats_tied - cats_won
    W = int(cats_won > cats_lost)
    L = int(cats_won < cats_lost)
    T = int(not (W or L))
    return np.array([W, L, T, cats_won])


def round_robin(scores: np.ndarray, categories: list[Category],
                team_names: list[str]) -> pd.DataFrame:
    """
    Calculate W, L, T, Pts, CatsWon if every team played every other team
    simultaneously in the given week.

    :param scores: Scores summary of a single week (teams x categories).
    :param categories: category definitions (order matching the score columns)
    :param team_names: team names by row index
    :return: Summary statistics
    """
    rr_cats = ["W", "L", "T", "CatsWon", "Pts"]
    number_of_teams = scores.shape[0]
    rr_summary = np.zeros((number_of_teams, len(rr_cats)), dtype=int)

    for i in range(number_of_teams):
        for k in range(number_of_teams):
            if i == k:
                # don't match teams against themselves
                continue

            # match team i against all other teams k, accumulate scores
            rr_summary[i, :-1] += matchup_result(scores[i], scores[k], categories)
        rr_summary[i, -1] = 2 * rr_summary[i, 0] + rr_summary[i, 2]  # calculate points

    rr_summary = pd.DataFrame(rr_summary, columns=rr_cats)
    rr_summary["Player"] = team_names[:number_of_teams]
    return rr_summary


def category_win_rates(weekly_scores: np.ndarray, categories: list[Category],
                       team_names: list[str]) -> pd.DataFrame:
    """
    Per-team win percentage per category across all pairwise round-robin
    comparisons of the given weeks. Ties count as half a win, so every
    category column averages 0.5 across the league.

    :param weekly_scores: scores of the weeks to cover (teams x categories x weeks)
    :param categories: category definitions (order matching the score columns)
    :param team_names: team names by row index
    :return: win rates in [0, 1] (teams x categories), plus a Player column
    """
    num_teams, _, num_weeks = weekly_scores.shape
    wins = np.zeros((num_teams, len(categories)))

    for week in range(num_weeks):
        scores = weekly_scores[:, :, week]
        higher = scores[:, None, :] > scores[None, :, :]  # (team, opponent, category)
        lower = scores[:, None, :] < scores[None, :, :]
        tied = scores[:, None, :] == scores[None, :, :]
        for i, cat in enumerate(categories):
            won = lower[:, :, i] if cat.inverted else higher[:, :, i]
            # the diagonal self-comparison always ties, subtract it
            wins[:, i] += won.sum(axis=1) + 0.5 * (tied[:, :, i].sum(axis=1) - 1)

    rates = wins / ((num_teams - 1) * num_weeks)
    table = pd.DataFrame(rates, columns=[cat.name for cat in categories])
    table["Player"] = team_names[:num_teams]
    return table


def category_contestedness(win_rates: pd.DataFrame,
                           categories: list[Category]) -> pd.Series:
    """
    How up-for-grabs each category is, from the spread of the teams' win
    rates: 1 - std / 0.5. 1 means full parity (every team near 0.5),
    0 means structurally locked (win rates split into 1s and 0s).

    :param win_rates: per-team win rates as returned by category_win_rates
    :param categories: category definitions
    :return: contestedness in [0, 1], indexed by category name
    """
    cat_names = [cat.name for cat in categories]
    return 1 - 2 * win_rates[cat_names].std(ddof=0)


def luck(actual_pts, rr_pts, num_opponents: int):
    """
    Schedule luck: actual matchup points minus points expected from
    round-robin strength. Positive means the schedule was favorable.

    :param actual_pts: points from real matchups (2*W + T), scalar or Series
    :param rr_pts: round-robin points over the same weeks, scalar or Series
    :param num_opponents: round-robin matchups per week (teams - 1)
    :return: actual_pts - rr_pts / num_opponents
    """
    return actual_pts - rr_pts / num_opponents


def max_lineup_seats(eligible_slots: list[list[str]],
                     slot_counts: dict[str, int]) -> list[int]:
    """
    Maximum matching (Kuhn's augmenting paths) of players to lineup slots.
    Earlier players get priority: once seated they may be moved to another
    eligible slot, but are never displaced entirely.

    :param eligible_slots: per player, the lineup slots they can fill
    :param slot_counts: available slots (name -> capacity)
    :return: indices of the players that get a seat
    """
    seats = [slot for slot, count in slot_counts.items() for _ in range(count)]
    seated: list[int | None] = [None] * len(seats)  # seat -> player index

    def take_seat(player: int, visited: set[int]) -> bool:
        for s, slot in enumerate(seats):
            if slot in eligible_slots[player] and s not in visited:
                visited.add(s)
                if seated[s] is None or take_seat(seated[s], visited):
                    seated[s] = player
                    return True
        return False

    return [p for p in range(len(eligible_slots)) if take_seat(p, set())]


def seat_counts(players: list[PreviewPlayer], slot_counts: dict[str, int],
                playing_by_period: dict[int, set[str]],
                periods: Iterable[int]) -> list[int]:
    """
    How many games each player can play over the given days: per day, players
    whose NHL team plays compete for the active lineup slots.

    :param players: roster
    :param slot_counts: active lineup slots (name -> capacity)
    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param periods: scoring periods to cover
    :return: playable games per player (matching the players order)
    """
    counts = [0] * len(players)
    for period in periods:
        playing = playing_by_period.get(period, set())
        candidates = [i for i, p in enumerate(players) if p.pro_team in playing]
        eligible = [players[i].eligible_slots for i in candidates]
        for j in max_lineup_seats(eligible, slot_counts):
            counts[candidates[j]] += 1
    return counts


@dataclass
class StreamingContext:
    """Inputs for planning streamer moves in one matchup week.

    The roster is a plain parameter everywhere downstream, so hypothetical
    rosters (after add/drop moves) can be evaluated with the same functions.
    """
    roster: list[PreviewPlayer]  # my team, IR excluded
    slot_counts: dict[str, int]  # active lineup slots (name -> capacity)
    playing_by_period: dict[int, set[str]]  # period -> NHL teams with a game
    periods: list[int]  # all scoring periods of the week
    actionable_periods: list[int]  # today and later: moves still affect them
    period_dates: dict[int, date]
    adds_used: int | None = None  # None = unknown
    adds_limit: int | None = None  # None = no limit / unknown
    # first days of the next week, shown as muted info columns only
    lookahead_periods: list[int] = field(default_factory=list)


def open_seat_counts(players: list[PreviewPlayer],
                     slot_counts: dict[str, int],
                     playing_by_period: dict[int, set[str]],
                     periods: Iterable[int]) -> dict[int, tuple[int, int]]:
    """
    Open active lineup seats per day: seats not fillable by the given players
    on that day. Goalie seats form a separate pool, as only Goalie-eligible
    players can fill them (and they fill nothing else).

    :param players: roster to seat (pass a filtered roster for what-if views)
    :param slot_counts: active lineup slots (name -> capacity)
    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param periods: scoring periods to cover
    :return: period -> (open skater seats, open goalie seats)
    """
    goalie_capacity = slot_counts.get(_GOALIE_SLOT, 0)
    skater_slots = {s: c for s, c in slot_counts.items() if s != _GOALIE_SLOT}
    skater_capacity = sum(skater_slots.values())

    open_seats = {}
    for period in periods:
        playing = playing_by_period.get(period, set())
        candidates = [p for p in players if p.pro_team in playing]
        goalies = sum(_GOALIE_SLOT in p.eligible_slots for p in candidates)
        skater_eligible = [p.eligible_slots for p in candidates
                           if _GOALIE_SLOT not in p.eligible_slots]
        seated = len(max_lineup_seats(skater_eligible, skater_slots))
        open_seats[period] = (skater_capacity - seated,
                              goalie_capacity - min(goalies, goalie_capacity))
    return open_seats


# flexible seats, filled only after specific position seats (least last)
_FLEX_SLOTS = ("Forward", "Util")


def _open_slots(eligible_slots: list[list[str]],
                slot_counts: dict[str, int]) -> dict[str, int]:
    """Open seats per slot in a maximum matching that prefers specific
    position seats: staged augmentation keeps every stage maximal, so
    Forward/Util seats are only used when unavoidable."""
    seats = [slot for slot, count in slot_counts.items()
             if slot not in _FLEX_SLOTS for _ in range(count)]
    stages = [len(seats)]
    for flex in _FLEX_SLOTS:
        seats += [flex] * slot_counts.get(flex, 0)
        if len(seats) > stages[-1]:
            stages.append(len(seats))
    seated: list[int | None] = [None] * len(seats)  # seat -> player index

    def take_seat(player: int, visited: set[int], limit: int) -> bool:
        for s in range(limit):
            if seats[s] in eligible_slots[player] and s not in visited:
                visited.add(s)
                if seated[s] is None or take_seat(seated[s], visited, limit):
                    seated[s] = player
                    return True
        return False

    unseated = list(range(len(eligible_slots)))
    for limit in stages:
        unseated = [p for p in unseated if not take_seat(p, set(), limit)]

    open_seats = dict.fromkeys(slot_counts, 0)
    for s, slot in enumerate(seats):
        if seated[s] is None:
            open_seats[slot] += 1
    return open_seats


def position_open_seats(players: list[PreviewPlayer],
                        slot_counts: dict[str, int],
                        playing_by_period: dict[int, set[str]],
                        periods: Iterable[int]) -> dict[int, dict[str, int]]:
    """
    Open seats per lineup slot per day, disjoint (they sum to the total open
    seats). Players are seated in specific position seats first, so Forward
    and Util seats only show as filled when no other assignment exists.

    :param players: roster to seat (pass a filtered roster for what-if views)
    :param slot_counts: active lineup slots (name -> capacity)
    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param periods: scoring periods to cover
    :return: period -> {slot -> open seats}, slots in slot_counts order
    """
    open_by_period = {}
    for period in periods:
        playing = playing_by_period.get(period, set())
        eligible = [p.eligible_slots for p in players if p.pro_team in playing]
        open_by_period[period] = _open_slots(eligible, slot_counts)
    return open_by_period


def rank_streaming_candidates(candidates: list[PreviewPlayer],
                              keep_roster: list[PreviewPlayer],
                              slot_counts: dict[str, int],
                              playing_by_period: dict[int, set[str]],
                              periods: list[int]) -> pd.DataFrame:
    """
    Rank streaming candidates by how many days they would actually fill an
    open skater seat if added to the given roster. A candidate fits a day
    when seating them reduces that day's open skater seats (i.e. their team
    plays and the matching finds them a seat without displacing anyone).

    :param candidates: free agents, input order is the final tiebreak
    :param keep_roster: roster after dropping the designated streamers
    :param slot_counts: active lineup slots (name -> capacity)
    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param periods: the (actionable) periods to consider
    :return: DataFrame with Player, Team, Injury, Slots (eligible slots), one
        column per period ('fit', 'play' or ''), Fit (days seated) and Games
        (days with a game); best fit first, then most games
    """
    base = open_seat_counts(keep_roster, slot_counts, playing_by_period,
                            periods)
    rows = []
    for cand in candidates:
        added = open_seat_counts(keep_roster + [cand], slot_counts,
                                 playing_by_period, periods)
        days = {}
        for p in periods:
            if added[p][0] < base[p][0]:
                days[p] = "fit"
            elif cand.pro_team in playing_by_period.get(p, set()):
                days[p] = "play"
            else:
                days[p] = ""
        rows.append({"Player": cand.name, "Team": cand.pro_team,
                     "Injury": cand.injury, "Slots": cand.eligible_slots,
                     **days,
                     "Fit": sum(v == "fit" for v in days.values()),
                     "Games": sum(v != "" for v in days.values())})
    table = pd.DataFrame(rows, columns=["Player", "Team", "Injury", "Slots",
                                        *periods, "Fit", "Games"])
    return table.sort_values(["Fit", "Games"], ascending=False,
                             kind="stable", ignore_index=True)


def team_gap_coverage(playing_by_period: dict[int, set[str]],
                      open_periods: set[int],
                      periods: list[int]) -> pd.DataFrame:
    """
    Rank NHL teams by how many open-seat days their schedule covers.

    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param open_periods: periods that have at least one open seat
    :param periods: the (actionable) periods to consider
    :return: DataFrame with Team, one bool column per period, Cover (games on
        open-seat days) and Games (all games), best coverage first
    """
    teams = set().union(*(playing_by_period.get(p, set()) for p in periods),
                        set())
    rows = []
    for team in sorted(teams):
        plays = {p: team in playing_by_period.get(p, set()) for p in periods}
        rows.append({"Team": team, **plays,
                     "Cover": sum(plays[p] for p in periods
                                  if p in open_periods),
                     "Games": sum(plays.values())})
    table = pd.DataFrame(rows, columns=["Team", *periods, "Cover", "Games"])
    return table.sort_values(["Cover", "Games"], ascending=False,
                             ignore_index=True)


def _blend(season: float | None, projected: float | None,
           weight: float) -> float | None:
    """Linear blend, falling back to whichever value exists."""
    if season is None:
        return projected
    if projected is None:
        return season
    return weight * season + (1 - weight) * projected


def _stat_games(stats: dict[str, float]) -> float:
    return stats.get("GP") or stats.get("GS") or 0


def blended_per_game(player: PreviewPlayer, stat: str,
                     weight: float) -> float | None:
    """
    Per-game rate of an additive stat, blending current-season and projected
    rates. Missing stat keys count as 0 for a player with games played.

    :param weight: weight of the current-season rate (0 = projection only)
    :return: blended per-game rate, or None if neither split has games
    """
    def rate(stats: dict[str, float]) -> float | None:
        games = _stat_games(stats)
        return stats.get(stat, 0.0) / games if games else None

    return _blend(rate(player.season_stats), rate(player.projected_stats), weight)


def blended_ratio(player: PreviewPlayer, stat: str,
                  weight: float) -> float | None:
    """Blend a ratio stat (e.g. GAA) directly; None if neither split has it."""
    return _blend(player.season_stats.get(stat),
                  player.projected_stats.get(stat), weight)


def preview_week(players: list[PreviewPlayer], slot_counts: dict[str, int],
                 playing_by_period: dict[int, set[str]],
                 remaining_periods: list[int],
                 actual_scores: np.ndarray, categories: list[Category],
                 blend_weight: float, actual_games: int = 0,
                 actual_goalie_games: int = 0) -> tuple[int, np.ndarray]:
    """
    Playable games and predicted final category scores of one team's matchup
    week: actual accumulated scores plus per-game-rate predictions over the
    remaining days. Ratio categories (GAA, SV%) are averaged per goalie game
    instead of summed; the actual portion is weighted by the goalie games
    actually played on the elapsed days.

    :param players: current roster (active players only)
    :param slot_counts: active lineup slots (name -> capacity)
    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param remaining_periods: the scoring periods that still have to be predicted
    :param actual_scores: accumulated real category scores so far (config order)
    :param categories: category definitions
    :param blend_weight: weight of current-season rates vs projections
    :param actual_games: player games actually counted on the elapsed days
    :param actual_goalie_games: goalie games actually counted on the elapsed days
    :return: (actual plus playable remaining games, predicted category scores)
    """
    remaining = seat_counts(players, slot_counts, playing_by_period,
                            remaining_periods)
    games = int(actual_games) + sum(remaining)

    is_goalie = [_GOALIE_SLOT in p.eligible_slots for p in players]

    totals = np.zeros(len(categories))
    for i, cat in enumerate(categories):
        if cat.name in RATIO_CATEGORIES:
            weighted = actual_scores[i] * actual_goalie_games
            goalie_games = actual_goalie_games
            for player, n, goalie in zip(players, remaining, is_goalie):
                if not (goalie and n):
                    continue
                value = blended_ratio(player, cat.name, blend_weight)
                if value is None:
                    continue
                weighted += value * n
                goalie_games += n
            totals[i] = weighted / goalie_games if goalie_games else actual_scores[i]
        else:
            totals[i] = actual_scores[i] + sum(
                (blended_per_game(player, cat.name, blend_weight) or 0.0) * n
                for player, n in zip(players, remaining))
    return games, totals
