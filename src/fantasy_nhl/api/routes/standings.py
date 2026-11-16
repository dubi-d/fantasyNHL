"""Weekly scores and season standings."""
from functools import partial

from fastapi import APIRouter

from ...sources.espn import fetch_week_pairings
from ...views.common import completed_matchups
from ...views.model import View
from ...views.standings import (
    build_accumulated_scores,
    build_category_profile,
    build_luck_ranking,
    build_power_rankings,
)
from ...views.weekly import build_weekly_awards, build_weekly_scores
from .base import Session, in_range, warning, week_dates
from .base import view as _view

router = APIRouter()
view = partial(_view, router)


@view("/weekly/scores")
def weekly_scores(session: Session) -> View:
    return build_weekly_scores(session.data)


@view("/weekly/awards")
def weekly_awards(session: Session, week: int | None = None) -> View:
    """Awards of a completed matchup (default: the latest)."""
    data = session.data
    completed = completed_matchups(data)
    if completed == 0:
        return warning("No completed matchups yet.")
    week = in_range(completed if week is None else week, 1, completed, "week")
    week_dates(session)  # the awards text carries the matchup's dates
    pairings = session.fetch(("pairings", week),
                             lambda: fetch_week_pairings(data, week))
    return build_weekly_awards(data, week, pairings)


@view("/standings/accumulated")
def accumulated_scores(session: Session) -> View:
    return build_accumulated_scores(session.data)


@view("/standings/luck")
def luck_ranking(session: Session) -> View:
    return build_luck_ranking(session.data)


@view("/standings/power-rankings")
def power_rankings(session: Session, window: int | None = None) -> View:
    """
    :param window: hot-streak window in matchups (default: up to 4)
    """
    data = session.data
    completed = completed_matchups(data)
    if completed < 2:
        return warning("Need at least 2 completed matchups.")
    window = in_range(min(4, completed) if window is None else window,
                      2, completed, "window")
    return build_power_rankings(data, completed, window)


@view("/standings/category-profile")
def category_profile(session: Session) -> View:
    return build_category_profile(session.data)
