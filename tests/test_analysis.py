import numpy as np
import pandas as pd
import pytest

from fantasy_nhl.analysis import (category_contestedness, category_win_rates,
                                  luck, matchup_result, round_robin)
from fantasy_nhl.config import Category

CATEGORIES = [
    Category("G"),
    Category("A"),
    Category("GAA", inverted=True),
]


class TestMatchupResult:
    def test_win(self):
        # wins G and A, loses inverted GAA -> 2-1
        result = matchup_result(np.array([5, 3, 3.0]), np.array([2, 1, 2.5]), CATEGORIES)
        assert list(result) == [1, 0, 0, 2]

    def test_loss(self):
        result = matchup_result(np.array([2, 1, 2.5]), np.array([5, 3, 3.0]), CATEGORIES)
        assert list(result) == [0, 1, 0, 1]

    def test_inverted_category_lower_wins(self):
        # only GAA differs; lower GAA wins the cat and the matchup
        result = matchup_result(np.array([1, 1, 2.0]), np.array([1, 1, 3.0]), CATEGORIES)
        assert list(result) == [1, 0, 0, 1]

    def test_tie(self):
        stats = np.array([1, 2, 2.5])
        result = matchup_result(stats, stats.copy(), CATEGORIES)
        assert list(result) == [0, 0, 1, 0]

    def test_tie_with_split_cats(self):
        # each wins one cat, one tied -> matchup tied
        result = matchup_result(np.array([2, 1, 2.5]), np.array([1, 2, 2.5]), CATEGORIES)
        assert list(result) == [0, 0, 1, 1]


class TestRoundRobin:
    @pytest.fixture
    def team_names(self):
        return ["AAA", "BBB", "CCC"]

    @pytest.fixture
    def scores(self):
        # AAA dominates, BBB middle, CCC worst (GAA inverted: lower better)
        return np.array([
            [10, 10, 1.0],
            [5, 5, 2.0],
            [1, 1, 3.0],
        ])

    def test_standings(self, scores, team_names):
        result = round_robin(scores, CATEGORIES, team_names)
        assert list(result["Player"]) == ["AAA", "BBB", "CCC"]
        assert list(result["W"]) == [2, 1, 0]
        assert list(result["L"]) == [0, 1, 2]
        assert list(result["T"]) == [0, 0, 0]
        assert list(result["CatsWon"]) == [6, 3, 0]

    def test_points_are_two_wins_plus_ties(self, scores, team_names):
        result = round_robin(scores, CATEGORIES, team_names)
        assert (result["Pts"] == 2 * result["W"] + result["T"]).all()


class TestCategoryWinRates:
    def test_dominant_middle_weak(self):
        # AAA dominates, BBB middle, CCC worst (GAA inverted: lower better)
        scores = np.array([
            [10, 10, 1.0],
            [5, 5, 2.0],
            [1, 1, 3.0],
        ])[:, :, None]  # single week
        result = category_win_rates(scores, CATEGORIES, ["AAA", "BBB", "CCC"])
        assert list(result["Player"]) == ["AAA", "BBB", "CCC"]
        assert result.loc[0, ["G", "A", "GAA"]].tolist() == [1.0, 1.0, 1.0]
        assert result.loc[1, ["G", "A", "GAA"]].tolist() == [0.5, 0.5, 0.5]
        assert result.loc[2, ["G", "A", "GAA"]].tolist() == [0.0, 0.0, 0.0]

    def test_tie_counts_half(self):
        scores = np.array([[5.0], [5.0]])[:, :, None]
        result = category_win_rates(scores, [Category("G")], ["A", "B"])
        assert result["G"].tolist() == [0.5, 0.5]

    def test_inverted_category_lower_wins(self):
        scores = np.array([[2.0], [3.0]])[:, :, None]
        result = category_win_rates(scores, [Category("GAA", inverted=True)], ["A", "B"])
        assert result["GAA"].tolist() == [1.0, 0.0]

    def test_averages_over_weeks(self):
        # A wins week 1, loses week 2 -> 0.5
        scores = np.array([
            [[3.0, 1.0]],
            [[1.0, 3.0]],
        ])
        result = category_win_rates(scores, [Category("G")], ["A", "B"])
        assert result["G"].tolist() == [0.5, 0.5]

    def test_columns_average_to_half(self):
        rng = np.random.default_rng(42)
        scores = rng.integers(0, 5, size=(4, 3, 2)).astype(float)
        result = category_win_rates(scores, CATEGORIES, list("ABCD"))
        for cat in CATEGORIES:
            assert result[cat.name].mean() == pytest.approx(0.5)


class TestCategoryContestedness:
    def test_locked_category(self):
        # one team always wins -> win rates 1 and 0 -> fully locked
        win_rates = pd.DataFrame({"G": [1.0, 0.0], "Player": ["A", "B"]})
        result = category_contestedness(win_rates, [Category("G")])
        assert result["G"] == 0.0

    def test_full_parity(self):
        win_rates = pd.DataFrame({"G": [0.5, 0.5, 0.5], "Player": list("ABC")})
        result = category_contestedness(win_rates, [Category("G")])
        assert result["G"] == 1.0

    def test_partial_spread(self):
        win_rates = pd.DataFrame({"G": [1.0, 0.5, 0.0], "Player": list("ABC")})
        result = category_contestedness(win_rates, [Category("G")])
        assert result["G"] == pytest.approx(1 - 2 * np.sqrt(1 / 6))

    def test_independent_of_tie_frequency(self):
        # constant ties and coin-flip outcomes both give 0.5 win rates
        win_rates = pd.DataFrame({"G": [0.5, 0.5], "GAA": [0.5, 0.5],
                                  "Player": ["A", "B"]})
        result = category_contestedness(
            win_rates, [Category("G"), Category("GAA", inverted=True)])
        assert result["G"] == result["GAA"] == 1.0


class TestLuck:
    def test_lucky(self):
        # won the real matchup (2 pts) but only beat 1 of 3 opponents
        assert luck(2, 2, 3) == pytest.approx(4 / 3)

    def test_unlucky(self):
        # lost the real matchup despite winning all round-robin matchups
        assert luck(0, 6, 3) == pytest.approx(-2)

    def test_zero_when_actual_matches_expected(self):
        assert luck(1, 3, 3) == 0

    def test_vectorized(self):
        actual = pd.Series([2, 0, 1])
        rr_pts = pd.Series([2, 6, 3])
        result = luck(actual, rr_pts, 3)
        assert result.tolist() == pytest.approx([4 / 3, -2, 0])

    def test_league_luck_sums_to_zero(self):
        # every week: total actual pts == total expected pts
        actual = pd.Series([2, 2, 0, 0])
        rr_pts = pd.Series([6, 4, 2, 0])
        assert luck(actual, rr_pts, 3).sum() == pytest.approx(0)
