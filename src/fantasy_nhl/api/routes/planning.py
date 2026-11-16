"""Roster planning: matchup preview, streaming planner, schedule outlook
and its calibration."""
from datetime import date
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from ...analysis import COMBINED_PLAYOFF_WEIGHT
from ...config import ScheduleCalibration, save_calibration
from ...sources.espn import (
    fetch_adds_used,
    fetch_calibration_data,
    fetch_daily_lineup_slots,
    fetch_free_agents,
    fetch_ir_roster,
    fetch_preview_data,
    fetch_rosters_and_slots,
    fetch_schedule_data,
)
from ...views.common import day_labels, stat_basis
from ...views.model import INFO, TableView, View, note
from ...views.preview import build_matchup_preview
from ...views.schedule import (
    build_calibration,
    build_schedule_outlook,
    lead_choices,
    lead_with,
    roster_fit,
    schedule_scores,
    select_schedule,
)
from ...views.streaming import (
    COVERAGE,
    build_candidates,
    build_streaming_plan,
    position_sorted,
    streaming_context,
)
from ..serialize import ViewModel, serialize_view
from ..state import LeagueSession
from .base import (
    LEAGUE,
    Entry,
    Session,
    Stats,
    in_range,
    invalid,
    local_write,
    team_row,
    total_weeks,
    warning,
)
from .base import view as _view
from .league import CalibrationInfo, calibration_info

router = APIRouter()
view = partial(_view, router)


def _preview(session: LeagueSession, week: int | None):
    data = session.data
    week = in_range(data.current_week if week is None else week, 1,
                    total_weeks(session), "week")
    return week, session.fetch(("preview", week),
                               lambda: fetch_preview_data(data, week))


@view("/preview")
def matchup_preview(session: Session, week: int | None = None,
                    stats: Stats = "blended") -> View:
    """Predicted category scores of a matchup (default: the current one)."""
    week, preview = _preview(session, week)
    return build_matchup_preview(
        session.data, preview, week,
        stat_basis(stats == "season", preview.blend_weight))


def _planner(session: LeagueSession, week: int | None, team: int,
             streamers: list[int], simulate: int | None):
    """The planner inputs of a team: (week, preview fetch, context, the
    streamers as players, label of the simulated day if any)."""
    data = session.data
    team_row(session, team)
    week, preview = _preview(session, week)
    adds_used = session.fetch(("adds", week),
                              lambda: fetch_adds_used(data, week))
    roster = position_sorted(preview.rosters[team])
    by_id = {player.player_id: player for player in roster}
    unknown = set(streamers) - set(by_id)
    if unknown:
        raise invalid(f"Not on the roster: {sorted(unknown)}")
    dropped = [by_id[player_id] for player_id in dict.fromkeys(streamers)]
    ir_roster = position_sorted(fetch_ir_roster(data, team))

    actionable = [p for p in preview.periods if p >= preview.current_period]
    simulated_from = None
    if simulate is not None:
        if actionable:
            raise invalid("simulate applies to a finished matchup only")
        if simulate not in preview.periods:
            raise invalid("simulate must be a scoring period of the week")
        actionable = [p for p in preview.periods if p >= simulate]
        simulated_from = day_labels(preview.periods,
                                    preview.period_dates)[simulate]
    daily_slots = {}
    if actionable:
        daily_slots = session.fetch(
            ("lineups", team, tuple(actionable)),
            lambda: fetch_daily_lineup_slots(data, team, actionable))
    context = streaming_context(preview, roster, ir_roster, adds_used[team],
                                actionable, daily_slots)
    return week, preview, context, dropped, simulated_from


class RosterChoice(BaseModel):
    id: int
    name: str


class DayInfo(BaseModel):
    period: int
    label: str


class PlanMeta(BaseModel):
    roster: list[RosterChoice] = []  # who can be marked as streamer
    days: list[DayInfo] = []  # the matchup's scoring periods
    finished: bool = False  # no day left: it can only be simulated
    has_open_days: bool = False  # there are days to list candidates for


@view("/streaming/plan", meta=PlanMeta)
def streaming_plan(session: Session, team: int, week: int | None = None,
                   streamers: Annotated[list[int], Query()] = [],
                   simulate: int | None = None) -> View:
    """
    A team's streaming planner for a matchup (default: the current one).

    :param team: team row
    :param streamers: ids of the roster players treated as dropped
    :param simulate: for a finished week, the scoring period to replay it
        from as if it were today
    """
    week, preview, context, dropped, simulated_from = _planner(
        session, week, team, streamers, simulate)
    plan = build_streaming_plan(context, week, session.data.team_names[team],
                                dropped, simulated_from)
    labels = day_labels(preview.periods, preview.period_dates)
    plan.meta.update(
        roster=[{"id": player.player_id, "name": player.name}
                for player in context.roster],
        days=[{"period": p, "label": labels[p]} for p in preview.periods],
        finished=not [p for p in preview.periods
                      if p >= preview.current_period],
        has_open_days=any(isinstance(block, TableView)
                          and block.key == COVERAGE for block in plan.blocks))
    return plan


@view("/streaming/candidates")
def streaming_candidates(session: Session, team: int,
                         week: int | None = None,
                         streamers: Annotated[list[int], Query()] = [],
                         simulate: int | None = None,
                         stats: Stats = "blended") -> View:
    """Free agents ranked by the open days of the plan they would fill
    (same parameters as the plan)."""
    data = session.data
    week, preview, context, dropped, simulated_from = _planner(
        session, week, team, streamers, simulate)
    free_agents = session.fetch(
        ("free_agents",), lambda: fetch_free_agents(data, preview.slot_counts))
    candidates = build_candidates(
        context, free_agents, data.config.categories,
        stat_basis(stats == "season", preview.blend_weight), dropped)
    if simulated_from:
        candidates.blocks.insert(0, note(
            "FA pool and stats are today's, not those of the simulated week.",
            level=INFO))
    return candidates


class OutlookMeta(BaseModel):
    sorts: list[str] = []  # score columns the table can lead with
    blends_playoffs: bool = False  # whether playoff_weight has an effect


@view("/schedule/outlook", meta=OutlookMeta)
def schedule_outlook(
        session: Session,
        scope: Literal["full", "remaining", "playoffs"] = "full",
        playoff_weight: Annotated[float, Query(ge=0, le=1)]
        = COMBINED_PLAYOFF_WEIGHT,
        fit_team: int | None = None, sort: str | None = None) -> View:
    """
    :param playoff_weight: weight of the playoff score in Combined
    :param fit_team: team row whose open seats weight the Fit score
        (remaining and playoffs scopes only)
    :param sort: score column to lead with, one of the view's meta.sorts
    """
    data = session.data
    if fit_team is not None:
        if scope == "full":
            raise invalid("fit_team applies to the remaining and playoffs "
                          "scopes only")
        team_row(session, fit_team, "fit_team")
    schedule = session.fetch(("schedule",), lambda: fetch_schedule_data(data))
    selection = select_schedule(data, schedule, scope)
    if selection is None:
        return warning("No matchups in the selected scope.")
    calibration = data.config.calibration
    fit = None
    if fit_team is not None:
        slot_counts, rosters = session.fetch(
            ("rosters",), lambda: fetch_rosters_and_slots(data))
        fit = roster_fit(schedule.playing_by_period, selection.score_periods,
                         rosters[fit_team], slot_counts)
    scores = schedule_scores(schedule, selection, calibration, playoff_weight,
                             fit)
    leads = lead_choices(selection, scores)
    if sort is not None and sort not in leads:
        raise invalid(f"sort must be one of {leads}")
    if leads:
        scores = lead_with(scores, sort or leads[0])
    outlook = build_schedule_outlook(data, schedule, selection, scores,
                                     calibration, playoff_weight,
                                     fitted=fit is not None)
    outlook.meta.update(sorts=leads,
                        blends_playoffs=selection.blends_playoffs)
    return outlook


class CalibrationRequest(BaseModel):
    source: str  # id of the league season to calibrate on


def _calibrate(session: LeagueSession, request: Request,
               body: CalibrationRequest) -> tuple[View, ScheduleCalibration]:
    source = request.app.state.store.leagues.get(body.source)
    if source is None:
        raise invalid("Unknown source league")
    calibration_data = session.fetch(
        ("calibration", source.id),
        lambda: fetch_calibration_data(source.config))
    table, curve = build_calibration(source.config.name, calibration_data)
    return table, ScheduleCalibration(source=source.config.name,
                                      calibrated=date.today().isoformat(),
                                      curve=curve)


@router.post(f"{LEAGUE}/schedule/calibration",
             dependencies=[Depends(local_write)])
def preview_calibration(session: Session, request: Request,
                        body: CalibrationRequest) -> ViewModel:
    """The night-value curve a source league season would calibrate."""
    table, _ = _calibrate(session, request, body)
    return serialize_view(table)


@router.put(f"{LEAGUE}/schedule/calibration",
            dependencies=[Depends(local_write)])
def store_calibration(entry: Entry, session: Session, request: Request,
                      body: CalibrationRequest) -> CalibrationInfo:
    """Calibrate the schedule scoring on a source league season and keep
    it for this league (calibration.yaml)."""
    _, calibration = _calibrate(session, request, body)
    save_calibration(entry.config.name, calibration)
    entry.config.calibration = calibration
    return calibration_info(entry.config)
