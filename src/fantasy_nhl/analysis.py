"""Pure analysis logic for round-robin category scoring."""
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from statistics import NormalDist

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


@dataclass
class DraftPick:
    """One draft pick joined with ESPN's current info on the player."""
    team_row: int  # drafting fantasy team (LeagueData row)
    round: int
    pick_in_round: int
    overall: int
    player_id: int
    name: str
    position: str  # ESPN default position name (e.g. "Goalie")
    eligible_slots: list[str] = field(default_factory=list)  # no Bench/IR
    adp: float | None = None  # ESPN average draft position (None = unknown)
    pct_owned: float | None = None  # ESPN roster% today
    pct_change: float | None = None  # ESPN roster% change over 7 days
    espn_rank: int | None = None  # ESPN standard draft rank
    projected_stats: dict[str, float] = field(default_factory=dict)
    rostered_by: int | None = None  # fantasy team row today (None = free agent)


@dataclass
class RosterPlayer(PreviewPlayer):
    """A rostered or free-agent player with ESPN's ownership and origin
    info (all lineup slots, including Bench and IR)."""
    player_id: int = 0
    position: str = ""  # ESPN default position name
    acquisition: str = ""  # DRAFT / ADD / TRADE ("" for free agents)
    team_row: int | None = None  # fantasy team row (None = free agent)
    lineup_slot: str = ""  # current slot name ("" for free agents)
    pct_owned: float | None = None
    pct_change: float | None = None  # 7-day roster% change
    espn_rank: int | None = None
    adp: float | None = None


@dataclass
class TransactionCounts:
    """A fantasy team's season-to-date transaction counters."""
    adds: int = 0
    drops: int = 0
    trades: int = 0


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


def weekly_points_timeline(weekly_scores: np.ndarray, categories: list[Category],
                           team_names: list[str]) -> pd.DataFrame:
    """
    Round-robin Pts per team for every given week.

    :param weekly_scores: scores of the weeks to cover (teams x categories x weeks)
    :param categories: category definitions (order matching the score columns)
    :param team_names: team names by row index
    :return: Pts table (index=team names, columns=week numbers 1..n)
    """
    num_weeks = weekly_scores.shape[2]
    pts = {week: round_robin(weekly_scores[:, :, week - 1],
                             categories, team_names)["Pts"].to_numpy()
           for week in range(1, num_weeks + 1)}
    return pd.DataFrame(pts, index=team_names[:weekly_scores.shape[0]])


def rank_timeline(cumulative: pd.DataFrame) -> pd.DataFrame:
    """Per-week rank from cumulative points (1 = most points;
    ties share the better rank)."""
    return cumulative.rank(axis=0, ascending=False, method="min").astype(int)


def trailing_points(timeline: pd.DataFrame, window: int) -> pd.DataFrame:
    """Sum of each team's Pts over the last `window` week columns
    (partial windows at the season start)."""
    return timeline.T.rolling(window, min_periods=1).sum().T.astype(int)


def average_points(timeline: pd.DataFrame) -> pd.DataFrame:
    """Average weekly Pts up to and including each week."""
    return timeline.cumsum(axis=1) / np.arange(1, timeline.shape[1] + 1)


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


def pick_weekly_awards(table: pd.DataFrame) -> dict[str, pd.Series]:
    """
    Pick award rows for one matchup week.

    :param table: one row per team with columns Player, Pts (round-robin
        points), Luck and Result ('W'/'L'/'T'/'NA'), index = team row
    :return: award name -> table row; 'best'/'worst' by round-robin points,
        'luckiest_win' = winner with the highest luck (weakest winner),
        'biggest_choke' = loser with the lowest luck (strongest loser);
        win/loss awards omitted when nobody won/lost
    """
    awards = {"best": table.loc[table["Pts"].idxmax()],
              "worst": table.loc[table["Pts"].idxmin()]}
    winners = table[table["Result"] == "W"]
    if not winners.empty:
        awards["luckiest_win"] = winners.loc[winners["Luck"].idxmax()]
    losers = table[table["Result"] == "L"]
    if not losers.empty:
        awards["biggest_choke"] = losers.loc[losers["Luck"].idxmin()]
    return awards


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
    """Blend a ratio stat (e.g. GAA) directly, ignoring splits without
    games (ESPN reports placeholder ratios for goalies with no starts);
    None if neither split has games and the stat."""
    def value(stats: dict[str, float]) -> float | None:
        return stats.get(stat) if _stat_games(stats) else None

    return _blend(value(player.season_stats), value(player.projected_stats),
                  weight)


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


_DEFENSE_POSITION = "Defense"
_GOALIE_POSITION = "Goalie"


def draft_pick_table(picks: list[DraftPick], team_names: list[str],
                     n_teams: int) -> pd.DataFrame:
    """
    One row per draft pick in draft order. Value = ADP − overall pick, so a
    positive value means the player went later than ESPN's average draft
    position (a steal), negative means a reach. Players without an ESPN ADP
    are floored at one pick after the last one (flagged in 'ADP?').

    :param n_teams: picks per round, to express Value in rounds as well
    """
    total = max((p.overall for p in picks), default=0)
    rows = []
    for p in picks:
        missing = p.adp is None or p.adp <= 0
        adp = float(total + 1) if missing else float(p.adp)
        rows.append({
            "TeamRow": p.team_row,
            "Team": team_names[p.team_row],
            "Rd": p.round,
            "Pick": p.pick_in_round,
            "Overall": p.overall,
            "Player": p.name,
            "Pos": p.position,
            "ADP": adp,
            "ADP?": missing,
            "Value": adp - p.overall,
            "ValueRd": (adp - p.overall) / n_teams,
            "Own%": p.pct_owned,
            "Chg": p.pct_change,
            "Rank": p.espn_rank,
            "NowOn": (None if p.rostered_by is None
                      else team_names[p.rostered_by]),
        })
    return pd.DataFrame(rows, columns=[
        "TeamRow", "Team", "Rd", "Pick", "Overall", "Player", "Pos", "ADP",
        "ADP?", "Value", "ValueRd", "Own%", "Chg", "Rank", "NowOn"])


def draft_team_summary(table: pd.DataFrame) -> pd.DataFrame:
    """
    Per drafting team (index = team row): average and total pick Value, the
    best steal and biggest reach, goalie/defense counts, the round of the
    first goalie and how many own picks are still on the roster.
    """
    rows = []
    index = []
    for row, group in table.groupby("TeamRow", sort=True):
        index.append(row)
        best = group.loc[group["Value"].idxmax()]
        worst = group.loc[group["Value"].idxmin()]
        goalies = group[group["Pos"] == _GOALIE_POSITION]
        rows.append({
            "Player": group["Team"].iloc[0],
            "Avg value": group["Value"].mean(),
            "Total": group["Value"].sum(),
            "Best steal": f"{best['Player']} ({best['Value']:+.0f})",
            "Biggest reach": f"{worst['Player']} ({worst['Value']:+.0f})",
            "G": len(goalies),
            "1st G": int(goalies["Rd"].min()) if len(goalies) else None,
            "D": int((group["Pos"] == _DEFENSE_POSITION).sum()),
            "Kept": int((group["NowOn"] == group["Team"]).sum()),
            "Picks": len(group),
        })
    return pd.DataFrame(rows, index=pd.Index(index, name="TeamRow"))


def draft_value_grid(table: pd.DataFrame) -> pd.DataFrame:
    """Pick Value per team (rows, team-row order) and round (columns R1..Rn);
    several picks in one round add up."""
    grid = table.pivot_table(index="TeamRow", columns="Rd", values="Value",
                             aggfunc="sum")
    names = table.drop_duplicates("TeamRow").set_index("TeamRow")["Team"]
    grid.index = pd.Index([names[row] for row in grid.index], name="Team")
    grid.columns = [f"R{r}" for r in grid.columns]
    return grid


def draft_extremes(table: pd.DataFrame,
                   n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """League-wide top-n steals (largest Value) and reaches (smallest);
    ties at the cutoff keep draft order."""
    return (table.nlargest(n, "Value", keep="first"),
            table.nsmallest(n, "Value", keep="first"))


def drafted_rosters(picks: list[DraftPick],
                    n_teams: int) -> list[list[RosterPlayer]]:
    """Draft-day rosters (projections only, drafted by the drafting team)
    by team row."""
    rosters: list[list[RosterPlayer]] = [[] for _ in range(n_teams)]
    for p in picks:
        rosters[p.team_row].append(RosterPlayer(
            name=p.name, pro_team="", eligible_slots=list(p.eligible_slots),
            projected_stats=dict(p.projected_stats), player_id=p.player_id,
            position=p.position, acquisition=ACQUIRED_DRAFT,
            team_row=p.team_row, pct_owned=p.pct_owned,
            pct_change=p.pct_change, espn_rank=p.espn_rank, adp=p.adp))
    return rosters


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


def _player_rate(player: PreviewPlayer, stat: str,
                 weight: float) -> float | None:
    if stat in RATIO_CATEGORIES:
        return blended_ratio(player, stat, weight)
    return blended_per_game(player, stat, weight)


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


_IR_SLOT = "IR"
_DEFENSE_SLOT = "Defense"
ACQUIRED_DRAFT = "DRAFT"
ACQUIRED_ADD = "ADD"
ACQUIRED_TRADE = "TRADE"
POSITION_GROUPS = ("F", "D", "G")


def position_group(player: PreviewPlayer) -> str:
    """'F', 'D' or 'G' by lineup eligibility (goalie beats defense)."""
    if _GOALIE_SLOT in player.eligible_slots:
        return "G"
    return "D" if _DEFENSE_SLOT in player.eligible_slots else "F"


def _rank_z(table: pd.DataFrame) -> pd.DataFrame:
    """Normal quantile of each column's percentile rank (ties averaged):
    median 0, 84th percentile +1, 98th +2. Rank-based, so a runaway leader
    in one category is not credited beyond his rank."""
    normal = NormalDist()
    n = table.notna().sum(axis=0)
    pct = (table.rank(axis=0) - 0.5) / n
    return pct.map(lambda p: np.nan if pd.isna(p) else normal.inv_cdf(p))


# season games a player needs for a Score over a FULL season; scaled by the
# elapsed fraction (2025-26 pool: per-game rates settle around 20 GP)
MIN_SCORE_GAMES = 20


def min_season_games(blend_weight: float) -> int:
    """Season games required for a Score at this point of the season
    (0 before the season starts, MIN_SCORE_GAMES once it is over)."""
    return math.ceil(MIN_SCORE_GAMES * blend_weight)


def player_value_scores(players: list[PreviewPlayer], categories: list[Category],
                        blend_weight: float) -> list[float | None]:
    """
    Stat-based value of every player in a pool: the mean, over categories,
    of the normal quantile of the player's percentile rank in the blended
    per-game rate of that category, within the pool and within the
    player's position group - forwards and defensemen separately over the
    skater categories, goalies over the goalie categories - with inverted
    categories flipped so higher is always better. Grouping by position
    keeps defense-only categories (DEF, BLK) from inflating every
    defenseman relative to forwards; ranking (rather than z-scoring the
    raw rates) keeps one runaway category from dominating the score.
    Players with fewer season games than min_season_games(blend_weight)
    get no Score: too few games for a rate, and falling back to the
    projection would credit them for games they did not play.

    :return: one score per player (None without enough games)
    """
    required = min_season_games(blend_weight)
    groups = np.array([position_group(p) for p in players])
    rates = np.full((len(players), len(categories)), np.nan)
    for i, player in enumerate(players):
        if _stat_games(player.season_stats) < required:
            continue
        is_goalie = groups[i] == "G"
        for j, cat in enumerate(categories):
            if (cat.name in GOALIE_CATEGORIES) != is_goalie:
                continue
            if cat.name in RATIO_CATEGORIES:
                value = blended_ratio(player, cat.name, blend_weight)
            else:
                value = blended_per_game(player, cat.name, blend_weight)
            if value is not None:
                rates[i, j] = value
    scores = pd.Series(np.nan, index=range(len(players)))
    for group in POSITION_GROUPS:
        members = groups == group
        if not members.any():
            continue
        z = _rank_z(pd.DataFrame(rates[members]))
        for j, cat in enumerate(categories):
            if cat.inverted:
                z[j] *= -1
        scores[np.flatnonzero(members)] = z.mean(axis=1).to_numpy()
    return [None if pd.isna(s) else float(s) for s in scores]


def percentile_ranks(values: Iterable[float | None]) -> list[float | None]:
    """Percentile rank (0-100, ties averaged) of each value among the
    non-missing ones; missing values stay None."""
    series = pd.Series(list(values), dtype=float)
    ranks = series.rank(pct=True) * 100
    return [None if pd.isna(r) else float(r) for r in ranks]


def player_values(pool: list[RosterPlayer], categories: list[Category],
                  blend_weight: float) -> pd.DataFrame:
    """
    Value table of a player pool indexed by player id: position Group,
    Score (see player_value_scores), percentile ranks of roster% (OwnPct)
    and Score (ScorePct) within the pool's position group, and
    Gap = OwnPct - ScorePct (positive: the crowd rosters the player more
    than the stats justify).
    """
    scores = player_value_scores(pool, categories, blend_weight)
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
    return table


def _player_row(player: RosterPlayer, values: pd.DataFrame,
                team_names: list[str]) -> dict:
    value = (values.loc[player.player_id]
             if player.player_id in values.index else None)
    return {
        "Player": player.name,
        "Pos": player.position,
        "TeamRow": player.team_row,
        "Team": ("FA" if player.team_row is None
                 else team_names[player.team_row]),
        "Slot": player.lineup_slot,
        "Acq": player.acquisition,
        "GP": int(_stat_games(player.season_stats)),
        "Own%": player.pct_owned,
        "Chg": player.pct_change,
        "Score": None if value is None else value["Score"],
        "Gap": None if value is None else value["Gap"],
        "Injury": player.injury,
    }


_PLAYER_COLUMNS = ["Player", "Pos", "TeamRow", "Team", "Slot", "Acq", "GP",
                   "Own%", "Chg", "Score", "Gap", "Injury"]


def player_table(players: Iterable[RosterPlayer], values: pd.DataFrame,
                 team_names: list[str]) -> pd.DataFrame:
    """One row per player with ownership, origin and value columns."""
    rows = [_player_row(p, values, team_names) for p in players]
    return pd.DataFrame(rows, columns=_PLAYER_COLUMNS).astype(
        {"Own%": float, "Chg": float, "Score": float, "Gap": float})


def roster_origins(rosters: list[list[RosterPlayer]], values: pd.DataFrame,
                   team_names: list[str],
                   counters: list[TransactionCounts]) -> pd.DataFrame:
    """
    Per team (index = team row): roster size and how it was assembled
    (drafted, added, traded-in, on IR), the average roster% and Score of
    its players, and the season's add/drop/trade counters.
    """
    rows = []
    for row, players in enumerate(rosters):
        table = player_table(players, values, team_names)
        rows.append({
            "Player": team_names[row],
            "Size": len(players),
            "Drafted": int((table["Acq"] == ACQUIRED_DRAFT).sum()),
            "Added": int((table["Acq"] == ACQUIRED_ADD).sum()),
            "Traded": int((table["Acq"] == ACQUIRED_TRADE).sum()),
            "IR": sum(p.lineup_slot == _IR_SLOT for p in players),
            "Avg Own%": table["Own%"].mean(),
            "Avg Score": table["Score"].mean(),
            "Adds": counters[row].adds,
            "Drops": counters[row].drops,
            "Trades": counters[row].trades,
        })
    return pd.DataFrame(rows, index=pd.Index(range(len(rosters)),
                                            name="TeamRow"))


def draft_return(picks: list[DraftPick], values: pd.DataFrame,
                 team_names: list[str],
                 players: dict[int, RosterPlayer] | None = None) -> pd.DataFrame:
    """
    How every draft pick has panned out: Return = the player's Score
    percentile (within his position group in the pool) minus the percentile
    of his draft slot among the picks (pick 1 = 100), in percentage points.
    Positive: producing more than the slot he cost; negative: a bust. A
    pick who is in the pool but has no Score (too few games) counts as the
    0th percentile - he delivered nothing for the slot. Roster% is carried
    along for information only - it reflects ESPN's default settings, not
    this league's categories.

    :param players: current player info by id, for the GP column
    """
    players = players or {}
    slot_pct = percentile_ranks(-p.overall for p in picks)
    rows = []
    for pick, slot in zip(picks, slot_pct):
        value = (values.loc[pick.player_id]
                 if pick.player_id in values.index else None)
        score_pct = None if value is None else value["ScorePct"]
        if value is not None and pd.isna(score_pct):
            score_pct = 0.0
        player = players.get(pick.player_id)
        rows.append({
            "Player": pick.name,
            "Pos": pick.position,
            "TeamRow": pick.team_row,
            "Team": team_names[pick.team_row],
            "Rd": pick.round,
            "Pick": pick.pick_in_round,
            "Overall": pick.overall,
            "GP": int(_stat_games(player.season_stats)) if player else None,
            "Own%": pick.pct_owned,
            "Score": None if value is None else value["Score"],
            "Return": (None if score_pct is None or pd.isna(score_pct)
                       else float(score_pct) - slot),
            "NowOn": (None if pick.rostered_by is None
                      else team_names[pick.rostered_by]),
        })
    return pd.DataFrame(rows, columns=[
        "Player", "Pos", "TeamRow", "Team", "Rd", "Pick", "Overall", "GP",
        "Own%", "Score", "Return", "NowOn"]).astype(
            {"GP": "Int64", "Own%": float, "Score": float, "Return": float})


def acquisition_summary(rosters: list[list[RosterPlayer]],
                        values: pd.DataFrame, team_names: list[str],
                        acquisition: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Players each team acquired a given way (ADD = free-agent/waiver pickups,
    TRADE = traded in), ranked by Score, plus a per-team summary (index =
    team row) with the count, average roster%/Score and the best player.
    """
    acquired = [p for players in rosters for p in players
                if p.acquisition == acquisition]
    table = player_table(acquired, values, team_names)
    table = table.sort_values("Score", ascending=False, na_position="last",
                              kind="stable").reset_index(drop=True)
    rows = []
    for row, name in enumerate(team_names):
        own = table[table["TeamRow"] == row]
        best = own.iloc[0]["Player"] if len(own) and not pd.isna(
            own.iloc[0]["Score"]) else None
        rows.append({
            "Player": name,
            "Count": len(own),
            "Avg Own%": own["Own%"].mean() if len(own) else None,
            "Avg Score": own["Score"].mean() if len(own) else None,
            "Best": best,
        })
    summary = pd.DataFrame(rows, index=pd.Index(range(len(team_names)),
                                                name="TeamRow"))
    return summary.astype({"Avg Own%": float, "Avg Score": float}), table


def market_gaps(roster: list[RosterPlayer], free_agents: list[RosterPlayer],
                values: pd.DataFrame, team_names: list[str],
                n: int, n_goalies: int) -> tuple[pd.DataFrame, pd.DataFrame,
                                                 pd.DataFrame]:
    """
    Drop candidates (the roster's n lowest-scoring players, weakest first;
    players without a Score come first) and free-agent targets - the n
    highest-scoring skaters and the n_goalies highest-scoring goalies,
    separately since Scores compare within a position group - each with
    the crowd-vs-stats Gap.
    """
    drops = player_table(roster, values, team_names)
    drops = drops.sort_values("Score", na_position="first",
                              kind="stable").head(n).reset_index(drop=True)
    skaters = [p for p in free_agents if position_group(p) != "G"]
    goalies = [p for p in free_agents if position_group(p) == "G"]

    def top(players: list[RosterPlayer], limit: int) -> pd.DataFrame:
        table = player_table(players, values, team_names)
        return table.sort_values("Score", ascending=False, na_position="last",
                                 kind="stable").head(limit).reset_index(drop=True)
    return drops, top(skaters, n), top(goalies, n_goalies)
