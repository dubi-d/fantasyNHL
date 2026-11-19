"""The stored NHL seasons: no league, nothing asked from ESPN."""
from functools import partial
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ...analysis import season_name
from ...views.history import build_player_history, history_players
from ...views.model import View
from .base import invalid
from .base import view as _view

router = APIRouter()
view = partial(_view, router, prefix="")


def get_history(request: Request) -> pd.DataFrame:
    return request.app.state.history.frame()


History = Annotated[pd.DataFrame, Depends(get_history)]


class HistoryPlayer(BaseModel):
    id: int  # the NHL's, not ESPN's
    label: str


class HistoryOptions(BaseModel):
    seasons: list[str]  # the stored ones, oldest first
    players: list[HistoryPlayer]  # everyone in them, by name


@router.get("/history/players")
def history_options(history: History) -> HistoryOptions:
    """Whose history can be asked for."""
    return HistoryOptions(
        seasons=[season_name(season)
                 for season in sorted(history["season"].unique())],
        players=[HistoryPlayer(id=pid, label=label)
                 for label, pid in history_players(history).items()])


@view("/history/player")
def player_history(history: History, player: int,
                   columns: Literal["fantasy", "all"] = "fantasy",
                   cells: Literal["total", "rate"] = "total") -> View:
    """
    A player's stored seasons and his average over them.

    :param player: his id (see history/players)
    :param columns: the stats of fantasy categories, or all the NHL has
    :param cells: season totals or per game
    """
    if not (history["player_id"] == player).any():
        raise invalid("Unknown player")
    return build_player_history(history, player, columns, cells)
