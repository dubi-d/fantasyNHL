"""Streaming planner: a team's week as a per-day roster grid with open
seats, the NHL teams covering them and the free agents who would fit."""
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import (
    GOALIE_CATEGORIES,
    RATIO_CATEGORIES,
    PreviewPlayer,
    RosterPlayer,
    StatBasis,
    StreamingContext,
    has_projection,
    has_season_games,
    lineup_game_counts,
    open_seat_counts,
    player_rate,
    position_open_seats,
    rank_streaming_candidates,
    team_gap_coverage,
)
from ..config import Category
from .common import (
    INJURY_ABBREV,
    NO_PROJECTION,
    SLOT_ABBREV,
    SLOT_ORDER,
    day_labels,
    no_season_stats_note,
    position_label,
    with_basis,
)
from .model import (
    ALERT,
    BENCH,
    DANGER,
    GOOD,
    INFO,
    MUTED,
    STRONG,
    WARN,
    WARNING,
    Span,
    TableView,
    Tone,
    View,
    note,
)

if TYPE_CHECKING:
    from ..sources.espn import PreviewData

ROSTER = "roster"
SLOTS = "slots"
COVERAGE = "coverage"
COVERAGE_TEAMS = 12  # NHL teams listed


def position_sorted(players: list) -> list:
    """Players ordered by their first lineup slot (centers first)."""
    return sorted(players, key=lambda p: min(
        (SLOT_ORDER.get(s, len(SLOT_ORDER)) for s in p.eligible_slots),
        default=len(SLOT_ORDER)))


def streaming_context(preview: "PreviewData", roster: list[PreviewPlayer],
                      ir_roster: list[RosterPlayer], adds_used: int | None,
                      actionable: list[int],
                      daily_lineup_slots: dict[int, dict[int, str]],
                      ) -> StreamingContext:
    """Planner inputs of one team from a week's preview fetch.

    :param actionable: the periods moves still affect (today and later)
    """
    return StreamingContext(
        roster=roster,
        slot_counts=preview.slot_counts,
        playing_by_period=preview.playing_by_period,
        periods=preview.periods,
        actionable_periods=actionable,
        period_dates=preview.period_dates,
        adds_used=adds_used,
        adds_limit=preview.add_limit,
        lookahead_periods=preview.next_periods[:2],
        daily_lineup_slots=daily_lineup_slots,
        ir_roster=ir_roster,
    )


def _injury_tone(value: object) -> Tone:
    return DANGER if value in ("OUT", "IR") else (WARN if value else None)


def _tones(frame: pd.DataFrame, columns: dict[str, list[Tone]]) -> pd.DataFrame:
    return pd.DataFrame(columns, index=frame.index, dtype=object)


def build_streaming_plan(ctx: StreamingContext, week: int, team_name: str,
                         streamers: list[PreviewPlayer],
                         simulated_from: str | None = None) -> View:
    """
    The planner of one team and week: legend, the ROSTER grid and, while
    days remain, the open seats per lineup SLOTS and the COVERAGE of the
    open days by NHL teams (missing when no seat is open).

    :param streamers: the roster players treated as dropped
    :param simulated_from: label of the day a finished week is replayed from
    """
    dropped = {id(player) for player in streamers}  # namesakes stay apart
    look = ctx.lookahead_periods
    labels = day_labels(ctx.periods + look, ctx.period_dates)
    elapsed = [p for p in ctx.periods if p not in set(ctx.actionable_periods)]
    muted = tuple(labels[d] for d in look)

    used = "?" if ctx.adds_used is None else ctx.adds_used
    limit = "\u221e" if ctx.adds_limit is None else ctx.adds_limit
    view = View([note(Span(f"Week {week} streaming planner", STRONG),
                      f" — {team_name}, adds used this week: ",
                      Span(f"{used} / {limit}", STRONG), space_before=True)])
    if simulated_from:
        view.blocks.append(note(
            f"SIMULATION — planning as if today were "
            f"{simulated_from}; using the current roster/IR group "
            "with saved assignments for those dates, not a "
            "reconstructed historical roster.", level=ALERT))
    elif not ctx.actionable_periods:
        view.blocks.append(note(
            "Week is over — the grid shows the current roster, not "
            "the historical lineups of that week.", level=WARNING))
    elif elapsed:
        view.blocks.append(note(
            "Dimmed days are elapsed and excluded from open seats "
            "and coverage; today counts as actionable.", level=INFO))
    if look and ctx.actionable_periods:
        view.blocks.append(note(
            f"Columns after {labels[max(ctx.periods)]} preview next "
            "week's first days — informational only, excluded from "
            "the coverage ranking.", level=INFO))
    view.blocks += [
        note("Games = remaining scheduled games in saved active ESPN slots "
             "(today included, no lookahead). ", Span("○", BENCH),
             " = saved Bench; ", Span("×", DANGER),
             " = IR; ? = lineup unavailable / incomplete total. "
             "Current IR rows are last, always Games 0. Inj = reported "
             "injury status.", level=INFO),
        note("Dots show NHL team schedules, not guaranteed player "
             "appearances or goalie starts. Open seats/coverage model "
             "capacity, not saved lineups; IR rows never fill seats.",
             level=INFO)]

    # Only the displayed rows include IR. All calculations keep ctx.roster.
    games = lineup_game_counts(ctx.roster, ctx.slot_counts,
                               ctx.playing_by_period, ctx.actionable_periods,
                               ctx.daily_lineup_slots)
    actionable = set(ctx.actionable_periods)
    dimmed = {labels[d] for d in elapsed + look}

    def marker(player: PreviewPlayer, day: int,
               ir: bool) -> tuple[str, str | None]:
        """A day's cell and tone: a mark where the player's team plays
        (the symbol tells Bench and IR apart without the colour)."""
        if player.pro_team not in ctx.playing_by_period.get(day, set()):
            return "", None
        if ir:
            return "×", DANGER
        if day not in actionable:
            return "•", None
        slot = ctx.daily_lineup_slots.get(day, {}).get(player.player_id)
        if player.player_id <= 0:
            return "?", None
        if slot == "Bench":
            return "○", BENCH
        if slot == "IR":
            return "×", DANGER
        return ("•" if slot in ctx.slot_counts else "?"), None

    rows = []
    row_tones = []
    for ir, players, counts in ((False, ctx.roster, games),
                                (True, ctx.ir_roster, [0] * len(ctx.ir_roster))):
        for player, count in zip(players, counts):
            days = {labels[d]: marker(player, d, ir)
                    for d in ctx.periods + look}
            inj = INJURY_ABBREV.get(player.injury, player.injury[:3])
            rows.append({
                "Player": player.name + (" (IR)" if ir else
                          " *" if id(player) in dropped else ""),
                "Pos": position_label(player.eligible_slots)
                       or getattr(player, "position", ""),
                "Team": player.pro_team,
                "Games": "?" if count is None else str(count),
                "Inj": inj,
                **{label: text for label, (text, _) in days.items()},
            })
            row_tones.append({
                "Inj": _injury_tone(inj),
                **{label: " ".join(filter(None, (
                    MUTED if label in dimmed else None, tone))) or None
                   for label, (_, tone) in days.items()}})
    grid = pd.DataFrame(rows, index=[""] * len(rows),
                        columns=["Player", "Pos", "Team", "Games", "Inj",
                                 *labels.values()])
    grid_tones = pd.DataFrame(row_tones, index=grid.index,
                              columns=["Inj", *labels.values()], dtype=object)

    keep = [p for p in ctx.roster if id(p) not in dropped]
    seat_periods = ctx.actionable_periods + look
    open_current = open_seat_counts(ctx.roster, ctx.slot_counts,
                                    ctx.playing_by_period, seat_periods)
    open_dropped = open_seat_counts(keep, ctx.slot_counts,
                                    ctx.playing_by_period, seat_periods)

    def open_row(name: str, opened: dict[int, tuple[int, int]],
                 part: int) -> dict[str, str]:
        return {"Player": name,
                **{labels[d]: str(seats[part]) if seats[part] else "-"
                   for d, seats in opened.items()}}

    footer = None
    if ctx.actionable_periods:
        footer_rows = [open_row("(open skater seats)", open_current, 0),
                       open_row("(open goalie seats)", open_current, 1)]
        if streamers:
            footer_rows += [open_row("(skater, streamers out)", open_dropped, 0),
                            open_row("(goalie, streamers out)", open_dropped, 1)]
        footer = pd.DataFrame(footer_rows, index=[""] * len(footer_rows))
    view.blocks.append(TableView(
        f"Roster week {week}" + (" (* = streamer)" if streamers else ""),
        grid, grid_tones, footer=footer, muted=muted, key=ROSTER))
    if not ctx.actionable_periods:
        return view

    # disjoint per-slot open seats; specific seats are filled before F/Util
    open_slots = position_open_seats(keep, ctx.slot_counts,
                                     ctx.playing_by_period, seat_periods)
    pos_table = pd.DataFrame([{
        "Pos": SLOT_ABBREV.get(slot, slot),
        **{labels[d]: str(open_slots[d][slot]) if open_slots[d][slot] else "-"
           for d in seat_periods},
    } for slot in ctx.slot_counts], index=[""] * len(ctx.slot_counts))
    totals = pd.DataFrame([{
        "Pos": "(total)",
        **{labels[d]: str(sum(open_slots[d].values()))
           if any(open_slots[d].values()) else "-"
           for d in seat_periods},
    }], index=[""])
    dropped = " — streamers dropped" if streamers else ""
    view.blocks.append(TableView(
        "Open seats by lineup slot" + dropped, pos_table,
        _tones(pos_table, {label: [MUTED] * len(pos_table) for label in muted}),
        footer=totals, muted=muted, key=SLOTS))

    # coverage counts games on days that still have any open seat
    open_periods = {d for d in ctx.actionable_periods
                    if sum(open_dropped[d]) > 0}
    if not open_periods:
        view.blocks.append(note(
            "No open seats on the remaining days — mark streamers "
            "to see which teams could cover their spots.", level=WARNING))
        return view
    coverage = team_gap_coverage(ctx.playing_by_period, open_periods,
                                 ctx.actionable_periods)
    coverage = coverage[coverage["Cover"] > 0].head(COVERAGE_TEAMS)
    cov_table = pd.DataFrame({
        "Team": coverage["Team"],
        **{labels[d]: coverage[d].map({True: "•", False: ""})
           for d in ctx.actionable_periods},
        **{labels[d]: coverage["Team"].map(
            lambda t, d=d: "•" if t in ctx.playing_by_period.get(d, set())
            else "") for d in look},
        "Cover": coverage["Cover"],
        "Games": coverage["Games"],
    })
    cov_table.index = range(1, len(cov_table) + 1)
    cov_tones = {labels[d]: [GOOD if v == "•" else None
                             for v in cov_table[labels[d]]]
                 for d in open_periods}
    cov_tones.update({label: [MUTED] * len(cov_table) for label in muted})
    open_labels = ", ".join(labels[d] for d in sorted(open_periods))
    view.blocks.append(TableView(
        f"NHL teams covering the open days ({open_labels})" + dropped,
        cov_table, _tones(cov_table, cov_tones), muted=muted, key=COVERAGE))
    return view


def candidates_title(first: int, last: int, total: int,
                     streamers: list[PreviewPlayer], basis: StatBasis) -> str:
    """Title of the candidates ranked ``first``..``last`` of ``total``."""
    return with_basis(
        f"Free agent candidates {first}–{last} of {total} by open days "
        "filled (• = fills an open seat, · = plays)"
        + (" — streamers dropped" if streamers else ""), basis)


def build_candidates(ctx: StreamingContext, candidates: list[PreviewPlayer],
                     categories: list[Category], basis: StatBasis,
                     streamers: list[PreviewPlayer]) -> View:
    """Free agents ranked by the open days they would fill a lineup seat
    on, with per-game rates (on the given stat basis) for the skater
    categories; one table of all candidates, best fit first.

    :param streamers: the roster players treated as dropped
    """
    look = ctx.lookahead_periods
    labels = day_labels(ctx.periods + look, ctx.period_dates)
    dropped = {id(player) for player in streamers}
    keep = [p for p in ctx.roster if id(p) not in dropped]
    ranked = rank_streaming_candidates(candidates, keep, ctx.slot_counts,
                                       ctx.playing_by_period,
                                       ctx.actionable_periods)
    ranked = ranked[ranked["Fit"] > 0]
    if ranked.empty:
        return View([note("No free agent fills an open seat on the remaining "
                          "days.", level=WARNING)])
    view = View()
    warning = no_season_stats_note(basis, candidates)
    if warning:
        view.blocks.append(warning)

    marker = {"fit": "•", "play": "·", "": ""}
    # candidates are skaters only, so goalie categories carry no signal
    rate_cats = [c for c in categories
                 if c.name not in RATIO_CATEGORIES
                 and c.name not in GOALIE_CATEGORIES]
    rows = []
    for _, r in ranked.iterrows():
        cand = candidates[r["Candidate"]]
        rates = {cat.name: player_rate(cand, cat.name, basis)
                 for cat in rate_cats}
        unprojected = (not basis.season_only and has_season_games(cand)
                       and not has_projection(cand))
        rows.append({
            "Player": (f"{r['Player']} {NO_PROJECTION}" if unprojected
                       else r["Player"]),
            "Pos": position_label(r["Slots"]),
            "Team": r["Team"],
            **{labels[d]: marker[r[d]] for d in ctx.actionable_periods},
            **{labels[d]: "·" if r["Team"] in ctx.playing_by_period.get(d, set())
               else "" for d in look},
            "Fit": r["Fit"],
            "Games": r["Games"],
            **{name: None if v is None else round(v, 2)
               for name, v in rates.items()},
            "Inj": INJURY_ABBREV.get(r["Injury"], r["Injury"][:3]),
        })
    table = pd.DataFrame(rows, index=range(1, len(rows) + 1))
    muted = tuple(labels[d] for d in look)
    tones = {labels[d]: [GOOD if v == "•" else None for v in table[labels[d]]]
             for d in ctx.actionable_periods}
    tones.update({label: [MUTED] * len(table) for label in muted})
    tones["Inj"] = [_injury_tone(v) for v in table["Inj"]]
    view.blocks.append(TableView(
        candidates_title(1, len(table), len(table), streamers, basis),
        table, _tones(table, tones), muted=muted))
    return view
