"""A past season's rosters and schedule for calibrating the scoring."""
from dataclasses import dataclass

from espn_api.hockey import League

from ...analysis import PreviewPlayer
from ...config import LeagueConfig
from .calendar import _playing_by_period
from .players import _fetch_roster_settings, _preview_rosters


@dataclass
class CalibrationData:
    """A past season's rosters and NHL schedule for scoring calibration."""
    rosters: list[list[PreviewPlayer]]
    slot_counts: dict[str, int]
    playing_by_period: dict[int, set[str]]


def fetch_calibration_data(source: LeagueConfig) -> CalibrationData:
    """Fetch a (finished) season's final rosters, lineup slots and NHL
    schedule to calibrate the schedule-scoring night-value curve."""
    league = League(
        league_id=source.league_id,
        year=source.year,
        espn_s2=source.espn_s2,
        swid=source.swid,
    )
    slot_counts, _ = _fetch_roster_settings(league)
    return CalibrationData(
        rosters=_preview_rosters(league, source.year, slot_counts),
        slot_counts=slot_counts,
        playing_by_period=_playing_by_period(league._get_all_pro_schedule()),
    )
