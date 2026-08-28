import numpy as np
import pandas as pd
import pytest

from fantasy_nhl.analysis import (
    PreviewPlayer,
    blended_per_game,
    category_contestedness,
    category_win_rates,
    luck,
    matchup_result,
    max_lineup_seats,
    open_seat_counts,
    position_open_seats,
    preview_week,
    round_robin,
    seat_counts,
    team_gap_coverage,
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
