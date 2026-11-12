"""Predicted category scores of a matchup week."""
import numpy as np

from ..config import Category
from .models import _GOALIE_SLOT, RATIO_CATEGORIES, PreviewPlayer
from .rates import StatBasis, player_rate
from .seats import seat_counts


def preview_week(players: list[PreviewPlayer], slot_counts: dict[str, int],
                 playing_by_period: dict[int, set[str]],
                 remaining_periods: list[int],
                 actual_scores: np.ndarray, categories: list[Category],
                 basis: StatBasis, actual_games: int = 0,
                 actual_goalie_games: int = 0) -> tuple[int, np.ndarray]:
    """
    Playable games and predicted final category scores of one team's matchup
    week: actual accumulated scores plus per-game-rate predictions over the
    remaining days. Ratio categories (GAA, SV%) are averaged per goalie game
    instead of summed; the actual portion is weighted by the goalie games
    actually played on the elapsed days.

    :param players: current roster (active players only)
    :param slot_counts: active lineup slots (name -> capacity)
    :param playing_by_period: scoring period -> NHL teams with a game that day
    :param remaining_periods: the scoring periods that still have to be predicted
    :param actual_scores: accumulated real category scores so far (config order)
    :param categories: category definitions
    :param basis: stats the per-game rates of the remaining days come from
    :param actual_games: player games actually counted on the elapsed days
    :param actual_goalie_games: goalie games actually counted on the elapsed days
    :return: (actual plus playable remaining games, predicted category scores)
    """
    remaining = seat_counts(players, slot_counts, playing_by_period,
                            remaining_periods)
    games = int(actual_games) + sum(remaining)

    is_goalie = [_GOALIE_SLOT in p.eligible_slots for p in players]

    totals = np.zeros(len(categories))
    for i, cat in enumerate(categories):
        if cat.name in RATIO_CATEGORIES:
            # ESPN reports GAA as inf before the first goalie game
            weighted = (actual_scores[i] * actual_goalie_games
                        if actual_goalie_games else 0.0)
            goalie_games = actual_goalie_games
            for player, n, goalie in zip(players, remaining, is_goalie):
                if not (goalie and n):
                    continue
                value = player_rate(player, cat.name, basis)
                if value is None:
                    continue
                weighted += value * n
                goalie_games += n
            totals[i] = weighted / goalie_games if goalie_games else actual_scores[i]
        else:
            totals[i] = actual_scores[i] + sum(
                (player_rate(player, cat.name, basis) or 0.0) * n
                for player, n in zip(players, remaining))
    return games, totals
