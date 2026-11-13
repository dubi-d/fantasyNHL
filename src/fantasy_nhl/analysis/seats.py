"""Lineup seats: who can play when, open seats, streaming candidates."""
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .models import _GOALIE_SLOT, PreviewPlayer, RosterPlayer


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
    # Saved ESPN slot by scoring period and player ID; missing means unknown.
    daily_lineup_slots: dict[int, dict[int, str]] = field(default_factory=dict)
    # Display-only current IR assignments; never included in seat calculations.
    ir_roster: list[RosterPlayer] = field(default_factory=list)


def lineup_game_counts(players: list[PreviewPlayer], slot_counts: dict[str, int],
                       playing_by_period: dict[int, set[str]],
                       periods: Iterable[int],
                       daily_lineup_slots: dict[int, dict[int, str]],
                       ) -> list[int | None]:
    """Scheduled games assigned to active ESPN slots, not hypothetical seats.

    A missing assignment on a scheduled day makes the player's total unknown
    (None). Bench/IR games don't count. Callers choose the exact dates, including
    today for streaming; current IR display rows are handled separately.
    """
    periods = list(periods)
    known_slots = set(slot_counts) | {"Bench", "IR"}
    counts: list[int | None] = []
    for player in players:
        count = 0
        for period in periods:
            if player.pro_team not in playing_by_period.get(period, set()):
                continue
            slot = daily_lineup_slots.get(period, {}).get(player.player_id)
            if player.player_id <= 0 or slot not in known_slots:
                counts.append(None)
                break
            if slot not in ("Bench", "IR") and slot_counts.get(slot, 0) > 0:
                count += 1
        else:
            counts.append(count)
    return counts


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
        column per period ('fit', 'play' or ''), Fit (days seated), Games
        (days with a game) and Candidate (position in ``candidates``);
        best fit first, then most games
    """
    base = open_seat_counts(keep_roster, slot_counts, playing_by_period,
                            periods)
    rows = []
    for position, cand in enumerate(candidates):
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
                     "Games": sum(v != "" for v in days.values()),
                     "Candidate": position})
    table = pd.DataFrame(rows, columns=["Player", "Team", "Injury", "Slots",
                                        *periods, "Fit", "Games",
                                        "Candidate"])
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
