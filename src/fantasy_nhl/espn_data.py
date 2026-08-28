"""Fetching league data from the ESPN fantasy API."""
from dataclasses import dataclass

import numpy as np
from espn_api.hockey import League

from .config import LeagueConfig


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
    )
