"""Everything for previewing one matchup week."""
import json
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
from espn_api.hockey import League
from espn_api.hockey.constant import POSITION_MAP

from ...analysis import PreviewPlayer
from .calendar import _EASTERN, fetch_schedule_data
from .league import LeagueData
from .players import _blend_weight, _fetch_roster_settings, _preview_rosters


@dataclass
class PreviewData:
    """Inputs for previewing one matchup week (team order matches LeagueData)."""
    week: int
    pairings: list[tuple[int, int]]  # (home row, away row)
    actual_scores: np.ndarray  # teams x categories, zeros where not yet played
    rosters: list[list[PreviewPlayer]]  # by team row, IR players excluded
    slot_counts: dict[str, int]  # active lineup slots (name -> capacity)
    playing_by_period: dict[int, set[str]]  # period -> NHL teams with a game
    periods: list[int]  # scoring periods of the week
    remaining_periods: list[int]  # periods still to predict: today and later
    blend_weight: float  # weight of current-season rates vs projections
    actual_games: np.ndarray  # player games already counted, by row
    actual_goalie_games: np.ndarray  # goalie games already counted
    start_date: date | None = None  # first calendar day of the week
    end_date: date | None = None  # last calendar day of the week
    current_period: int = 0  # today's scoring period
    period_dates: dict[int, date] = field(default_factory=dict)  # week's days
    add_limit: int | None = None  # weekly acquisition limit (None = no limit)
    next_periods: list[int] = field(default_factory=list)  # next week's days
    # NHL teams whose game today had started at fetch time (counted as actual)
    started_today: set[str] = field(default_factory=set)


def _actual_games(league: League, week: int,
                  elapsed_periods: list[int]) -> tuple[dict[int, float],
                                                       dict[int, float]]:
    """Player games actually counted per fantasy team (id) on the elapsed
    days. ESPN only exposes the historical daily lineups one scoring period
    per request."""
    games: dict[int, float] = {}
    goalie_games: dict[int, float] = {}
    filters = {"schedule": {"filterMatchupPeriodIds": {"value": [week]}}}
    headers = {"x-fantasy-filter": json.dumps(filters)}
    for period in elapsed_periods:
        data = league.espn_request.league_get(
            params={"view": ["mMatchupScore", "mScoreboard"],
                    "scoringPeriodId": period},
            headers=headers)
        for entry in data["schedule"]:
            for side in ("home", "away"):
                team = entry.get(side)
                if team is None:
                    continue
                roster = team.get("rosterForCurrentScoringPeriod", {})
                for e in roster.get("entries", []):
                    slot = POSITION_MAP.get(e.get("lineupSlotId"))
                    if slot in ("Bench", "IR"):
                        continue
                    player = e["playerPoolEntry"]["player"]
                    for split in player.get("stats", []):
                        if (split.get("scoringPeriodId") != period
                                or split.get("statSourceId") != 0):
                            continue
                        raw = split.get("stats", {})
                        # skaters report GP (34), goalies GS (0)
                        gp = raw.get("34") or raw.get("0") or 0
                        tid = team["teamId"]
                        games[tid] = games.get(tid, 0) + gp
                        if slot == "Goalie":
                            goalie_games[tid] = goalie_games.get(tid, 0) + gp
    return games, goalie_games


def fetch_preview_data(data: LeagueData, week: int) -> PreviewData:
    """Fetch everything needed to preview the given matchup week: pairings,
    accumulated real scores, current rosters, lineup slots and NHL schedule."""
    league = data.espn_league
    if league is None:
        raise ValueError("LeagueData has no live ESPN session.")

    schedule = fetch_schedule_data(data)
    period_dates = schedule.period_dates
    week_periods = schedule.week_periods
    if week not in week_periods:
        raise ValueError(f"No scoring periods known for week {week}.")
    periods = week_periods[week]
    next_periods = week_periods.get(week + 1, [])
    today = league.scoringPeriodId
    # live totals cover today's started games; the rest of today is predicted
    remaining_periods = [p for p in periods if p >= today]
    now = datetime.now(tz=_EASTERN)
    started_today = {team for team, start
                     in schedule.game_starts.get(today, {}).items()
                     if start <= now}

    playing_by_period = schedule.playing_by_period

    row_by_team_id = {team.team_id: row for row, team in enumerate(league.teams)}
    pairings = []
    actual_scores = np.zeros((len(league.teams), len(data.config.categories)))
    for matchup in league.scoreboard(week):
        home_row = row_by_team_id[matchup.home_team.team_id]
        away_row = row_by_team_id[matchup.away_team.team_id]
        pairings.append((home_row, away_row))
        for row, cats in ((home_row, matchup.home_team_cats),
                          (away_row, matchup.away_team_cats)):
            if cats is None:
                continue
            for i, cat in enumerate(data.config.categories):
                actual_scores[row, i] = cats[cat.name]["score"]

    blend_weight = _blend_weight(league)

    counted = [p for p in periods if p < today
               or (p == today and started_today)]
    games_by_id, goalie_by_id = _actual_games(league, week, counted)
    actual_games = np.zeros(len(league.teams))
    actual_goalie_games = np.zeros(len(league.teams))
    for team_id, row in row_by_team_id.items():
        actual_games[row] = games_by_id.get(team_id, 0)
        actual_goalie_games[row] = goalie_by_id.get(team_id, 0)

    slot_counts, add_limit = _fetch_roster_settings(league)
    return PreviewData(
        week=week,
        pairings=pairings,
        actual_scores=actual_scores,
        rosters=_preview_rosters(league, data.config.year, slot_counts),
        slot_counts=slot_counts,
        playing_by_period=playing_by_period,
        periods=periods,
        remaining_periods=remaining_periods,
        blend_weight=blend_weight,
        actual_games=actual_games,
        actual_goalie_games=actual_goalie_games,
        start_date=period_dates.get(min(periods)) if periods else None,
        end_date=period_dates.get(max(periods)) if periods else None,
        current_period=league.scoringPeriodId,
        period_dates={p: period_dates[p] for p in periods + next_periods
                      if p in period_dates},
        add_limit=add_limit,
        next_periods=next_periods,
        started_today=started_today,
    )
