"""Fetching league data from the ESPN fantasy API."""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from espn_api.hockey import League
from espn_api.hockey.constant import POSITION_MAP, PRO_TEAM_MAP

from .analysis import PreviewPlayer
from .config import LeagueConfig

# NHL scoring periods roll over on US/Eastern calendar days
_EASTERN = ZoneInfo("America/New_York")


@dataclass
class LeagueData:
    """Snapshot of a league's matchup weeks (including the ongoing one).

    weekly_cat_scores axes:
     - axis 0 (rows): team (order matching team_names)
     - axis 1 (columns): categories (order from config)
     - axis 2 ("depth"): matchup week (last one = ongoing current week)
    """
    config: LeagueConfig
    team_names: list[str]  # by row index
    current_week: int
    weekly_cat_scores: np.ndarray
    weekly_results: list[list[str]]  # [row][week-1] -> 'W'/'L'/'T'/'NA'
    total_weeks: int = 0  # matchup weeks including playoffs
    regular_weeks: int = 0  # regular-season matchup weeks
    espn_league: League | None = field(default=None, repr=False)


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
    remaining_periods: list[int]  # periods strictly after today
    blend_weight: float  # weight of current-season rates vs projections
    actual_games: np.ndarray  # player games counted on elapsed days, by row
    actual_goalie_games: np.ndarray  # goalie games counted on elapsed days
    start_date: date | None = None  # first calendar day of the week
    end_date: date | None = None  # last calendar day of the week


def fetch_league_data(config: LeagueConfig) -> LeagueData:
    """Connect to ESPN and collect weekly category scores and matchup results
    for all weeks up to and including the ongoing one."""
    league = League(
        league_id=config.league_id,
        year=config.year,
        espn_s2=config.espn_s2,
        swid=config.swid,
    )
    current_week = league.currentMatchupPeriod
    # team IDs are not necessarily contiguous, map them to array rows
    row_by_team_id = {team.team_id: row for row, team in enumerate(league.teams)}
    team_names = [team.team_name for team in league.teams]

    scores = np.zeros((len(league.teams), len(config.categories), current_week))
    results = [["NA"] * current_week for _ in league.teams]
    for week in range(1, current_week + 1):
        for matchup in league.scoreboard(week):
            home_row = row_by_team_id[matchup.home_team.team_id]
            away_row = row_by_team_id[matchup.away_team.team_id]
            if matchup.winner == "HOME":
                results[home_row][week - 1] = "W"
                results[away_row][week - 1] = "L"
            elif matchup.winner == "AWAY":
                results[home_row][week - 1] = "L"
                results[away_row][week - 1] = "W"
            elif matchup.winner == "TIE":
                results[home_row][week - 1] = "T"
                results[away_row][week - 1] = "T"

            for row, cats in ((home_row, matchup.home_team_cats),
                              (away_row, matchup.away_team_cats)):
                if cats is None:
                    continue
                missing = [c.name for c in config.categories if c.name not in cats]
                if missing:
                    raise ValueError(
                        f"Categories {missing} not scored by league "
                        f"'{config.name}'; ESPN reports {sorted(cats)}. "
                        f"Fix the categories in config.yaml."
                    )
                for i, cat in enumerate(config.categories):
                    scores[row, i, week - 1] = cats[cat.name]["score"]

    return LeagueData(
        config=config,
        team_names=team_names,
        current_week=current_week,
        weekly_cat_scores=scores,
        weekly_results=results,
        total_weeks=len(league.settings.matchup_periods),
        regular_weeks=league.settings.reg_season_count,
        espn_league=league,
    )


def _period_dates(pro_schedule: dict, first_period: int,
                  final_period: int) -> dict[int, date]:
    """Calendar date of every scoring period, extrapolated from the earliest
    scheduled NHL game (scoring periods are consecutive Eastern-time days)."""
    dated: dict[int, date] = {}
    for games_by_period in pro_schedule.values():
        for period_str, games in games_by_period.items():
            for game in games:
                day = datetime.fromtimestamp(game["date"] / 1000,
                                             tz=_EASTERN).date()
                period = int(period_str)
                if period not in dated or day < dated[period]:
                    dated[period] = day
    if not dated:
        raise ValueError("ESPN pro schedule is empty; cannot derive weeks.")
    anchor = min(dated)
    return {p: dated[anchor] + timedelta(days=p - anchor)
            for p in range(first_period, final_period + 1)}


def _week_scoring_periods(league: League,
                          period_dates: dict[int, date]) -> dict[int, list[int]]:
    """Scoring periods per matchup week: exact (from ESPN's scored days) for
    elapsed weeks, Mon-Sun calendar extrapolation for future days. ESPN does
    not publish the mapping for days that have not been scored yet."""
    groups: dict[tuple, list[int]] = {}
    for period, day in period_dates.items():
        groups.setdefault(tuple(day.isocalendar()[:2]), []).append(period)
    calendar_weeks = [sorted(ps) for _, ps in sorted(groups.items())]

    known = {int(w): sorted(int(p) for p in ps)
             for w, ps in league.matchup_ids.items()}
    current = league.currentMatchupPeriod
    mapping = {w: ps for w, ps in known.items() if w < current}
    reg_weeks = league.settings.reg_season_count
    # playoff matchup periods can span several calendar weeks
    playoff_len = max(league.settings.playoff_matchup_period_length, 1)

    def week_length(week: int) -> int:
        return playoff_len if week > reg_weeks else 1

    def group_index(period: int) -> int:
        return next(i for i, g in enumerate(calendar_weeks) if period in g)

    if current in known:
        # extend the ongoing week's scored days to the end of its calendar span
        last = max(known[current])
        end = max(group_index(last),
                  group_index(min(known[current])) + week_length(current) - 1)
        span = {p for g in calendar_weeks[group_index(last):end + 1] for p in g}
        mapping[current] = sorted(set(known[current])
                                  | {p for p in span if p > last})
    else:
        # no day scored yet: the week starts right after the last scored one
        start = max(mapping[current - 1]) + 1 if current - 1 in mapping \
            else league.firstScoringPeriod
        idx = next((i for i, g in enumerate(calendar_weeks) if start in g), None)
        mapping[current] = [] if idx is None else \
            [p for g in calendar_weeks[idx:idx + week_length(current)]
             for p in g if p >= start]

    last = max(mapping[current], default=0)
    future = [g for g in calendar_weeks if g[0] > last]
    week = current + 1
    i = 0
    while i < len(future):
        length = week_length(week)
        mapping[week] = [p for g in future[i:i + length] for p in g]
        week += 1
        i += length
    return mapping


def _fetch_slot_counts(league: League) -> dict[str, int]:
    """Active lineup slot capacities from the raw settings (the espn_api
    wrapper does not retain rosterSettings)."""
    data = league.espn_request.league_get(params={"view": "mSettings"})
    raw_counts = data["settings"]["rosterSettings"]["lineupSlotCounts"]
    slot_counts = {}
    for slot_id, count in raw_counts.items():
        name = POSITION_MAP.get(int(slot_id))
        if count > 0 and isinstance(name, str) and name not in ("Bench", "IR"):
            slot_counts[name] = count
    return slot_counts


def _preview_rosters(league: League, year: int,
                     slot_counts: dict[str, int]) -> list[list[PreviewPlayer]]:
    """Current rosters as PreviewPlayers by team row, excluding IR players."""
    rosters = []
    for team in league.teams:
        players = []
        for player in team.roster:
            if player.lineupSlot == "IR":
                continue
            eligible = [s for s in player.eligibleSlots if s in slot_counts]
            if not eligible:
                continue
            players.append(PreviewPlayer(
                name=player.name,
                pro_team=player.proTeam,
                eligible_slots=eligible,
                season_stats=player.stats.get(f"Total {year}",
                                              {}).get("total") or {},
                projected_stats=player.stats.get(f"Projected {year}",
                                                 {}).get("total") or {},
            ))
        rosters.append(players)
    return rosters


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

    pro_schedule = league._get_all_pro_schedule()
    period_dates = _period_dates(pro_schedule, league.firstScoringPeriod,
                                 league.finalScoringPeriod)
    week_periods = _week_scoring_periods(league, period_dates)
    if week not in week_periods:
        raise ValueError(f"No scoring periods known for week {week}.")
    periods = week_periods[week]
    # live totals already cover today; predict only the days after it
    remaining_periods = [p for p in periods if p > league.scoringPeriodId]

    playing_by_period: dict[int, set[str]] = {}
    for team_id, games_by_period in pro_schedule.items():
        name = PRO_TEAM_MAP.get(team_id)
        if name is None:
            continue
        for period_str, games in games_by_period.items():
            if games:
                playing_by_period.setdefault(int(period_str), set()).add(name)

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

    season_span = league.finalScoringPeriod - league.firstScoringPeriod
    elapsed = league.scoringPeriodId - league.firstScoringPeriod
    blend_weight = min(max(elapsed / season_span if season_span else 1.0, 0.0), 1.0)

    remaining_set = set(remaining_periods)
    games_by_id, goalie_by_id = _actual_games(
        league, week, [p for p in periods if p not in remaining_set])
    actual_games = np.zeros(len(league.teams))
    actual_goalie_games = np.zeros(len(league.teams))
    for team_id, row in row_by_team_id.items():
        actual_games[row] = games_by_id.get(team_id, 0)
        actual_goalie_games[row] = goalie_by_id.get(team_id, 0)

    slot_counts = _fetch_slot_counts(league)
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
    )
