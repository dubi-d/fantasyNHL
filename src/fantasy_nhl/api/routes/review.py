"""Players, rosters and the draft: the views of the roster review."""
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ...analysis import ACQUIRED_ADD, ACQUIRED_TRADE
from ...sources.espn import fetch_roster_review
from ...views.common import no_season_stats_note, stat_basis
from ...views.draft import (
    build_draft_grades,
    build_draft_return,
    build_team_draft,
    not_drafted,
)
from ...views.model import View
from ...views.players import (
    COMPARE_MAX,
    GROUP_CHOICES,
    build_compare,
    build_leaders,
    cell_choices,
    leader_sorts,
    player_labels,
)
from ...views.review import (
    NOBODY,
    ReviewContext,
    build_review_context,
    has_players,
)
from ...views.rosters import (
    build_acquired,
    build_gaps,
    build_origins,
    build_outlook,
    build_team_roster,
)
from ..state import LeagueSession
from .base import LEAGUE, Session, Stats, invalid, team_row, warning
from .base import view as _view

router = APIRouter()
view = partial(_view, router)


def _review_context(session: LeagueSession,
                    stats: Stats) -> ReviewContext | None:
    """The valued player pool, None while there is nobody to value."""
    data = session.data
    review = session.fetch(("review",), lambda: fetch_roster_review(data))
    if not has_players(review):
        return None
    return session.derived(
        ("review_context", stats), review,
        lambda: build_review_context(data, review, stat_basis(
            stats == "season", review.blend_weight)))


def _review(session: LeagueSession, stats: Stats, build, *args,
            needs_draft: bool = False) -> View:
    context = _review_context(session, stats)
    if context is None:
        return warning(NOBODY)
    if needs_draft and not context.drafted:
        return not_drafted()
    built = build(context, *args)
    review = context.review
    no_stats = no_season_stats_note(
        context.basis,
        [p for roster in review.rosters for p in roster] + review.free_agents)
    if no_stats:
        built.blocks.insert(0, no_stats)
    return built


class PlayerChoice(BaseModel):
    id: int
    label: str
    goalie: bool


class GroupChoice(BaseModel):
    key: str
    label: str
    sorts: list[str]


class Choice(BaseModel):
    key: str
    label: str


class ReviewOptions(BaseModel):
    drafted: bool
    players: list[PlayerChoice]  # for comparisons, by name
    groups: list[GroupChoice]  # leaderboard position groups
    cells: list[Choice]  # what leaderboard cells can show


@router.get(f"{LEAGUE}/review/options")
def review_options(session: Session,
                   stats: Stats = "blended") -> ReviewOptions:
    """What the player, roster and draft views can be asked for."""
    context = _review_context(session, stats)
    if context is None:
        return ReviewOptions(drafted=False, players=[], groups=[], cells=[])
    return ReviewOptions(
        drafted=context.drafted,
        players=[PlayerChoice(id=pid, label=label,
                              goalie=context.profile.at[pid, "Group"] == "G")
                 for label, pid in player_labels(context).items()],
        groups=[GroupChoice(key=key, label=label,
                            sorts=leader_sorts(context, key))
                for key, label in GROUP_CHOICES.items()],
        cells=[Choice(key=key, label=label)
               for key, label in cell_choices(context.basis).items()])


@view("/review/leaders")
def review_leaders(session: Session,
                   scope: Literal["all", "fa", "team"] = "all",
                   team: int | None = None,
                   group: Literal["F", "D", "FD", "G"] = "F",
                   sort: str = "Score",
                   cells: Literal["pct", "rate", "total"] = "pct",
                   stats: Stats = "blended") -> View:
    """
    Category leaderboard.

    :param scope: whole pool, free agents or one team (then give ``team``)
    :param sort: Score, Spec, Elite or a category (see review/options)
    :param cells: percentiles, per-game rates or (season stats only) totals
    """
    if scope == "team":
        if team is None:
            raise invalid("team is required for scope=team")
        team_row(session, team)

    def build(context: ReviewContext) -> View:
        if sort not in leader_sorts(context, group):
            raise invalid(f"sort must be one of {leader_sorts(context, group)}")
        if cells not in cell_choices(context.basis):
            raise invalid("Season totals need stats=season")
        return build_leaders(context, scope, team if scope == "team" else None,
                             group, sort, cells)
    return _review(session, stats, build)


@view("/review/compare")
def review_compare(session: Session,
                   players: Annotated[list[int], Query()],
                   stats: Stats = "blended") -> View:
    """
    :param players: ids of 2-4 skaters or 2-4 goalies (see review/options)
    """
    def build(context: ReviewContext) -> View:
        ids = tuple(dict.fromkeys(players))
        if not 2 <= len(ids) <= COMPARE_MAX:
            raise invalid(f"Pick 2 to {COMPARE_MAX} different players")
        if not set(ids) <= set(context.pool):
            raise invalid("Unknown player")
        if len({context.profile.at[pid, "Group"] == "G" for pid in ids}) > 1:
            raise invalid("Can't mix skaters and goalies")
        return build_compare(context, ids)
    return _review(session, stats, build)


@view("/review/origins")
def review_origins(session: Session, stats: Stats = "blended") -> View:
    return _review(session, stats, build_origins)


@view("/review/outlook")
def review_outlook(session: Session,
                   source: Literal["draft", "current"] = "current",
                   stats: Stats = "blended") -> View:
    """
    :param source: rosters as drafted or as they are now
    """
    return _review(session, stats, build_outlook, source,
                   needs_draft=source == "draft")


@view("/review/draft-grades")
def review_draft_grades(session: Session, stats: Stats = "blended") -> View:
    return _review(session, stats, build_draft_grades, needs_draft=True)


@view("/review/draft-return")
def review_draft_return(session: Session, stats: Stats = "blended") -> View:
    return _review(session, stats, build_draft_return, needs_draft=True)


@view("/review/pickups")
def review_pickups(session: Session, stats: Stats = "blended") -> View:
    return _review(session, stats, build_acquired, ACQUIRED_ADD,
                   "Waiver pickups")


@view("/review/trades")
def review_trades(session: Session, stats: Stats = "blended") -> View:
    return _review(session, stats, build_acquired, ACQUIRED_TRADE,
                   "Traded-in players")


@view("/review/team")
def review_team(session: Session, team: int,
                source: Literal["draft", "current"] = "current",
                stats: Stats = "blended") -> View:
    """A team's roster: its draft picks or its current players."""
    team_row(session, team)
    return _review(session, stats,
                   build_team_draft if source == "draft" else build_team_roster,
                   team, needs_draft=source == "draft")


@view("/review/gaps")
def review_gaps(session: Session, team: int,
                stats: Stats = "blended") -> View:
    """A team's drop candidates next to the best free agents."""
    team_row(session, team)
    return _review(session, stats, build_gaps, team)
