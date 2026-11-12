"""Matchup preview: predicted category scores per head-to-head pairing."""
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import (
    RATIO_CATEGORIES,
    StatBasis,
    has_projection,
    matchup_result,
    preview_week,
)
from .common import RESULT_TONES, basis_label, no_season_stats_note
from .model import (
    BAD,
    EVEN,
    GOOD,
    INFO,
    STRONG,
    WARNING,
    Span,
    TableView,
    View,
    column_tones,
    note,
)

if TYPE_CHECKING:
    from ..espn_data import LeagueData, PreviewData


def _pair_tones(home_raw: float, away_raw: float, inverted: bool,
                home_display: float, away_display: float) -> list[str]:
    """Tones of the two displayed scores of a category: the better one,
    judged on the raw (unrounded) values, is good."""
    if home_raw == away_raw or home_display == away_display:
        return [EVEN, EVEN]
    home_wins = home_raw < away_raw if inverted else home_raw > away_raw
    winner = home_display if home_wins else away_display
    return [GOOD if value == winner else BAD
            for value in (home_display, away_display)]


def build_matchup_preview(data: "LeagueData", preview: "PreviewData",
                          week: int, basis: StatBasis) -> View:
    """Player games and predicted category scores of every pairing of a
    matchup week. Elapsed days use real data (scores and games actually
    played), remaining days per-game-rate predictions on ``basis`` with the
    current roster filling all active slots."""
    if not preview.pairings:
        return View([note("No matchups scheduled for this week yet (playoff "
                          "pairings appear once the bracket is seeded).",
                          level=WARNING)])

    days_real = len(preview.periods) - len(preview.remaining_periods)
    if not preview.remaining_periods:
        status = "completed, real data"
    elif days_real == 0:
        status = "not started, predictions only"
    else:
        status = (f"{days_real} days real (live), "
                  f"{len(preview.remaining_periods)} days predicted")
    dates = ""
    if preview.start_date and preview.end_date:
        dates = (f", {preview.start_date:%a %b %-d} \u2013 "
                 f"{preview.end_date:%a %b %-d}")
    view = View([note(
        Span(f"Week {week} preview", STRONG),
        f" — {len(preview.periods)} days{dates}, {status}. Games = games "
        f"already played (incl. today's started games) plus playable games "
        f"of the current roster for the rest of the week.",
        space_before=True)])

    if preview.remaining_periods:
        rostered = [p for roster in preview.rosters for p in roster]
        text = ("Remaining days are predicted from per-game rates — stats: "
                f"{basis_label(basis)}")
        unprojected = sum(not has_projection(p) for p in rostered)
        if basis.season_only:
            text += "; players without games this season predict 0"
        elif unprojected:
            text += ("; rostered players without an ESPN projection "
                     f"({unprojected}) are predicted from season stats alone")
        view.blocks.append(note(f"{text}.", level=INFO))
        warning = no_season_stats_note(basis, rostered)
        if warning:
            view.blocks.append(warning)

    playing = dict(preview.playing_by_period)
    today = preview.current_period
    playing[today] = playing.get(today, set()) - preview.started_today

    categories = data.config.categories
    games = {}
    scores = {}  # raw values for results, so display rounding can't fake ties
    display = {}
    for row in range(len(data.team_names)):
        games[row], scores[row] = preview_week(
            preview.rosters[row], preview.slot_counts, playing,
            preview.remaining_periods, preview.actual_scores[row],
            categories, basis,
            preview.actual_games[row], preview.actual_goalie_games[row])
        display[row] = [
            round(float(value), 2 if cat.name in RATIO_CATEGORIES else 1)
            for value, cat in zip(scores[row], categories)]

    for home_row, away_row in preview.pairings:
        rows = []
        for row, opponent in ((home_row, away_row), (away_row, home_row)):
            won, lost, _tied, cats_won = matchup_result(
                scores[row], scores[opponent], categories)
            rows.append({"Player": data.team_names[row], "Games": games[row],
                         **{cat.name: display[row][i]
                            for i, cat in enumerate(categories)},
                         "Cats": int(cats_won),
                         "Proj": "W" if won else ("L" if lost else "T")})
        frame = pd.DataFrame(rows, index=["", ""])
        tones = column_tones(frame, {"Proj": RESULT_TONES.get})
        for i, cat in enumerate(categories):
            tones[cat.name] = _pair_tones(scores[home_row][i],
                                          scores[away_row][i], cat.inverted,
                                          display[home_row][i],
                                          display[away_row][i])
        view.blocks.append(TableView(
            f"{data.team_names[home_row]} vs {data.team_names[away_row]}",
            frame, tones))
    return view
