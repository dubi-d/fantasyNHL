"""The stored NHL seasons: no league, nothing asked from ESPN. Only the
current season asks the NHL."""
from datetime import datetime
from functools import partial
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ...analysis import season_name
from ...sources.nhl import NhlStatsError
from ...views.history import build_player_history, history_players
from ...views.model import View
from ..state import HistoryStore
from .base import invalid, local_write
from .base import view as _view

router = APIRouter()
view = partial(_view, router, prefix="")


def get_store(request: Request) -> HistoryStore:
    return request.app.state.history


Store = Annotated[HistoryStore, Depends(get_store)]


def get_history(store: Store) -> pd.DataFrame:
    return store.frame()


History = Annotated[pd.DataFrame, Depends(get_history)]


class HistoryPlayer(BaseModel):
    id: int  # the NHL's, not ESPN's
    label: str


class HistoryOptions(BaseModel):
    seasons: list[str]  # the stored ones, oldest first
    players: list[HistoryPlayer]  # everyone in them, by name


class CurrentInfo(BaseModel):
    season: str | None  # none: it is stored as a finished season
    loaded_at: datetime | None  # when it was downloaded from the NHL


@router.get("/history/players")
def history_options(history: History) -> HistoryOptions:
    """Whose history can be asked for."""
    return HistoryOptions(
        seasons=[season_name(season)
                 for season in sorted(history["season"].unique())],
        players=[HistoryPlayer(id=pid, label=label)
                 for label, pid in history_players(history).items()])


@view("/history/player")
def player_history(store: Store, player: int,
                   columns: Literal["fantasy", "all"] = "fantasy",
                   cells: Literal["total", "rate"] = "total",
                   current: bool = False) -> View:
    """
    A player's stored seasons and his average over them.

    :param player: his id (see history/players)
    :param columns: the stats of fantasy categories, or all the NHL has
    :param cells: season totals or per game
    :param current: add the current season, downloaded from the NHL if it
        was not today; without it nothing is asked from anyone
    """
    season, failed = store.current() if current else (None, False)
    # read after that: it may just have stored a season that ended
    history = store.frame()
    if not (history["player_id"] == player).any():
        raise invalid("Unknown player")
    return build_player_history(history, player, columns, cells, season,
                                failed)


@router.post("/history/current/refresh",
             dependencies=[Depends(local_write)])
def refresh_current(store: Store) -> CurrentInfo:
    """Download the current season from the NHL now."""
    try:
        season, _ = store.current(refresh=True)
    except NhlStatsError as error:
        raise HTTPException(502, str(error)) from None
    return CurrentInfo(season=season and season_name(season.season),
                       loaded_at=season and season.loaded)
