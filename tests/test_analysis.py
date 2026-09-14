import math

import numpy as np
import pandas as pd
import pytest
from statistics import NormalDist

from fantasy_nhl.analysis import (
    FULL_SEASON_GP,
    FULL_SEASON_GS,
    MIN_SCORE_GAMES,
    PUNT_Z,
    SEAT_CAP,
    DraftPick,
    PreviewPlayer,
    RosterPlayer,
    TransactionCounts,
    acquisition_summary,
    average_points,
    blended_per_game,
    calibrate_night_value,
    category_contestedness,
    category_outlook,
    category_win_rates,
    draft_extremes,
    draft_pick_table,
    draft_return,
    draft_team_summary,
    draft_value_grid,
    drafted_rosters,
    effective_games,
    luck,
    market_gaps,
    matchup_result,
    max_lineup_seats,
    min_season_games,
    night_seat_curve,
    off_night_periods,
    open_seat_counts,
    percentile_ranks,
    pick_weekly_awards,
    player_table,
    player_value_scores,
    player_values,
    position_open_seats,
    preview_week,
    projected_category_balance,
    rank_streaming_candidates,
    rank_timeline,
    replacement_rates,
    roster_origins,
    round_robin,
    schedule_summary,
    seat_counts,
    team_gap_coverage,
    team_week_schedule,
    trailing_points,
    weekly_points_timeline,
)
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


class TestWeeklyPointsTimeline:
    TEAMS = ["AAA", "BBB", "CCC"]

    @pytest.fixture
    def cube(self):
        # week 1: AAA dominates; week 2: CCC dominates; week 3: all tied
        week1 = np.array([
            [10, 10, 1.0],
            [5, 5, 2.0],
            [1, 1, 3.0],
        ])
        week2 = week1[::-1]
        week3 = np.array([[5, 5, 2.0]] * 3)
        return np.stack([week1, week2, week3], axis=2)

    def test_weekly_points(self, cube):
        timeline = weekly_points_timeline(cube, CATEGORIES, self.TEAMS)
        assert list(timeline.index) == self.TEAMS
        assert list(timeline.columns) == [1, 2, 3]
        assert timeline.loc["AAA"].tolist() == [4, 0, 2]
        assert timeline.loc["BBB"].tolist() == [2, 2, 2]
        assert timeline.loc["CCC"].tolist() == [0, 4, 2]

    def test_week_columns_sum_to_full_pot(self, cube):
        # every pairing awards 2 pts total
        timeline = weekly_points_timeline(cube, CATEGORIES, self.TEAMS)
        teams = len(self.TEAMS)
        assert (timeline.sum(axis=0) == teams * (teams - 1)).all()


class TestRankTimeline:
    def test_ranks_by_cumulative_points(self):
        cumulative = pd.DataFrame({1: [4, 2, 0], 2: [4, 4, 4]},
                                  index=["AAA", "BBB", "CCC"])
        ranks = rank_timeline(cumulative)
        assert ranks[1].tolist() == [1, 2, 3]
        assert ranks[2].tolist() == [1, 1, 1]

    def test_ties_share_better_rank(self):
        cumulative = pd.DataFrame({1: [4, 4, 0]}, index=["AAA", "BBB", "CCC"])
        assert rank_timeline(cumulative)[1].tolist() == [1, 1, 3]


class TestTrailingPoints:
    def test_partial_then_sliding_window(self):
        timeline = pd.DataFrame({1: [4, 0], 2: [2, 2], 3: [0, 4]},
                                index=["AAA", "BBB"])
        result = trailing_points(timeline, 2)
        assert result.loc["AAA"].tolist() == [4, 6, 2]
        assert result.loc["BBB"].tolist() == [0, 2, 6]

    def test_window_covering_all_weeks_equals_cumsum(self):
        timeline = pd.DataFrame({1: [4, 0], 2: [2, 2]}, index=["AAA", "BBB"])
        result = trailing_points(timeline, 5)
        assert (result == timeline.cumsum(axis=1)).all().all()


class TestAveragePoints:
    def test_average_up_to_each_week(self):
        timeline = pd.DataFrame({1: [4, 0], 2: [0, 4]}, index=["AAA", "BBB"])
        result = average_points(timeline)
        assert result.loc["AAA"].tolist() == [4.0, 2.0]
        assert result.loc["BBB"].tolist() == [0.0, 2.0]

    def test_league_mean_is_teams_minus_one(self):
        # each week column awards teams*(teams-1) pts in total
        timeline = pd.DataFrame({1: [4, 2, 0], 2: [2, 2, 2]},
                                index=["AAA", "BBB", "CCC"])
        result = average_points(timeline)
        assert result.mean(axis=0).tolist() == pytest.approx([2.0, 2.0])


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


class TestPickWeeklyAwards:
    def test_core_four(self):
        # 4 teams: C won despite weak stats, B lost despite strong stats
        table = pd.DataFrame({
            "Player": ["A", "B", "C", "D"],
            "Pts": [6, 4, 2, 0],
            "Luck": [0.0, -4 / 3, 4 / 3, 0.0],
            "Result": ["W", "L", "W", "L"],
        })
        awards = pick_weekly_awards(table)
        assert awards["best"]["Player"] == "A"
        assert awards["worst"]["Player"] == "D"
        assert awards["luckiest_win"]["Player"] == "C"
        assert awards["biggest_choke"]["Player"] == "B"

    def test_row_index_preserved(self):
        table = pd.DataFrame({
            "Player": ["A", "B"],
            "Pts": [2, 0],
            "Luck": [0.0, 0.0],
            "Result": ["W", "L"],
        }, index=[7, 3])
        awards = pick_weekly_awards(table)
        assert awards["best"].name == 7
        assert awards["biggest_choke"].name == 3

    def test_no_decided_results(self):
        # e.g. a playoff week before any result: only best/worst awarded
        table = pd.DataFrame({
            "Player": ["A", "B"],
            "Pts": [2, 0],
            "Luck": [float("nan")] * 2,
            "Result": ["NA", "NA"],
        })
        awards = pick_weekly_awards(table)
        assert set(awards) == {"best", "worst"}


class TestMaxLineupSeats:
    def test_greedy_trap_resolved(self):
        # flexible player must yield the Center slot to the Center-only player
        eligible = [["Center", "Left Wing"], ["Center"]]
        assert max_lineup_seats(eligible, {"Center": 1, "Left Wing": 1}) == [0, 1]

    def test_slot_capacity(self):
        eligible = [["Defense"], ["Defense"], ["Defense"]]
        assert max_lineup_seats(eligible, {"Defense": 2}) == [0, 1]

    def test_displacement_chain(self):
        # third player cannot be seated: both slots stay occupied
        eligible = [["Center", "Left Wing"], ["Center"], ["Left Wing"]]
        seated = max_lineup_seats(eligible, {"Center": 1, "Left Wing": 1})
        assert len(seated) == 2

    def test_ineligible_player(self):
        assert max_lineup_seats([["Goalie"]], {"Center": 1}) == []

    def test_no_players(self):
        assert max_lineup_seats([], {"Center": 1}) == []


class TestSeatCounts:
    SLOTS = {"Center": 1, "Goalie": 1}

    def test_counts_days_with_games(self):
        players = [PreviewPlayer("A", "Boston Bruins", ["Center"])]
        playing = {1: {"Boston Bruins"}, 2: set(), 3: {"Boston Bruins"}}
        assert seat_counts(players, self.SLOTS, playing, [1, 2, 3]) == [2]

    def test_team_without_game_excluded(self):
        players = [PreviewPlayer("A", "Boston Bruins", ["Center"])]
        playing = {1: {"Dallas Stars"}}
        assert seat_counts(players, self.SLOTS, playing, [1]) == [0]

    def test_capped_by_slots(self):
        players = [PreviewPlayer("A", "Boston Bruins", ["Center"]),
                   PreviewPlayer("B", "Dallas Stars", ["Center"])]
        playing = {1: {"Boston Bruins", "Dallas Stars"}}
        assert seat_counts(players, self.SLOTS, playing, [1]) == [1, 0]


class TestBlendedPerGame:
    PLAYER = PreviewPlayer("A", "Boston Bruins", ["Center"],
                           season_stats={"GP": 10, "G": 5},
                           projected_stats={"GP": 80, "G": 20})

    def test_full_season_weight(self):
        assert blended_per_game(self.PLAYER, "G", 1.0) == pytest.approx(0.5)

    def test_full_projection_weight(self):
        assert blended_per_game(self.PLAYER, "G", 0.0) == pytest.approx(0.25)

    def test_blend(self):
        assert blended_per_game(self.PLAYER, "G", 0.5) == pytest.approx(0.375)

    def test_no_season_games_falls_back_to_projection(self):
        player = PreviewPlayer("A", "Boston Bruins", ["Center"],
                               season_stats={"GP": 0, "G": 0},
                               projected_stats={"GP": 80, "G": 20})
        assert blended_per_game(player, "G", 1.0) == pytest.approx(0.25)

    def test_goalie_uses_games_started(self):
        goalie = PreviewPlayer("G", "Boston Bruins", ["Goalie"],
                               season_stats={"GS": 10, "SV": 250})
        assert blended_per_game(goalie, "SV", 1.0) == pytest.approx(25.0)

    def test_missing_stat_counts_as_zero(self):
        # e.g. DEF for a forward with games played
        assert blended_per_game(self.PLAYER, "DEF", 1.0) == pytest.approx(0.0)

    def test_no_data_returns_none(self):
        player = PreviewPlayer("A", "Boston Bruins", ["Center"])
        assert blended_per_game(player, "G", 0.5) is None


class TestPreviewWeek:
    CATEGORIES = [Category("G"), Category("GAA", inverted=True)]
    SLOTS = {"Center": 1, "Goalie": 1}

    @pytest.fixture
    def players(self):
        return [
            PreviewPlayer("Skater", "Boston Bruins", ["Center"],
                          season_stats={"GP": 10, "G": 5, "GAA": 99}),
            PreviewPlayer("Goalie", "Dallas Stars", ["Goalie"],
                          season_stats={"GS": 10, "GAA": 2.0}),
        ]

    # both NHL teams play every day of the 3-day week
    PLAYING = {p: {"Boston Bruins", "Dallas Stars"} for p in (1, 2, 3)}

    def test_completed_week_returns_actual(self, players):
        actual = np.array([7.0, 3.5])
        games, totals = preview_week(players, self.SLOTS, self.PLAYING,
                                     [], actual, self.CATEGORIES, 1.0,
                                     actual_games=5, actual_goalie_games=3)
        assert games == 5  # taken from actual games, not the roster replay
        assert totals == pytest.approx([7.0, 3.5])

    def test_future_week_pure_prediction(self, players):
        games, totals = preview_week(players, self.SLOTS, self.PLAYING,
                                     [1, 2, 3], np.zeros(2),
                                     self.CATEGORIES, 1.0)
        assert games == 6
        # skater: 0.5 G/game * 3 games; goalie GAA: his own average
        assert totals == pytest.approx([1.5, 2.0])

    def test_ongoing_week_blends_actual_and_prediction(self, players):
        # day 1-2 elapsed (actual: 2 G, GAA 3.5, 4 games), day 3 predicted
        actual = np.array([2.0, 3.5])
        games, totals = preview_week(players, self.SLOTS, self.PLAYING,
                                     [3], actual, self.CATEGORIES, 1.0,
                                     actual_games=4, actual_goalie_games=2)
        assert games == 6
        # G: 2 + 0.5 * 1; GAA: (3.5 * 2 + 2.0 * 1) / 3
        assert totals == pytest.approx([2.5, 3.0])

    def test_ratio_ignores_skater_stats(self, players):
        # the skater's bogus GAA=99 must not contaminate the goalie average
        _, totals = preview_week(players, self.SLOTS, self.PLAYING,
                                 [1], np.zeros(2), self.CATEGORIES, 1.0)
        assert totals[1] == pytest.approx(2.0)

    def test_ratio_multiple_goalies_weighted_by_games(self):
        players = [
            PreviewPlayer("G1", "Boston Bruins", ["Goalie"],
                          season_stats={"GS": 10, "GAA": 2.0}),
            PreviewPlayer("G2", "Dallas Stars", ["Goalie"],
                          season_stats={"GS": 10, "GAA": 3.0}),
        ]
        # two goalie slots: G1 plays days 1+2, G2 only day 1
        playing = {1: {"Boston Bruins", "Dallas Stars"}, 2: {"Boston Bruins"}}
        _, totals = preview_week(players, {"Goalie": 2}, playing,
                                 [1, 2], np.zeros(2),
                                 self.CATEGORIES, 1.0)
        assert totals[1] == pytest.approx((2.0 * 2 + 3.0 * 1) / 3)

    def test_projection_blend_weight(self, players):
        players[0].projected_stats = {"GP": 10, "G": 10}  # 1.0 G/game
        _, totals = preview_week(players, self.SLOTS, self.PLAYING,
                                 [1], np.zeros(2), self.CATEGORIES, 0.5)
        # blended rate (0.5 + 1.0) / 2 = 0.75 over one game
        assert totals[0] == pytest.approx(0.75)


class TestOpenSeatCounts:
    SLOTS = {"Center": 1, "Defense": 1, "Goalie": 1}

    def test_all_seats_open_when_nobody_plays(self):
        players = [PreviewPlayer("A", "Boston Bruins", ["Center"])]
        assert open_seat_counts(players, self.SLOTS, {1: set()}, [1]) \
            == {1: (2, 1)}

    def test_playing_player_fills_a_seat(self):
        players = [PreviewPlayer("A", "Boston Bruins", ["Center"])]
        playing = {1: {"Boston Bruins"}}
        assert open_seat_counts(players, self.SLOTS, playing, [1]) \
            == {1: (1, 1)}

    def test_goalie_pool_is_separate(self):
        # a goalie never fills a skater seat, a skater never a goalie seat
        players = [PreviewPlayer("G", "Boston Bruins", ["Goalie"]),
                   PreviewPlayer("A", "Boston Bruins", ["Center", "Defense"]),
                   PreviewPlayer("B", "Boston Bruins", ["Center", "Defense"]),
                   PreviewPlayer("C", "Boston Bruins", ["Center"])]
        playing = {1: {"Boston Bruins"}}
        assert open_seat_counts(players, self.SLOTS, playing, [1]) \
            == {1: (0, 0)}

    def test_matching_moves_flexible_player(self):
        # the C/D player must shift to Defense so both seats fill
        players = [PreviewPlayer("A", "Boston Bruins", ["Center", "Defense"]),
                   PreviewPlayer("B", "Boston Bruins", ["Center"])]
        playing = {1: {"Boston Bruins"}}
        assert open_seat_counts(players, self.SLOTS, playing, [1]) \
            == {1: (0, 1)}

    def test_dropping_a_player_opens_his_days(self):
        players = [PreviewPlayer("A", "Boston Bruins", ["Center"]),
                   PreviewPlayer("B", "Dallas Stars", ["Defense"])]
        playing = {1: {"Boston Bruins", "Dallas Stars"}, 2: {"Boston Bruins"}}
        kept = [p for p in players if p.name != "A"]
        assert open_seat_counts(players, self.SLOTS, playing, [1, 2]) \
            == {1: (0, 1), 2: (1, 1)}
        assert open_seat_counts(kept, self.SLOTS, playing, [1, 2]) \
            == {1: (1, 1), 2: (2, 1)}

    def test_multiple_days(self):
        players = [PreviewPlayer("A", "Boston Bruins", ["Center"])]
        playing = {1: {"Boston Bruins"}, 2: set()}
        assert open_seat_counts(players, self.SLOTS, playing, [1, 2]) \
            == {1: (1, 1), 2: (2, 1)}


class TestPositionOpenSeats:
    def test_all_slots_reported_separately(self):
        slots = {"Center": 1, "Left Wing": 1, "Util": 1}
        assert position_open_seats([], slots, {1: set()}, [1]) \
            == {1: {"Center": 1, "Left Wing": 1, "Util": 1}}

    def test_specific_seat_filled_before_util(self):
        slots = {"Center": 1, "Util": 1}
        players = [PreviewPlayer("A", "Boston Bruins", ["Center", "Util"])]
        playing = {1: {"Boston Bruins"}}
        assert position_open_seats(players, slots, playing, [1]) \
            == {1: {"Center": 0, "Util": 1}}

    def test_util_used_when_unavoidable(self):
        slots = {"Center": 1, "Util": 1}
        players = [PreviewPlayer("A", "Boston Bruins", ["Center", "Util"]),
                   PreviewPlayer("B", "Boston Bruins", ["Center", "Util"])]
        playing = {1: {"Boston Bruins"}}
        assert position_open_seats(players, slots, playing, [1]) \
            == {1: {"Center": 0, "Util": 0}}

    def test_forward_filled_before_util(self):
        slots = {"Center": 1, "Forward": 1, "Util": 1}
        players = [PreviewPlayer("A", "Boston Bruins",
                                 ["Center", "Forward", "Util"]),
                   PreviewPlayer("B", "Boston Bruins",
                                 ["Center", "Forward", "Util"])]
        playing = {1: {"Boston Bruins"}}
        assert position_open_seats(players, slots, playing, [1]) \
            == {1: {"Center": 0, "Forward": 0, "Util": 1}}

    def test_augmenting_reassigns_flexible_player(self):
        # A must move from Center to Left Wing so B fits; no Util needed
        slots = {"Center": 1, "Left Wing": 1, "Util": 1}
        players = [PreviewPlayer("A", "Boston Bruins",
                                 ["Center", "Left Wing", "Util"]),
                   PreviewPlayer("B", "Boston Bruins", ["Center", "Util"])]
        playing = {1: {"Boston Bruins"}}
        assert position_open_seats(players, slots, playing, [1]) \
            == {1: {"Center": 0, "Left Wing": 0, "Util": 1}}

    def test_goalie_cannot_fill_util(self):
        slots = {"Goalie": 1, "Util": 1}
        players = [PreviewPlayer("G", "Boston Bruins", ["Goalie"]),
                   PreviewPlayer("H", "Boston Bruins", ["Goalie"])]
        playing = {1: {"Boston Bruins"}}
        assert position_open_seats(players, slots, playing, [1]) \
            == {1: {"Goalie": 0, "Util": 1}}

    def test_sums_match_total_open_seats(self):
        slots = {"Center": 2, "Defense": 2, "Goalie": 1, "Util": 1}
        players = [PreviewPlayer("A", "Boston Bruins", ["Center", "Util"]),
                   PreviewPlayer("B", "Boston Bruins", ["Defense", "Util"]),
                   PreviewPlayer("G", "Boston Bruins", ["Goalie"])]
        playing = {1: {"Boston Bruins"}}
        by_slot = position_open_seats(players, slots, playing, [1])[1]
        skater_open, goalie_open = open_seat_counts(
            players, slots, playing, [1])[1]
        assert sum(by_slot.values()) == skater_open + goalie_open
        assert by_slot["Goalie"] == goalie_open


class TestTeamGapCoverage:
    PLAYING = {
        1: {"Boston Bruins", "Dallas Stars"},
        2: {"Boston Bruins"},
        3: {"Dallas Stars", "Ottawa Senators"},
    }

    def test_cover_counts_only_open_days(self):
        table = team_gap_coverage(self.PLAYING, {2, 3}, [1, 2, 3])
        by_team = table.set_index("Team")
        assert by_team.loc["Boston Bruins", "Cover"] == 1  # plays day 2
        assert by_team.loc["Dallas Stars", "Cover"] == 1  # plays day 3
        assert by_team.loc["Ottawa Senators", "Cover"] == 1

    def test_games_counts_all_days(self):
        table = team_gap_coverage(self.PLAYING, {2, 3}, [1, 2, 3])
        by_team = table.set_index("Team")
        assert by_team.loc["Boston Bruins", "Games"] == 2
        assert by_team.loc["Ottawa Senators", "Games"] == 1

    def test_sorted_by_cover_then_games(self):
        table = team_gap_coverage(self.PLAYING, {1, 2, 3}, [1, 2, 3])
        assert list(table["Team"]) == ["Boston Bruins", "Dallas Stars",
                                       "Ottawa Senators"]

    def test_day_columns_are_play_flags(self):
        table = team_gap_coverage(self.PLAYING, {1}, [1, 2, 3])
        row = table.set_index("Team").loc["Boston Bruins"]
        assert bool(row[1]) and bool(row[2]) and not bool(row[3])

    def test_no_periods_gives_empty_table(self):
        table = team_gap_coverage(self.PLAYING, set(), [])
        assert table.empty


class TestOffNightPeriods:
    def test_threshold_is_inclusive(self):
        playing = {1: {"A", "B"}, 2: {"A", "B", "C"}, 3: {"A"}}
        assert off_night_periods(playing, max_teams=2) == {1, 3}

    def test_empty_night_is_not_an_off_night(self):
        assert off_night_periods({1: set()}, max_teams=2) == set()


class TestTeamWeekSchedule:
    PLAYING = {
        1: {"Boston Bruins", "Dallas Stars"},
        2: {"Boston Bruins"},
        3: {"Dallas Stars", "Ottawa Senators"},
        4: {"Ottawa Senators"},
    }
    WEEKS = {1: [1, 2], 2: [3, 4]}

    def test_games_per_week(self):
        games, _ = team_week_schedule(self.PLAYING, self.WEEKS, set())
        assert list(games.columns) == [1, 2]
        assert games.loc["Boston Bruins", 1] == 2
        assert games.loc["Boston Bruins", 2] == 0
        assert games.loc["Ottawa Senators", 2] == 2

    def test_off_nights_restricted_to_off_periods(self):
        _, off = team_week_schedule(self.PLAYING, self.WEEKS, {2, 4})
        assert off.loc["Boston Bruins", 1] == 1
        assert off.loc["Dallas Stars", 1] == 0
        assert off.loc["Ottawa Senators", 2] == 1

    def test_teams_sorted_and_periods_outside_weeks_ignored(self):
        games, _ = team_week_schedule(self.PLAYING, {1: [1]}, set())
        assert list(games.index) == ["Boston Bruins", "Dallas Stars"]


class TestScheduleSummary:
    GAMES = pd.DataFrame({1: [3, 2], 2: [1, 4]}, index=["A", "B"])
    OFF = pd.DataFrame({1: [2, 0], 2: [0, 1]}, index=["A", "B"])

    def test_totals_and_averages(self):
        table = schedule_summary(self.GAMES, self.OFF, set())
        row = table.set_index("Team").loc["A"]
        assert row["Games"] == 4
        assert row["G/M"] == pytest.approx(2.0)
        assert row["Off"] == 2
        assert row["Off/M"] == pytest.approx(1.0)

    def test_no_playoff_weeks_omits_po_columns_and_sorts_by_off_rate(self):
        table = schedule_summary(self.GAMES, self.OFF, set())
        assert "PO G" not in table.columns
        assert list(table["Team"]) == ["A", "B"]

    def test_playoff_columns_present_but_sort_stays_off_rate(self):
        table = schedule_summary(self.GAMES, self.OFF, {2})
        by_team = table.set_index("Team")
        assert by_team.loc["B", "PO G"] == 4
        assert by_team.loc["B", "PO Off"] == 1
        # A leads on Off/M (1.0 vs 0.5) regardless of playoff numbers
        assert list(table["Team"]) == ["A", "B"]

    def test_near_weeks_column_leads_sort(self):
        table = schedule_summary(self.GAMES, self.OFF, set(), near_weeks=[2])
        by_team = table.set_index("Team")
        assert by_team.loc["B", "G/M next 1"] == pytest.approx(4.0)
        assert by_team.loc["B", "Off/M next 1"] == pytest.approx(1.0)
        assert by_team.loc["A", "Off/M next 1"] == pytest.approx(0.0)
        # B leads near-term despite fewer total off-nights
        assert list(table["Team"]) == ["B", "A"]

    def test_score_columns_follow_team_and_lead_sort(self):
        scores = {"Fit": pd.Series({"A": 1.0, "B": 2.0}),
                  "Score": pd.Series({"A": 3.0, "B": 1.0})}
        table = schedule_summary(self.GAMES, self.OFF, set(), scores=scores)
        assert list(table.columns[:3]) == ["Team", "Fit", "Score"]
        # Fit leads the sort: B (2.0) over A (1.0) despite A's Off/M lead
        assert list(table["Team"]) == ["B", "A"]


class TestCalibrateNightValue:
    SLOTS = {"Center": 1}

    def test_mean_capped_seats_by_teams_playing(self):
        rosters = [[PreviewPlayer("A", "Boston Bruins", ["Center"])],
                   [PreviewPlayer("B", "Utah HC", ["Center"])]]
        playing = {1: {"Boston Bruins"}, 2: {"Dallas Stars",
                                             "Ottawa Senators"}}
        curve = calibrate_night_value(rosters, self.SLOTS, playing)
        # night 1: A plays (0 seats), B idle (1 seat) -> mean 0.5
        assert curve[1] == pytest.approx(0.5)
        # night 2: neither roster plays -> 1 open seat each
        assert curve[2] == pytest.approx(1.0)

    def test_seats_capped(self):
        rosters = [[PreviewPlayer("A", "Boston Bruins", ["Center"])]]
        slots = {"Center": 10}
        playing = {1: {"Dallas Stars"}}
        curve = calibrate_night_value(rosters, slots, playing)
        assert curve[1] == pytest.approx(SEAT_CAP)

    def test_empty_nights_ignored(self):
        rosters = [[PreviewPlayer("A", "Boston Bruins", ["Center"])]]
        curve = calibrate_night_value(rosters, self.SLOTS,
                                      {1: set(), 2: {"Boston Bruins"}})
        assert set(curve) == {1}


class TestNightSeatCurve:
    def test_interpolates_between_observed_points(self):
        fn = night_seat_curve({2: 2.0, 4: 1.0})
        assert fn(3) == pytest.approx(1.5)

    def test_clips_at_curve_ends(self):
        fn = night_seat_curve({2: 2.0, 4: 1.0})
        assert fn(1) == pytest.approx(2.0)
        assert fn(10) == pytest.approx(1.0)

    def test_linear_fallback_when_uncalibrated(self):
        fn = night_seat_curve(None)
        assert fn(16) == pytest.approx(1.5)
        assert fn(4) == pytest.approx(2.625)
        assert fn(32) == pytest.approx(0.0)


class TestEffectiveGames:
    def test_streamable_night_counts_more(self):
        playing = {1: {"A"}, 2: {"A", "B"}}
        weeks = {1: [1, 2]}
        seats = {1: 3.0, 2: 0.0}
        eff = effective_games(playing, weeks, seats)
        # A: full-bonus night (2.0) + plain night (1.0); B: plain night
        assert eff["A"] == pytest.approx(3.0)
        assert eff["B"] == pytest.approx(1.0)

    def test_averaged_per_matchup(self):
        playing = {1: {"A"}, 2: {"A"}}
        weeks = {1: [1], 2: [2]}
        eff = effective_games(playing, weeks, {1: 0.0, 2: 0.0})
        assert eff["A"] == pytest.approx(1.0)

    def test_seat_bonus_capped(self):
        playing = {1: {"A"}}
        eff = effective_games(playing, {1: [1]}, {1: 99.0})
        assert eff["A"] == pytest.approx(2.0)


class TestRankStreamingCandidates:
    SLOTS = {"Center": 1, "Util": 1, "Goalie": 1}
    KEEP = [PreviewPlayer("Mine", "Boston Bruins", ["Center", "Util"])]

    def test_fit_when_open_seat_matches(self):
        playing = {1: {"Boston Bruins", "Dallas Stars"}}
        cand = PreviewPlayer("FA", "Dallas Stars", ["Center", "Util"])
        table = rank_streaming_candidates([cand], self.KEEP, self.SLOTS,
                                          playing, [1])
        row = table.iloc[0]
        assert row[1] == "fit" and row["Fit"] == 1 and row["Games"] == 1

    def test_play_but_no_fit_when_seats_taken(self):
        slots = {"Center": 1}
        playing = {1: {"Boston Bruins", "Dallas Stars"}}
        keep = [PreviewPlayer("Mine", "Boston Bruins", ["Center"])]
        cand = PreviewPlayer("FA", "Dallas Stars", ["Center"])
        table = rank_streaming_candidates([cand], keep, slots, playing, [1])
        row = table.iloc[0]
        assert row[1] == "play" and row["Fit"] == 0 and row["Games"] == 1

    def test_no_game_day_is_empty(self):
        playing = {1: {"Boston Bruins"}}
        cand = PreviewPlayer("FA", "Dallas Stars", ["Center"])
        table = rank_streaming_candidates([cand], self.KEEP, self.SLOTS,
                                          playing, [1])
        row = table.iloc[0]
        assert row[1] == "" and row["Fit"] == 0 and row["Games"] == 0

    def test_open_goalie_seat_does_not_fit_skater(self):
        slots = {"Center": 1, "Goalie": 1}
        playing = {1: {"Boston Bruins", "Dallas Stars"}}
        keep = [PreviewPlayer("Mine", "Boston Bruins", ["Center"])]
        cand = PreviewPlayer("FA", "Dallas Stars", ["Center"])
        table = rank_streaming_candidates([cand], keep, slots, playing, [1])
        assert table.iloc[0]["Fit"] == 0

    def test_goalie_candidate_never_fits_skater_seats(self):
        playing = {1: {"Boston Bruins", "Dallas Stars"}}
        cand = PreviewPlayer("FA G", "Dallas Stars", ["Goalie"])
        table = rank_streaming_candidates([cand], self.KEEP, self.SLOTS,
                                          playing, [1])
        row = table.iloc[0]
        assert row["Fit"] == 0 and row[1] == "play"

    def test_sorted_by_fit_then_input_order(self):
        playing = {2: {"Dallas Stars", "Ottawa Senators"},
                   3: {"Ottawa Senators"}}
        two_fits = PreviewPlayer("Two", "Ottawa Senators", ["Center"])
        one_fit = PreviewPlayer("First", "Dallas Stars", ["Center", "Util"])
        # same fit and games as First, but listed later (less owned)
        tied_later = PreviewPlayer("Later", "Dallas Stars", ["Center"])
        keep = [PreviewPlayer("Mine", "Boston Bruins", ["Center", "Util"])]
        slots = {"Center": 1, "Util": 1}
        table = rank_streaming_candidates(
            [one_fit, tied_later, two_fits], keep, slots, playing, [2, 3])
        assert list(table["Player"]) == ["Two", "First", "Later"]

    def test_games_break_fit_ties(self):
        slots = {"Center": 1}
        keep = [PreviewPlayer("Mine", "Boston Bruins", ["Center"])]
        # day 1 seat open, day 2 seat taken by Mine
        playing = {1: {"Dallas Stars", "Ottawa Senators"},
                   2: {"Boston Bruins", "Dallas Stars"}}
        one_game = PreviewPlayer("OneGame", "Ottawa Senators", ["Center"])
        two_games = PreviewPlayer("TwoGames", "Dallas Stars", ["Center"])
        table = rank_streaming_candidates([one_game, two_games], keep, slots,
                                          playing, [1, 2])
        assert list(table["Player"]) == ["TwoGames", "OneGame"]
        assert list(table["Fit"]) == [1, 1]
        assert list(table["Games"]) == [2, 1]

    def test_injury_and_slots_passed_through(self):
        cand = PreviewPlayer("FA", "Dallas Stars", ["Center", "Util"],
                             injury="DAY_TO_DAY")
        table = rank_streaming_candidates([cand], self.KEEP, self.SLOTS,
                                          {1: set()}, [1])
        row = table.iloc[0]
        assert row["Injury"] == "DAY_TO_DAY"
        assert row["Slots"] == ["Center", "Util"]

    def test_empty_candidates(self):
        table = rank_streaming_candidates([], self.KEEP, self.SLOTS,
                                          {1: set()}, [1])
        assert table.empty


def _pick(team_row, rnd, pick, n_teams=2, **kw):
    overall = (rnd - 1) * n_teams + pick
    defaults = dict(player_id=overall, name=f"P{overall}", position="Center",
                    eligible_slots=["Center", "Util"])
    defaults.update(kw)
    return DraftPick(team_row, rnd, pick, overall, **defaults)


class TestDraftPickTable:
    TEAMS = ["Alpha", "Beta"]

    def test_value_sign_and_rounds(self):
        # Alpha takes a player with ADP 5 at pick 1 (reach), Beta an ADP-1
        # player at pick 2 (steal); 2 teams -> a round is 2 picks
        picks = [_pick(0, 1, 1, adp=5.0), _pick(1, 1, 2, adp=1.0)]
        table = draft_pick_table(picks, self.TEAMS, n_teams=2)
        assert list(table["Value"]) == [4.0, -1.0]
        assert list(table["ValueRd"]) == [2.0, -0.5]
        assert list(table["Team"]) == ["Alpha", "Beta"]
        assert not table["ADP?"].any()

    def test_missing_adp_floored_after_last_pick(self):
        picks = [_pick(0, 1, 1, adp=1.0), _pick(1, 1, 2, adp=None),
                 _pick(1, 2, 1, adp=0.0), _pick(0, 2, 2, adp=3.0)]
        table = draft_pick_table(picks, self.TEAMS, n_teams=2)
        assert list(table["ADP"]) == [1.0, 5.0, 5.0, 3.0]
        assert list(table["ADP?"]) == [False, True, True, False]
        assert list(table["Value"]) == [0.0, 3.0, 2.0, -1.0]

    def test_now_on_maps_roster_row(self):
        picks = [_pick(0, 1, 1, adp=1.0, rostered_by=1),
                 _pick(1, 1, 2, adp=2.0, rostered_by=None)]
        table = draft_pick_table(picks, self.TEAMS, n_teams=2)
        assert list(table["NowOn"]) == ["Beta", None]

    def test_empty_draft(self):
        table = draft_pick_table([], self.TEAMS, n_teams=2)
        assert table.empty
        assert "Value" in table.columns


class TestDraftTeamSummary:
    TEAMS = ["Alpha", "Beta"]

    def picks(self):
        return [
            _pick(0, 1, 1, adp=3.0, rostered_by=0),  # +2
            _pick(1, 1, 2, adp=1.0, rostered_by=1, position="Goalie",
                  eligible_slots=["Goalie"]),  # -1
            _pick(1, 2, 1, adp=9.0, rostered_by=0, position="Defense"),  # +6
            _pick(0, 2, 2, adp=1.0, rostered_by=None, position="Goalie"),  # -3
        ]

    def test_values_and_extremes(self):
        table = draft_pick_table(self.picks(), self.TEAMS, n_teams=2)
        summary = draft_team_summary(table)
        assert list(summary.index) == [0, 1]
        assert list(summary["Player"]) == ["Alpha", "Beta"]
        assert list(summary["Avg value"]) == [-0.5, 2.5]
        assert list(summary["Total"]) == [-1.0, 5.0]
        assert summary.loc[0, "Best steal"] == "P1 (+2)"
        assert summary.loc[0, "Biggest reach"] == "P4 (-3)"
        assert summary.loc[1, "Best steal"] == "P3 (+6)"

    def test_positions_and_retention(self):
        table = draft_pick_table(self.picks(), self.TEAMS, n_teams=2)
        summary = draft_team_summary(table)
        assert list(summary["G"]) == [1, 1]
        assert list(summary["1st G"]) == [2, 1]
        assert list(summary["D"]) == [0, 1]
        # Alpha kept P1 (lost P4 to FA); Beta kept its goalie, P3 moved to Alpha
        assert list(summary["Kept"]) == [1, 1]
        assert list(summary["Picks"]) == [2, 2]

    def test_no_goalies(self):
        picks = [_pick(0, 1, 1, adp=1.0)]
        summary = draft_team_summary(
            draft_pick_table(picks, self.TEAMS, n_teams=2))
        assert summary.loc[0, "G"] == 0
        assert pd.isna(summary.loc[0, "1st G"])


class TestDraftValueGridAndExtremes:
    TEAMS = ["Alpha", "Beta"]

    def test_grid_shape_and_values(self):
        picks = [_pick(0, 1, 1, adp=3.0), _pick(1, 1, 2, adp=1.0),
                 _pick(1, 2, 1, adp=9.0), _pick(0, 2, 2, adp=1.0)]
        grid = draft_value_grid(draft_pick_table(picks, self.TEAMS, 2))
        assert list(grid.index) == ["Alpha", "Beta"]
        assert list(grid.columns) == ["R1", "R2"]
        assert grid.loc["Alpha"].tolist() == [2.0, -3.0]
        assert grid.loc["Beta"].tolist() == [-1.0, 6.0]

    def test_extremes(self):
        picks = [_pick(0, 1, 1, adp=3.0), _pick(1, 1, 2, adp=1.0),
                 _pick(1, 2, 1, adp=9.0), _pick(0, 2, 2, adp=1.0)]
        steals, reaches = draft_extremes(
            draft_pick_table(picks, self.TEAMS, 2), 2)
        assert list(steals["Player"]) == ["P3", "P1"]
        assert list(reaches["Player"]) == ["P4", "P2"]

    def test_extremes_ties_keep_draft_order_and_exact_n(self):
        # all four picks have Value 0: exactly n rows, earliest picks first
        picks = [_pick(0, 1, 1, adp=1.0), _pick(1, 1, 2, adp=2.0),
                 _pick(1, 2, 1, adp=3.0), _pick(0, 2, 2, adp=4.0)]
        steals, reaches = draft_extremes(
            draft_pick_table(picks, self.TEAMS, 2), 2)
        assert list(steals["Player"]) == ["P1", "P2"]
        assert list(reaches["Player"]) == ["P1", "P2"]

    def test_grid_sums_two_picks_in_one_round(self):
        picks = [_pick(0, 1, 1, adp=3.0), _pick(0, 1, 2, adp=6.0),
                 _pick(1, 2, 1, adp=3.0)]
        grid = draft_value_grid(draft_pick_table(picks, self.TEAMS, 2))
        assert grid.loc["Alpha", "R1"] == 2.0 + 4.0
        assert pd.isna(grid.loc["Alpha", "R2"])


class TestProjectedCategoryBalance:
    CATS = [Category("G"), Category("GAA", inverted=True), Category("SV%")]

    @staticmethod
    def goalie(name, gaa, gs):
        return PreviewPlayer(name, "", ["Goalie"],
                             projected_stats={"GAA": gaa, "GS": gs, "SV%": 0.9})

    def test_totals_and_z_scores(self):
        rosters = [
            [PreviewPlayer("A1", "", ["Center"], projected_stats={"G": 30}),
             PreviewPlayer("A2", "", ["Center"], projected_stats={"G": 10})],
            [PreviewPlayer("B1", "", ["Center"], projected_stats={"G": 20})],
        ]
        z, totals = projected_category_balance(rosters, [Category("G")],
                                               ["Alpha", "Beta"])
        assert totals["G"].tolist() == [40.0, 20.0]
        assert z["G"].tolist() == [1.0, -1.0]

    def test_ratio_weighted_by_starts_and_inverted_flip(self):
        rosters = [
            [self.goalie("A", 2.0, 60), self.goalie("A2", 4.0, 20)],  # 2.5
            [self.goalie("B", 3.5, 50)],
        ]
        z, totals = projected_category_balance(rosters, self.CATS,
                                               ["Alpha", "Beta"])
        assert totals["GAA"].tolist() == pytest.approx([2.5, 3.5])
        # lower GAA is better -> Alpha positive
        assert z.loc["Alpha", "GAA"] == pytest.approx(1.0)
        assert z.loc["Beta", "GAA"] == pytest.approx(-1.0)

    def test_constant_category_and_no_goalies(self):
        rosters = [
            [PreviewPlayer("A", "", ["Center"], projected_stats={"G": 5})],
            [PreviewPlayer("B", "", ["Center"], projected_stats={"G": 5}),
             self.goalie("BG", 3.0, 40)],
        ]
        z, totals = projected_category_balance(rosters, self.CATS,
                                               ["Alpha", "Beta"])
        assert z["G"].tolist() == [0.0, 0.0]
        assert pd.isna(totals.loc["Alpha", "GAA"])
        assert pd.isna(z.loc["Alpha", "GAA"])
        assert z.loc["Beta", "GAA"] == 0.0

    def test_blended_pace_full_weight_uses_season_rate(self):
        # 0.5 G/game this season vs 0.25 projected, over 80 projected games
        hot = PreviewPlayer("Hot", "", ["Center"],
                            season_stats={"G": 20, "GP": 40},
                            projected_stats={"G": 20, "GP": 80})
        cold = PreviewPlayer("Cold", "", ["Center"],
                             season_stats={"G": 5, "GP": 40},
                             projected_stats={"G": 20, "GP": 80})
        rosters = [[hot], [cold]]
        _, projected = projected_category_balance(rosters, [Category("G")],
                                                  ["A", "B"], 0.0)
        assert projected["G"].tolist() == [20.0, 20.0]
        _, pace = projected_category_balance(rosters, [Category("G")],
                                             ["A", "B"], 1.0)
        assert pace["G"].tolist() == [40.0, 10.0]
        _, half = projected_category_balance(rosters, [Category("G")],
                                             ["A", "B"], 0.5)
        assert half["G"].tolist() == pytest.approx([30.0, 15.0])

    def test_blended_pace_small_sample_stays_on_projections(self):
        fluke = PreviewPlayer("Fluke", "", ["Center"],
                              season_stats={"G": 3, "GP": 3},  # 1 G/game
                              projected_stats={"G": 10, "GP": 80})
        _, pace = projected_category_balance([[fluke]], [Category("G")],
                                             ["A"], 1.0)
        assert pace.loc["A", "G"] == 10.0
        # a quarter in he only needs 5 games: still too few
        _, pace = projected_category_balance([[fluke]], [Category("G")],
                                             ["A"], 0.25)
        assert pace.loc["A", "G"] == 10.0

    def test_blended_pace_without_projection_uses_season_games(self):
        callup = PreviewPlayer("Callup", "", ["Center"],
                               season_stats={"G": 10, "GP": 25})
        _, pace = projected_category_balance([[callup]], [Category("G")],
                                             ["A"], 1.0)
        assert pace.loc["A", "G"] == 10.0

    def test_blended_pace_ratio(self):
        goalie = PreviewPlayer("G", "", ["Goalie"],
                               season_stats={"GAA": 2.0, "GS": 30},
                               projected_stats={"GAA": 3.0, "GS": 60})
        _, pace = projected_category_balance(
            [[goalie]], [Category("GAA", inverted=True)], ["A"], 0.5)
        assert pace.loc["A", "GAA"] == pytest.approx(2.5)

    REPLACEMENT = {"F": {"G": 0.2}, "D": {"G": 0.1}, "G": {"GAA": 3.0}}

    def test_replacement_fills_missing_games(self):
        half = PreviewPlayer("Half", "", ["Center"],
                             projected_stats={"G": 10, "GP": 41})
        unprojected = PreviewPlayer("Rookie", "", ["Defense"])
        full = PreviewPlayer("Full", "", ["Center"],
                             projected_stats={"G": 30, "GP": FULL_SEASON_GP})
        _, pace = projected_category_balance(
            [[half], [unprojected], [full]], [Category("G")], ["A", "B", "C"],
            replacement=self.REPLACEMENT)
        assert pace["G"].tolist() == pytest.approx(
            [10 + 0.2 * 41, 0.1 * FULL_SEASON_GP, 30.0])

    def test_replacement_fill_on_blended_pace(self):
        # 0.5 G/game over 41 projected games, the other 41 at 0.2
        hot = PreviewPlayer("Hot", "", ["Center"],
                            season_stats={"G": 20, "GP": 40},
                            projected_stats={"G": 5, "GP": 41})
        _, pace = projected_category_balance(
            [[hot]], [Category("G")], ["A"], 1.0, replacement=self.REPLACEMENT)
        assert pace.loc["A", "G"] == pytest.approx(0.5 * 41 + 0.2 * 41)

    def test_replacement_fill_ratio_weighted_by_missing_starts(self):
        goalie = self.goalie("G", 2.0, FULL_SEASON_GS // 2)
        _, pace = projected_category_balance(
            [[goalie]], self.CATS, ["A"], replacement=self.REPLACEMENT)
        assert pace.loc["A", "GAA"] == pytest.approx(2.5)
        # a roster without a goalie counts one replacement goalie
        _, pace = projected_category_balance(
            [[PreviewPlayer("S", "", ["Center"])]], self.CATS, ["A"],
            replacement=self.REPLACEMENT)
        assert pace.loc["A", "GAA"] == pytest.approx(3.0)
        _, pace = projected_category_balance(
            [[PreviewPlayer("S", "", ["Center"])]], self.CATS, ["A"])
        assert pd.isna(pace.loc["A", "GAA"])


class TestReplacementRates:
    CATS = [Category("G"), Category("GAA", inverted=True)]

    def test_median_per_group_and_category(self):
        players = [_skater(1, "F1", 10, gp=50), _skater(2, "F2", 20, gp=50),
                   _skater(3, "F3", 40, gp=50),
                   _skater(4, "D1", 5, gp=50, eligible_slots=["Defense"]),
                   _goalie(5, "G1", 2.0), _goalie(6, "G2", 4.0)]
        rates = replacement_rates(players, self.CATS, blend_weight=1.0)
        assert rates["F"] == {"G": pytest.approx(0.4)}
        assert rates["D"] == {"G": pytest.approx(0.1)}
        assert rates["G"] == {"GAA": pytest.approx(3.0)}

    def test_players_without_rate_skipped_and_empty_groups(self):
        players = [_skater(1, "F1", 10, gp=50),
                   _skater(2, "None", 0, gp=0, season_stats={})]
        rates = replacement_rates(players, self.CATS, blend_weight=1.0)
        assert rates["F"] == {"G": pytest.approx(0.2)}
        assert rates["D"] == {} and rates["G"] == {}


class TestCategoryOutlook:
    CATS = [Category("G"), Category("A"), Category("GAA", inverted=True)]

    def test_round_robin_points_and_balance(self):
        totals = pd.DataFrame(
            {"G": [30.0, 20.0, 10.0], "A": [10.0, 20.0, 30.0],
             "GAA": [2.0, 3.0, 3.0]},
            index=pd.Index(["Alpha", "Beta", "Gamma"], name="Team"))
        z = pd.DataFrame(
            {"G": [1.0, 0.0, -1.0], "A": [-1.0, 0.0, 1.0],
             "GAA": [1.0, -1.0, -1.0]}, index=totals.index)
        table = category_outlook(z, totals, self.CATS)
        assert list(table.index) == ["Alpha", "Beta", "Gamma"]
        # Alpha beats both (G + GAA vs Beta; G + GAA vs Gamma) = 4 pts;
        # Beta: loses to Alpha, vs Gamma wins G, loses A, ties GAA -> tie
        assert table["RR Pts"].tolist() == [4, 1, 1]
        assert table["Cats/M"].tolist() == pytest.approx([2.0, 1.0, 1.0])
        assert table.loc["Beta", "Spread"] == pytest.approx(
            np.std([0.0, 0.0, -1.0]))
        assert table["Punts"].tolist() == [1, 1, 2]

    def test_punt_threshold_inclusive(self):
        index = pd.Index(["A", "B"], name="Team")
        z = pd.DataFrame({"G": [PUNT_Z, -PUNT_Z]}, index=index)
        totals = pd.DataFrame({"G": [1.0, 2.0]}, index=index)
        table = category_outlook(z, totals, [Category("G")])
        assert table["Punts"].tolist() == [1, 0]
        assert table["RR Pts"].tolist() == [0, 2]
        assert table["Spread"].tolist() == [0.0, 0.0]


class TestDraftedRosters:
    def test_groups_by_team_with_projections(self):
        picks = [_pick(1, 1, 1, projected_stats={"G": 30}),
                 _pick(0, 1, 2, eligible_slots=["Goalie"], position="Goalie")]
        rosters = drafted_rosters(picks, n_teams=3)
        assert [len(r) for r in rosters] == [1, 1, 0]
        assert rosters[1][0].projected_stats == {"G": 30}
        assert rosters[0][0].eligible_slots == ["Goalie"]
        assert rosters[1][0].player_id == 1
        assert rosters[0][0].team_row == 0
        assert rosters[0][0].position == "Goalie"


GP = MIN_SCORE_GAMES + 5  # enough games for a Score at any blend weight


def _skater(pid, name, g, gp=GP, **kw):
    defaults = dict(position="Center", eligible_slots=["Center", "Util"],
                    season_stats={"G": g, "GP": gp})
    defaults.update(kw)
    return RosterPlayer(name, "", defaults.pop("eligible_slots"),
                        player_id=pid, **defaults)


def _goalie(pid, name, gaa, gs=GP, **kw):
    return RosterPlayer(name, "", ["Goalie"], player_id=pid, position="Goalie",
                        season_stats={"GAA": gaa, "GS": gs}, **kw)


REVIEW_CATS = [Category("G"), Category("GAA", inverted=True)]
# normal quantile of the 75th percentile: the score of the better of two
HALF = NormalDist().inv_cdf(0.75)


class TestPlayerValueScores:
    def test_skaters_and_goalies_scored_within_their_group(self):
        players = [_skater(1, "Hi", 10), _skater(2, "Lo", 0),
                   _goalie(3, "Wall", 2.0), _goalie(4, "Sieve", 4.0)]
        scores = player_value_scores(players, REVIEW_CATS, blend_weight=1.0)
        assert scores[0] == pytest.approx(HALF)
        assert scores[1] == pytest.approx(-HALF)
        # lower GAA is better -> inverted flip
        assert scores[2] == pytest.approx(HALF)
        assert scores[3] == pytest.approx(-HALF)

    def test_no_games_gives_none_and_constant_gives_zero(self):
        players = [_skater(1, "A", 5), _skater(2, "B", 5),
                   _skater(3, "Nope", 0, gp=0)]
        scores = player_value_scores(players, REVIEW_CATS, blend_weight=1.0)
        assert scores[0] == pytest.approx(0.0) and scores[1] == pytest.approx(0.0)
        assert scores[2] is None

    def test_defensemen_scored_among_defensemen(self):
        # a D-only category would otherwise hand every D a free bonus
        cats = [Category("G"), Category("DEF")]
        forwards = [_skater(1, "F1", 10, season_stats={"G": 10, "GP": GP}),
                    _skater(2, "F2", 0, season_stats={"G": 0, "GP": GP})]
        dmen = [_skater(3, "D1", 0, eligible_slots=["Defense"],
                        season_stats={"G": 2, "DEF": 4, "GP": GP}),
                _skater(4, "D2", 0, eligible_slots=["Defense"],
                        season_stats={"G": 0, "DEF": 0, "GP": GP})]
        scores = player_value_scores(forwards + dmen, cats, 1.0)
        # forwards: DEF constant (0) -> 0; G decides
        assert scores[0] == pytest.approx(HALF / 2)
        assert scores[1] == pytest.approx(-HALF / 2)
        # defensemen: both cats favour D1, symmetric within the D group
        assert scores[2] == pytest.approx(HALF)
        assert scores[3] == pytest.approx(-HALF)

    def test_rank_based_caps_runaway_category(self):
        # 100 goals/game ranks the same as 11: only the order counts
        cats = [Category("G")]
        players = [_skater(1, "Runaway", 1000), _skater(2, "Good", 10),
                   _skater(3, "Meh", 5)]
        capped = player_value_scores(players, cats, 1.0)
        players[0].season_stats["G"] = 11
        modest = player_value_scores(players, cats, 1.0)
        assert capped == pytest.approx(modest)
        assert capped[0] > capped[1] > capped[2]
        assert capped[1] == pytest.approx(0.0)  # median

    def test_projection_fallback_only_before_the_season(self):
        rookie = _skater(1, "Rookie", 0, gp=0,
                         projected_stats={"G": 20, "GP": 10})
        vet = _skater(2, "Vet", 10, projected_stats={"G": 5, "GP": 10})
        # preseason: nobody has games, projections rank everyone
        scores = player_value_scores([rookie, vet], REVIEW_CATS, 0.0)
        assert scores[0] == pytest.approx(HALF)
        assert scores[1] == pytest.approx(-HALF)
        # season over: no games -> no Score, however good the projection
        scores = player_value_scores([rookie, vet], REVIEW_CATS, 1.0)
        assert scores[0] is None
        assert scores[1] == pytest.approx(0.0)  # alone in his group

    def test_min_games_scales_with_season_fraction(self):
        assert min_season_games(0.0) == 0
        assert min_season_games(0.1) == math.ceil(MIN_SCORE_GAMES * 0.1)
        assert min_season_games(1.0) == MIN_SCORE_GAMES
        few = _skater(1, "Few", 3, gp=MIN_SCORE_GAMES - 1)
        enough = _skater(2, "Enough", 3, gp=MIN_SCORE_GAMES)
        scores = player_value_scores([few, enough], REVIEW_CATS, 1.0)
        assert scores[0] is None and scores[1] is not None
        # a quarter into the season the same player has played enough
        scores = player_value_scores([few, enough], REVIEW_CATS, 0.25)
        assert None not in scores

    def test_goalie_placeholder_ratio_without_starts_ignored(self):
        # ESPN reports GAA 0.0 for a goalie who has not started: must not
        # rank him as the best goalie
        bench = _goalie(1, "Bench", 0.0, gs=0)
        good = _goalie(2, "Good", 2.5)
        bad = _goalie(3, "Bad", 3.5)
        scores = player_value_scores([bench, good, bad], REVIEW_CATS, 1.0)
        assert scores[0] is None
        assert scores[1] > scores[2]

    def test_empty(self):
        assert player_value_scores([], REVIEW_CATS, 0.5) == []


class TestPercentileRanks:
    def test_ties_and_missing(self):
        assert percentile_ranks([1, 3, 2]) == [
            pytest.approx(100 / 3), 100.0, pytest.approx(200 / 3)]
        assert percentile_ranks([1, 1, None]) == [75.0, 75.0, None]
        assert percentile_ranks([]) == []


class TestPlayerValues:
    def test_gap_sign(self):
        # Crowd darling with weak stats vs unknown with strong stats
        pool = [_skater(1, "Hype", 0, pct_owned=90.0),
                _skater(2, "Gem", 10, pct_owned=10.0)]
        values = player_values(pool, REVIEW_CATS, 1.0)
        assert list(values.index) == [1, 2]
        assert values.loc[1, "Gap"] > 0 > values.loc[2, "Gap"]
        assert values.loc[2, "ScorePct"] == 100.0

    def test_percentiles_within_position_group(self):
        pool = [_skater(1, "F", 10, pct_owned=50.0),
                _skater(2, "D", 1, pct_owned=99.0, eligible_slots=["Defense"]),
                _goalie(3, "G", 3.0, pct_owned=1.0)]
        values = player_values(pool, REVIEW_CATS, 1.0)
        assert list(values["Group"]) == ["F", "D", "G"]
        # alone in its group: every percentile is 100, Gap 0
        assert list(values["ScorePct"]) == [100.0] * 3
        assert list(values["OwnPct"]) == [100.0] * 3
        assert list(values["Gap"]) == [0.0] * 3


class TestRosterReviewTables:
    TEAMS = ["Alpha", "Beta"]

    def rosters(self):
        alpha = [_skater(1, "A1", 10, acquisition="DRAFT", team_row=0,
                         lineup_slot="Center", pct_owned=95.0),
                 _skater(2, "A2", 4, acquisition="ADD", team_row=0,
                         lineup_slot="IR", pct_owned=45.0, injury="OUT"),
                 _goalie(3, "AG", 2.5, acquisition="TRADE", team_row=0,
                         lineup_slot="Goalie", pct_owned=80.0)]
        beta = [_skater(4, "B1", 6, acquisition="ADD", team_row=1,
                        lineup_slot="Bench", pct_owned=60.0),
                _skater(5, "B2", 2, acquisition="DRAFT", team_row=1,
                        lineup_slot="Util", pct_owned=20.0)]
        return [alpha, beta]

    def values(self, rosters, extra=()):
        pool = [p for r in rosters for p in r] + list(extra)
        return player_values(pool, REVIEW_CATS, 1.0)

    def test_player_table_columns(self):
        rosters = self.rosters()
        table = player_table(rosters[0], self.values(rosters), self.TEAMS)
        assert list(table["Player"]) == ["A1", "A2", "AG"]
        assert list(table["Team"]) == ["Alpha"] * 3
        assert list(table["GP"]) == [GP, GP, GP]
        assert table.loc[1, "Injury"] == "OUT"
        assert table["Score"].dtype == float
        fa = _skater(9, "FA", 1)
        assert player_table([fa], self.values(rosters), self.TEAMS)\
            .loc[0, "Team"] == "FA"

    def test_roster_origins(self):
        rosters = self.rosters()
        counters = [TransactionCounts(10, 9, 1), TransactionCounts(3, 3, 0)]
        table = roster_origins(rosters, self.values(rosters), self.TEAMS,
                               counters)
        alpha, beta = table.loc[0], table.loc[1]
        assert (alpha["Size"], alpha["Drafted"], alpha["Added"],
                alpha["Traded"], alpha["IR"]) == (3, 1, 1, 1, 1)
        assert (beta["Size"], beta["Drafted"], beta["Added"],
                beta["Traded"], beta["IR"]) == (2, 1, 1, 0, 0)
        assert alpha["Avg Own%"] == pytest.approx((95 + 45 + 80) / 3)
        assert (alpha["Adds"], alpha["Drops"], alpha["Trades"]) == (10, 9, 1)
        assert list(table["Player"]) == self.TEAMS

    def test_draft_return_sign(self):
        rosters = self.rosters()
        values = self.values(rosters)
        # A1 taken first and is the best skater: little gain; B2 taken last
        # and is the worst: also small; A2 (2nd pick) mediocre -> negative
        picks = [
            DraftPick(0, 1, 1, 1, 1, "A1", "Center", pct_owned=95.0, rostered_by=0),
            DraftPick(0, 1, 2, 2, 2, "A2", "Center", pct_owned=45.0, rostered_by=0),
            DraftPick(1, 2, 1, 3, 5, "B2", "Center", pct_owned=20.0, rostered_by=1),
            DraftPick(1, 2, 2, 4, 4, "B1", "Center", pct_owned=60.0, rostered_by=None),
        ]
        pool = {p.player_id: p for r in rosters for p in r}
        table = draft_return(picks, values, self.TEAMS, pool)
        by = table.set_index("Player")
        # skater ScorePct: A1 100, B1 75, A2 50, B2 25; slot pct 100/75/50/25
        assert by.loc["A1", "Return"] == pytest.approx(0.0)
        assert by.loc["A2", "Return"] == pytest.approx(-25.0)
        assert by.loc["B2", "Return"] == pytest.approx(-25.0)
        assert by.loc["B1", "Return"] == pytest.approx(50.0)
        assert by.loc["B1", "NowOn"] is None
        assert by.loc["A1", "GP"] == GP
        assert list(table["Overall"]) == [1, 2, 3, 4]

    def test_draft_return_unplayed_pick_is_a_full_bust(self):
        rosters = self.rosters()
        ghost = _skater(9, "Ghost", 0, gp=0, team_row=0, pct_owned=90.0)
        values = self.values([rosters[0] + [ghost], rosters[1]])
        picks = [DraftPick(0, 1, 1, 1, 9, "Ghost", "Center", rostered_by=0),
                 DraftPick(1, 1, 2, 2, 4, "B1", "Center", rostered_by=1)]
        table = draft_return(picks, values, self.TEAMS,
                             {9: ghost}).set_index("Player")
        # no Score (0 GP) but in the pool -> 0th percentile minus slot 100
        assert pd.isna(table.loc["Ghost", "Score"])
        assert table.loc["Ghost", "Return"] == pytest.approx(-100.0)
        assert table.loc["Ghost", "GP"] == 0

    def test_draft_return_ignores_roster_pct(self):
        rosters = self.rosters()
        for player in rosters[0] + rosters[1]:
            player.pct_owned = 100.0 - player.pct_owned  # invert the crowd
        values = self.values(rosters)
        picks = [DraftPick(0, 1, 1, 1, 1, "A1", "Center", pct_owned=5.0),
                 DraftPick(1, 1, 2, 2, 4, "B1", "Center", pct_owned=40.0)]
        table = draft_return(picks, values, self.TEAMS).set_index("Player")
        assert table.loc["A1", "Return"] == pytest.approx(0.0)
        assert table.loc["B1", "Return"] == pytest.approx(25.0)
        assert table.loc["A1", "Own%"] == 5.0  # informational only

    def test_draft_return_unknown_player(self):
        rosters = self.rosters()
        picks = [DraftPick(0, 1, 1, 1, 99, "Ghost", "Center")]
        table = draft_return(picks, self.values(rosters), self.TEAMS)
        assert pd.isna(table.loc[0, "Return"])
        assert pd.isna(table.loc[0, "Score"])
        assert pd.isna(table.loc[0, "GP"])

    def test_acquisition_summary_groups_by_team_row(self):
        rosters = self.rosters()
        same_names = ["Twins", "Twins"]
        summary, players = acquisition_summary(
            rosters, self.values(rosters), same_names, "ADD")
        assert list(summary["Count"]) == [1, 1]
        assert list(players["TeamRow"]) == [1, 0]

    def test_acquisition_summary(self):
        rosters = self.rosters()
        summary, players = acquisition_summary(
            rosters, self.values(rosters), self.TEAMS, "ADD")
        assert list(players["Player"]) == ["B1", "A2"]  # by Score desc
        assert list(summary["Count"]) == [1, 1]
        assert summary.loc[0, "Best"] == "A2"
        assert summary.loc[1, "Best"] == "B1"
        trades, traded = acquisition_summary(
            rosters, self.values(rosters), self.TEAMS, "TRADE")
        assert list(traded["Player"]) == ["AG"]
        assert trades.loc[1, "Count"] == 0
        assert trades.loc[1, "Best"] is None
        assert pd.isna(trades.loc[1, "Avg Score"])

    def test_market_gaps(self):
        rosters = self.rosters()
        fas = [_skater(7, "Stud", 12, pct_owned=5.0),
               _skater(8, "Dud", 0, pct_owned=50.0),
               _goalie(10, "Wall", 2.0, pct_owned=10.0),
               _goalie(11, "Sieve", 4.0, pct_owned=30.0),
               _goalie(12, "Meh", 3.0, pct_owned=20.0)]
        values = self.values(rosters, fas)
        drops, skaters, goalies = market_gaps(rosters[0], fas, values,
                                              self.TEAMS, 2, 2)
        # A2 is below the skater median, AG is a mid goalie now that there
        # are FA goalies to rank against, A1 is the best skater
        assert list(drops["Player"]) == ["A2", "AG"]
        assert list(skaters["Player"]) == ["Stud", "Dud"]
        assert list(goalies["Player"]) == ["Wall", "Meh"]  # best GAA first
        assert skaters.loc[0, "Team"] == "FA"
        assert skaters.loc[0, "Gap"] < 0  # under-owned for his stats
        assert drops.loc[0, "Slot"] == "IR"

    def test_market_gaps_unscored_first(self):
        rosters = self.rosters()
        ghost = _skater(9, "Ghost", 0, gp=0, team_row=0, pct_owned=99.0)
        roster = rosters[0] + [ghost]
        values = self.values([roster, rosters[1]])
        drops, _, _ = market_gaps(roster, [], values, self.TEAMS, 1, 1)
        assert list(drops["Player"]) == ["Ghost"]
        assert pd.isna(drops.loc[0, "Score"])

    def test_market_gaps_n_larger_than_pool(self):
        rosters = self.rosters()
        drops, skaters, goalies = market_gaps(
            rosters[1], [], self.values(rosters), self.TEAMS, 50, 5)
        assert len(drops) == 2
        assert skaters.empty and goalies.empty
