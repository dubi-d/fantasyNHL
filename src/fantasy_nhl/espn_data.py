"""Fetching league data from the ESPN fantasy API."""
from dataclasses import dataclass

import numpy as np
from espn_api.hockey import League

from .config import LeagueConfig


@dataclass
class LeagueData:
    """Snapshot of a league's completed matchup weeks.

    weekly_cat_scores axes:
     - axis 0 (rows): team (team_id = row_idx + 1)
     - axis 1 (columns): categories (order from config)
     - axis 2 ("depth"): matchup week
    """
    config: LeagueConfig
    team_names: dict[int, str]  # team_id -> name
    current_week: int
    weekly_cat_scores: np.ndarray


def fetch_league_data(config: LeagueConfig) -> LeagueData:
    """Connect to ESPN and collect weekly category scores for all completed weeks."""
    league = League(
        league_id=config.league_id,
        year=config.year,
        espn_s2=config.espn_s2,
        swid=config.swid,
    )
    current_week = league.currentMatchupPeriod
    team_names = {team.team_id: team.team_name for team in league.teams}

    scores = np.zeros((len(league.teams), len(config.categories), current_week - 1))
    for week in range(1, current_week):
        for matchup in league.scoreboard(week):
            for team, cats in ((matchup.home_team, matchup.home_team_cats),
                               (matchup.away_team, matchup.away_team_cats)):
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
                    scores[team.team_id - 1, i, week - 1] = cats[cat.name]["score"]

    return LeagueData(
        config=config,
        team_names=team_names,
        current_week=current_week,
        weekly_cat_scores=scores,
    )
