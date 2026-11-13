"""The leagues themselves: which there are, what the forms need to know
about one, and reloading it."""
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ...config import LeagueConfig
from ...views.common import completed_matchups, week_label
from ..state import LeagueEntry, LeagueSession
from .base import LEAGUE, Entry, Session, local_write, total_weeks, week_dates

router = APIRouter()


class LeagueInfo(BaseModel):
    id: str
    name: str
    year: int
    default: bool  # the league to start on


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
    loaded_at: datetime  # when the league was read from ESPN
    warnings: list[str]  # what could not be loaded


def league_info(league: LeagueEntry | LeagueSession) -> LeagueInfo:
    return LeagueInfo(id=league.id, name=league.config.name,
                      year=league.config.year, default=league.config.default)


def calibration_info(config: LeagueConfig) -> CalibrationInfo | None:
    calibration = config.calibration
    return calibration and CalibrationInfo(source=calibration.source,
                                           calibrated=calibration.calibrated)


@router.get("/leagues")
def leagues(request: Request) -> list[LeagueInfo]:
    return [league_info(entry)
            for entry in request.app.state.store.leagues.values()]


@router.get(LEAGUE)
def league_meta(session: Session) -> LeagueMeta:
    data = session.data
    dates = week_dates(session)
    completed = completed_matchups(data)
    return LeagueMeta(
        **league_info(session).model_dump(), teams=data.team_names,
        current_week=data.current_week, completed_matchups=completed,
        weeks=[WeekInfo(week=week, label=week_label(data, week, dates or {}),
                        completed=week <= completed)
               for week in range(1, total_weeks(session) + 1)],
        categories=[CategoryInfo(name=cat.name, inverted=cat.inverted)
                    for cat in data.config.categories],
        calibration=calibration_info(session.config),
        loaded_at=session.loaded_at,
        warnings=[] if dates is not None else [
            "ESPN's calendar could not be read: matchups have no dates."])


@router.post(f"{LEAGUE}/reload", dependencies=[Depends(local_write)])
def reload(entry: Entry) -> LeagueInfo:
    """Drop everything fetched for the league (after roster moves etc.)."""
    entry.reload()
    return league_info(entry)
