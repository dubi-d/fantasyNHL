"""Pure analysis logic for round-robin category scoring."""
import numpy as np
import pandas as pd

from .config import Category


def matchup_result(player_stats: np.ndarray, opponent_stats: np.ndarray,
                   categories: list[Category]) -> np.ndarray:
    """
    Given accumulated stats of a player and his opponent in a week,
    compute W, L, T, CatsWon.

    :param player_stats: 1D numpy array containing category scores
    :param opponent_stats: 1D numpy array containing category scores
    :param categories: category definitions (order matching the stat arrays)
    :return: 1D numpy array [W, L, T, CatsWon]
    """
    cats_won = 0
    cats_tied = 0

    for i, cat in enumerate(categories):
        if cat.inverted:
            cats_won += int(player_stats[i] < opponent_stats[i])
        else:
            cats_won += int(player_stats[i] > opponent_stats[i])
        cats_tied += int(player_stats[i] == opponent_stats[i])

    cats_lost = len(categories) - cats_tied - cats_won
    W = int(cats_won > cats_lost)
    L = int(cats_won < cats_lost)
    T = int(not (W or L))
    return np.array([W, L, T, cats_won])


def round_robin(scores: np.ndarray, categories: list[Category],
                team_names: list[str]) -> pd.DataFrame:
    """
    Calculate W, L, T, Pts, CatsWon if every team played every other team
    simultaneously in the given week.

    :param scores: Scores summary of a single week (teams x categories).
    :param categories: category definitions (order matching the score columns)
    :param team_names: team names by row index
    :return: Summary statistics
    """
    rr_cats = ["W", "L", "T", "CatsWon", "Pts"]
    number_of_teams = scores.shape[0]
    rr_summary = np.zeros((number_of_teams, len(rr_cats)), dtype=int)

    for i in range(number_of_teams):
        for k in range(number_of_teams):
            if i == k:
                # don't match teams against themselves
                continue

            # match team i against all other teams k, accumulate scores
            rr_summary[i, :-1] += matchup_result(scores[i], scores[k], categories)
        rr_summary[i, -1] = 2 * rr_summary[i, 0] + rr_summary[i, 2]  # calculate points

    rr_summary = pd.DataFrame(rr_summary, columns=rr_cats)
    rr_summary["Player"] = team_names[:number_of_teams]
    return rr_summary


def category_win_rates(weekly_scores: np.ndarray, categories: list[Category],
                       team_names: list[str]) -> pd.DataFrame:
    """
    Per-team win percentage per category across all pairwise round-robin
    comparisons of the given weeks. Ties count as half a win, so every
    category column averages 0.5 across the league.

    :param weekly_scores: scores of the weeks to cover (teams x categories x weeks)
    :param categories: category definitions (order matching the score columns)
    :param team_names: team names by row index
    :return: win rates in [0, 1] (teams x categories), plus a Player column
    """
    num_teams, _, num_weeks = weekly_scores.shape
    wins = np.zeros((num_teams, len(categories)))

    for week in range(num_weeks):
        scores = weekly_scores[:, :, week]
        higher = scores[:, None, :] > scores[None, :, :]  # (team, opponent, category)
        lower = scores[:, None, :] < scores[None, :, :]
        tied = scores[:, None, :] == scores[None, :, :]
        for i, cat in enumerate(categories):
            won = lower[:, :, i] if cat.inverted else higher[:, :, i]
            # the diagonal self-comparison always ties, subtract it
            wins[:, i] += won.sum(axis=1) + 0.5 * (tied[:, :, i].sum(axis=1) - 1)

    rates = wins / ((num_teams - 1) * num_weeks)
    table = pd.DataFrame(rates, columns=[cat.name for cat in categories])
    table["Player"] = team_names[:num_teams]
    return table


def category_contestedness(win_rates: pd.DataFrame,
                           categories: list[Category]) -> pd.Series:
    """
    How up-for-grabs each category is, from the spread of the teams' win
    rates: 1 - std / 0.5. 1 means full parity (every team near 0.5),
    0 means structurally locked (win rates split into 1s and 0s).

    :param win_rates: per-team win rates as returned by category_win_rates
    :param categories: category definitions
    :return: contestedness in [0, 1], indexed by category name
    """
    cat_names = [cat.name for cat in categories]
    return 1 - 2 * win_rates[cat_names].std(ddof=0)


def luck(actual_pts, rr_pts, num_opponents: int):
    """
    Schedule luck: actual matchup points minus points expected from
    round-robin strength. Positive means the schedule was favorable.

    :param actual_pts: points from real matchups (2*W + T), scalar or Series
    :param rr_pts: round-robin points over the same weeks, scalar or Series
    :param num_opponents: round-robin matchups per week (teams - 1)
    :return: actual_pts - rr_pts / num_opponents
    """
    return actual_pts - rr_pts / num_opponents
