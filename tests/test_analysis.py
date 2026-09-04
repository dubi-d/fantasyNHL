import numpy as np
import pandas as pd
import pytest

from fantasy_nhl.analysis import (
    SEAT_CAP,
    PreviewPlayer,
    average_points,
    blended_per_game,
    calibrate_night_value,
    category_contestedness,
    category_win_rates,
    effective_games,
    luck,
    matchup_result,
    max_lineup_seats,
    night_seat_curve,
    off_night_periods,
    open_seat_counts,
    pick_weekly_awards,
    position_open_seats,
    preview_week,
    rank_streaming_candidates,
    rank_timeline,
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
