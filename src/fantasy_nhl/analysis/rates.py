"""Per-game rates of a player: season stats, projections, their blend."""
import math
from dataclasses import dataclass

from .models import RATIO_CATEGORIES, PreviewPlayer


def _blend(season: float | None, projected: float | None,
           weight: float) -> float | None:
    """Linear blend, falling back to whichever value exists."""
    if season is None:
        return projected
    if projected is None:
        return season
    return weight * season + (1 - weight) * projected


def _stat_games(stats: dict[str, float]) -> float:
    return stats.get("GP") or stats.get("GS") or 0


def _split_per_game(stats: dict[str, float], stat: str) -> float | None:
    games = _stat_games(stats)
    return stats.get(stat, 0.0) / games if games else None


def _split_ratio(stats: dict[str, float], stat: str) -> float | None:
    return stats.get(stat) if _stat_games(stats) else None


def blended_per_game(player: PreviewPlayer, stat: str,
                     weight: float) -> float | None:
    """
    Per-game rate of an additive stat, blending current-season and projected
    rates. Missing stat keys count as 0 for a player with games played.

    :param weight: weight of the current-season rate (0 = projection only)
    :return: blended per-game rate, or None if neither split has games
    """
    return _blend(_split_per_game(player.season_stats, stat),
                  _split_per_game(player.projected_stats, stat), weight)


def blended_ratio(player: PreviewPlayer, stat: str,
                  weight: float) -> float | None:
    """Blend a ratio stat (e.g. GAA) directly, ignoring splits without
    games (ESPN reports placeholder ratios for goalies with no starts);
    None if neither split has games and the stat."""
    return _blend(_split_ratio(player.season_stats, stat),
                  _split_ratio(player.projected_stats, stat), weight)


def _player_rate(player: PreviewPlayer, stat: str,
                 weight: float) -> float | None:
    if stat in RATIO_CATEGORIES:
        return blended_ratio(player, stat, weight)
    return blended_per_game(player, stat, weight)


@dataclass(frozen=True)
class StatBasis:
    """Which player stats a rate is built from: season stats blended with
    ESPN's projection by the elapsed share of the season, or the season
    stats alone."""
    season_only: bool
    season_fraction: float  # share of the season elapsed (0..1)

    @classmethod
    def blended(cls, season_fraction: float) -> "StatBasis":
        return cls(False, season_fraction)

    @classmethod
    def season(cls, season_fraction: float) -> "StatBasis":
        return cls(True, season_fraction)

    @property
    def min_games(self) -> int:
        """Season games a player needs for a Score (see min_season_games);
        season stats alone need at least one game."""
        required = min_season_games(self.season_fraction)
        return max(required, 1) if self.season_only else required


def has_projection(player: PreviewPlayer) -> bool:
    return bool(_stat_games(player.projected_stats))


def has_season_games(player: PreviewPlayer) -> bool:
    return bool(_stat_games(player.season_stats))


def player_rate(player: PreviewPlayer, stat: str,
                basis: StatBasis) -> float | None:
    """Per-game rate of a stat (ratio categories: the ratio itself) on the
    given basis. Blended falls back to whichever of season and projection
    exists; season-only never uses the projection (None without games)."""
    if not basis.season_only:
        return _player_rate(player, stat, basis.season_fraction)
    split = _split_ratio if stat in RATIO_CATEGORIES else _split_per_game
    return split(player.season_stats, stat)


# season games a player needs for a Score over a FULL season; scaled by the
# elapsed fraction (2025-26 pool: per-game rates settle around 20 GP)
MIN_SCORE_GAMES = 20


def min_season_games(blend_weight: float) -> int:
    """Season games required for a Score at this point of the season
    (0 before the season starts, MIN_SCORE_GAMES once it is over)."""
    return math.ceil(MIN_SCORE_GAMES * blend_weight)
