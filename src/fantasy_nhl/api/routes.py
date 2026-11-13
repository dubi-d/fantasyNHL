"""The HTTP API: every view of the CLI tools as JSON, their prompts as
query parameters. A view with a figure also serves it at <view>/figure.png."""
import threading
from datetime import date
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from ..analysis import ACQUIRED_ADD, ACQUIRED_TRADE, COMBINED_PLAYOFF_WEIGHT
from ..config import ScheduleCalibration, save_calibration
from ..sources.espn import (
    fetch_adds_used,
    fetch_calibration_data,
    fetch_daily_lineup_slots,
    fetch_free_agents,
    fetch_ir_roster,
    fetch_preview_data,
    fetch_roster_review,
    fetch_rosters_and_slots,
    fetch_schedule_data,
    fetch_week_dates,
    fetch_week_pairings,
)
from ..views.common import (
    completed_matchups,
    day_labels,
    no_season_stats_note,
    stat_basis,
    week_label,
)
from ..views.draft import (
    build_draft_grades,
    build_draft_return,
    build_team_draft,
    not_drafted,
)
from ..views.model import INFO, WARNING, FigureBlock, TableView, View, note
from ..views.players import (
    COMPARE_MAX,
    GROUP_CHOICES,
    build_compare,
    build_leaders,
    cell_choices,
    leader_sorts,
    player_labels,
)
from ..views.preview import build_matchup_preview
from ..views.review import ReviewContext, build_review_context
from ..views.rosters import (
    build_acquired,
    build_gaps,
    build_origins,
    build_outlook,
    build_team_roster,
)
from ..views.schedule import (
    build_calibration,
    build_schedule_outlook,
    lead_choices,
    lead_with,
    roster_fit,
    schedule_scores,
    select_schedule,
)
from ..views.standings import (
    build_accumulated_scores,
    build_category_profile,
    build_luck_ranking,
    build_power_rankings,
)
from ..views.streaming import (
    COVERAGE,
    build_candidates,
    build_streaming_plan,
    position_sorted,
    streaming_context,
)
from ..views.weekly import build_weekly_awards, build_weekly_scores
from .serialize import ViewModel, serialize_view
from .state import LeagueSession

router = APIRouter(prefix="/api")
LEAGUE = "/leagues/{league}"
LOCAL_HOSTS = ("127.0.0.1", "localhost")

Stats = Literal["blended", "season"]
_figure_lock = threading.Lock()  # pyplot keeps global state


def get_session(league: str, request: Request) -> LeagueSession:
    session = request.app.state.store.sessions.get(league)
    if session is None:
        raise HTTPException(404, "Unknown league")
    return session


Session = Annotated[LeagueSession, Depends(get_session)]


def local_write(request: Request) -> None:
    """Guard for state-changing requests: JSON only (a page of another
    site cannot send that without permission) and no foreign Origin."""
    content_type = request.headers.get("content-type", "")
    if content_type.split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send application/json")
    origin = request.headers.get("origin")
    if origin and origin.split("://")[-1].split(":")[0] not in LOCAL_HOSTS:
        raise HTTPException(403, "Foreign origin")


def _invalid(message: str) -> HTTPException:
    return HTTPException(422, message)


def _in_range(value: int, low: int, high: int, name: str) -> int:
    if not low <= value <= high:
        raise _invalid(f"{name} must be between {low} and {high}")
    return value


def _warning(text: str) -> View:
    return View([note(text, level=WARNING)])


def view(path: str):
    """Register a function building a View from path and query parameters
    as a JSON endpoint, plus the PNG endpoint of its figure."""
    def register(build):
        def as_json(request: Request,
                    built: View = Depends(build)) -> ViewModel:
            query = f"?{request.url.query}" if request.url.query else ""
            return serialize_view(
                built, f"{request.url.path}/figure.png{query}")

        def as_png(built: View = Depends(build)) -> Response:
            figure = next((block for block in built.blocks
                           if isinstance(block, FigureBlock)), None)
            if figure is None:
                raise HTTPException(404, "This view has no figure")
            from .. import plots  # deferred: matplotlib import is slow
            png = BytesIO()
            with _figure_lock:
                plots.save_figure(
                    getattr(plots, f"{figure.kind}_figure")(**figure.inputs),
                    png)
            return Response(png.getvalue(), media_type="image/png")

        router.add_api_route(LEAGUE + path, as_json, name=build.__name__,
                             response_model=ViewModel)
        router.add_api_route(f"{LEAGUE}{path}/figure.png", as_png,
                             include_in_schema=False)
        return build
    return register


class LeagueInfo(BaseModel):
    id: str
    name: str
    year: int


class WeekInfo(BaseModel):
    week: int
    label: str
    completed: bool


class CategoryInfo(BaseModel):
    name: str
    inverted: bool


class CalibrationInfo(BaseModel):
    source: str
    calibrated: str


class LeagueMeta(LeagueInfo):
    teams: list[str]  # by team row, the index other endpoints take
    current_week: int
    completed_matchups: int
    weeks: list[WeekInfo]
    categories: list[CategoryInfo]
    calibration: CalibrationInfo | None


def _league_info(session: LeagueSession) -> LeagueInfo:
    return LeagueInfo(id=session.id, name=session.config.name,
                      year=session.config.year)


def _calibration_info(session: LeagueSession) -> CalibrationInfo | None:
    calibration = session.config.calibration
    return calibration and CalibrationInfo(source=calibration.source,
                                           calibrated=calibration.calibrated)


def _week_dates(session: LeagueSession) -> dict:
    data = session.data
    return session.fetch(("week_dates",), lambda: fetch_week_dates(data))


def _total_weeks(session: LeagueSession) -> int:
    return session.data.total_weeks or session.data.current_week


@router.get("/leagues")
def leagues(request: Request) -> list[LeagueInfo]:
    return [_league_info(session)
            for session in request.app.state.store.sessions.values()]


@router.get(LEAGUE)
def league_meta(session: Session) -> LeagueMeta:
    data = session.data
    week_dates = _week_dates(session)
    completed = completed_matchups(data)
    return LeagueMeta(
        **_league_info(session).model_dump(), teams=data.team_names,
        current_week=data.current_week, completed_matchups=completed,
        weeks=[WeekInfo(week=week, label=week_label(data, week, week_dates),
                        completed=week <= completed)
               for week in range(1, _total_weeks(session) + 1)],
        categories=[CategoryInfo(name=cat.name, inverted=cat.inverted)
                    for cat in data.config.categories],
        calibration=_calibration_info(session))


@router.post(f"{LEAGUE}/reload", dependencies=[Depends(local_write)])
def reload(session: Session) -> LeagueInfo:
    """Drop everything fetched for the league (after roster moves etc.)."""
    session.reload()
    return _league_info(session)


@view("/weekly/scores")
def weekly_scores(session: Session) -> View:
    return build_weekly_scores(session.data)


@view("/weekly/awards")
def weekly_awards(session: Session, week: int | None = None) -> View:
    """Awards of a completed matchup (default: the latest)."""
    data = session.data
    completed = completed_matchups(data)
    if completed == 0:
        return _warning("No completed matchups yet.")
    week = _in_range(week or completed, 1, completed, "week")
    _week_dates(session)  # the awards text carries the matchup's dates
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
        return _warning("Need at least 2 completed matchups.")
    window = _in_range(window or min(4, completed), 2, completed, "window")
    return build_power_rankings(data, completed, window)


@view("/standings/category-profile")
def category_profile(session: Session) -> View:
    return build_category_profile(session.data)


def _preview(session: LeagueSession, week: int | None):
    data = session.data
    week = _in_range(week or data.current_week, 1, _total_weeks(session),
                     "week")
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
             streamers: list[str], simulate: int | None):
    """The planner inputs of a team: (week, preview fetch, context, label
    of the simulated day if any)."""
    data = session.data
    _in_range(team, 0, len(data.team_names) - 1, "team")
    week, preview = _preview(session, week)
    adds_used = session.fetch(("adds", week),
                              lambda: fetch_adds_used(data, week))
    roster = position_sorted(preview.rosters[team])
    unknown = set(streamers) - {player.name for player in roster}
    if unknown:
        raise _invalid(f"Not on the roster: {sorted(unknown)}")
    ir_roster = position_sorted(fetch_ir_roster(data, team))

    actionable = [p for p in preview.periods if p >= preview.current_period]
    simulated_from = None
    if not actionable and simulate is not None:
        if simulate not in preview.periods:
            raise _invalid("simulate must be a scoring period of the week")
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
    return week, preview, context, simulated_from


@view("/streaming/plan")
def streaming_plan(session: Session, team: int, week: int | None = None,
                   streamers: Annotated[list[str], Query()] = [],
                   simulate: int | None = None) -> View:
    """
    A team's streaming planner for a matchup (default: the current one).

    :param team: team row
    :param streamers: roster players treated as dropped
    :param simulate: for a finished week, the scoring period to replay it
        from as if it were today
    """
    week, preview, context, simulated_from = _planner(
        session, week, team, streamers, simulate)
    plan = build_streaming_plan(context, week, session.data.team_names[team],
                                streamers, simulated_from)
    labels = day_labels(preview.periods, preview.period_dates)
    plan.meta.update(
        roster=[player.name for player in context.roster],
        days=[{"period": p, "label": labels[p]} for p in preview.periods],
        finished=not [p for p in preview.periods
                      if p >= preview.current_period],
        has_open_days=any(isinstance(block, TableView)
                          and block.key == COVERAGE for block in plan.blocks))
    return plan


@view("/streaming/candidates")
def streaming_candidates(session: Session, team: int,
                         week: int | None = None,
                         streamers: Annotated[list[str], Query()] = [],
                         simulate: int | None = None,
                         stats: Stats = "blended") -> View:
    """Free agents ranked by the open days of the plan they would fill
    (same parameters as the plan)."""
    data = session.data
    week, preview, context, simulated_from = _planner(
        session, week, team, streamers, simulate)
    free_agents = session.fetch(
        ("free_agents",), lambda: fetch_free_agents(data, preview.slot_counts))
    candidates = build_candidates(
        context, free_agents, data.config.categories,
        stat_basis(stats == "season", preview.blend_weight), streamers)
    if simulated_from:
        candidates.blocks.insert(0, note(
            "FA pool and stats are today's, not those of the simulated week.",
            level=INFO))
    return candidates


@view("/schedule/outlook")
def schedule_outlook(
        session: Session,
        scope: Literal["full", "remaining", "playoffs"] = "full",
        playoff_weight: Annotated[float, Query(ge=0, le=1)]
        = COMBINED_PLAYOFF_WEIGHT,
        fit_team: int | None = None, sort: str | None = None) -> View:
    """
    :param playoff_weight: weight of the playoff score in Combined
    :param fit_team: team row whose open seats weight the Fit score
        (remaining and playoffs scopes)
    :param sort: score column to lead with, one of the view's meta.sorts
    """
    data = session.data
    schedule = session.fetch(("schedule",), lambda: fetch_schedule_data(data))
    selection = select_schedule(data, schedule, scope)
    if selection is None:
        return _warning("No matchups in the selected scope.")
    calibration = data.config.calibration
    fit = None
    if fit_team is not None and scope != "full":
        _in_range(fit_team, 0, len(data.team_names) - 1, "fit_team")
        slot_counts, rosters = session.fetch(
            ("rosters",), lambda: fetch_rosters_and_slots(data))
        fit = roster_fit(schedule.playing_by_period, selection.score_periods,
                         rosters[fit_team], slot_counts)
    scores = schedule_scores(schedule, selection, calibration, playoff_weight,
                             fit)
    leads = lead_choices(selection, scores)
    if sort is not None and sort not in leads:
        raise _invalid(f"sort must be one of {leads}")
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
    source = request.app.state.store.sessions.get(body.source)
    if source is None:
        raise _invalid("Unknown source league")
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
    return serialize_view(table, "")


@router.put(f"{LEAGUE}/schedule/calibration",
            dependencies=[Depends(local_write)])
def store_calibration(session: Session, request: Request,
                      body: CalibrationRequest) -> CalibrationInfo:
    """Calibrate the schedule scoring on a source league season and keep
    it for this league (calibration.yaml)."""
    _, calibration = _calibrate(session, request, body)
    save_calibration(session.config.name, calibration)
    session.config.calibration = calibration
    return _calibration_info(session)


def _review_context(session: LeagueSession,
                    stats: Stats) -> ReviewContext | None:
    """The valued player pool, None while there is nobody to value."""
    data = session.data
    review = session.fetch(("review",), lambda: fetch_roster_review(data))
    if not any(review.rosters) and not review.picks:
        return None
    return session.cached(
        ("review_context", stats),
        lambda: build_review_context(data, review, stat_basis(
            stats == "season", review.blend_weight)))


def _review(session: LeagueSession, stats: Stats, build, *args,
            needs_draft: bool = False) -> View:
    context = _review_context(session, stats)
    if context is None:
        return _warning("Rosters are empty and the league has not drafted "
                        "yet.")
    if needs_draft and not context.drafted:
        return not_drafted()
    built = build(context, *args)
    review = context.review
    warning = no_season_stats_note(
        context.basis,
        [p for roster in review.rosters for p in roster] + review.free_agents)
    if warning:
        built.blocks.insert(0, warning)
    return built


def _team(session: LeagueSession, team: int) -> int:
    return _in_range(team, 0, len(session.data.team_names) - 1, "team")


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
            raise _invalid("team is required for scope=team")
        _team(session, team)

    def build(context: ReviewContext) -> View:
        if sort not in leader_sorts(context, group):
            raise _invalid(f"sort must be one of {leader_sorts(context, group)}")
        if cells not in cell_choices(context.basis):
            raise _invalid("Season totals need stats=season")
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
            raise _invalid(f"Pick 2 to {COMPARE_MAX} different players")
        if not set(ids) <= set(context.pool):
            raise _invalid("Unknown player")
        if len({context.profile.at[pid, "Group"] == "G" for pid in ids}) > 1:
            raise _invalid("Can't mix skaters and goalies")
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
    _team(session, team)
    return _review(session, stats,
                   build_team_draft if source == "draft" else build_team_roster,
                   team, needs_draft=source == "draft")


@view("/review/gaps")
def review_gaps(session: Session, team: int,
                stats: Stats = "blended") -> View:
    """A team's drop candidates next to the best free agents."""
    _team(session, team)
    return _review(session, stats, build_gaps, team)
