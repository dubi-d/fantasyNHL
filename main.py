import numpy as np
import pandas as pd
from espn_api.hockey import League


# League info
# Cookies for login purposes (use your own)

LEAGUE_ID = 66082163
YEAR = 2021
SWID = '{C00A35AB-85C6-494A-AA9B-F479E7DE4023}'
ESPN_S2 = 'AEC4RCmF5SmVt843LzQsM2eLIZJyT%2BRyZb9Dg7mmH4zIwnKLYELnX1aRCV797tog' \
          'yY2%2B6skSfH5DuPDjKfokEnlfldMBu84MBrrPQStDZ58wuRZPikIs7Ip5pi1wOgls' \
          '4e0S%2BUTAZxhSyRs2n7anYAF810kEfP0k1Exu9mfwFjasyZirLDEI3jy9JDu00J34' \
          'm242rD%2F8Ys6vTRvQIq40KbxQjln0dyoVsH0G5G8SFlYy7b4TobzVD7x8OO%2F46g' \
          'ALC30%3D'

# 2022
#LEAGUE_ID = 576726473
#YEAR = 2023
#SWID = '{C00A35AB-85C6-494A-AA9B-F479E7DE4023}'
#ESPN_S2 = 'AEBSog1%2BzMJ53yfdocP2KSge9AWxjw%2B2y4X34b%2BjqhSxjHgLRpNq6BFMG2Nxo' \
#          '3uS8Sk787ens4A7m%2FiULjEowCIZR933eO5idCi4S0KqqMYyKtCgxLEKfvTp04WeqW' \
#          'HExk%2FI1DJ3tcLs3dtiPHnr%2BID1aoKfX5Cx4mfWVmsV2uTx98qm%2Bni5yJzAoVY' \
#          'tCAxJdGzr11S8n2hloXe0YAKnlVQzLo53RGY6KI6xJDiH%2BO1qrrJP4DQJYQ91CDIU' \
#          'Lm39h0EXi9ipe3Q4a%2BWB1GHCOwX0'

# Map category name to index (with a defined order)
# mark inverted categories by adding any string (e.g. "inverted_cat")
CATEGORIES = [
    ["G", "13"],
    ["A", "14"],
    ["PIM", "17"],
    ["PPP", "38"],
    ["SHP", "39"],
    ["HAT", "28"],
    ["SOG", "29"],
    ["HIT", "31"],
    ["BLK", "32"],
    ["SO", "7"],
    ["SV%", "11"],
    ["GAA", "10", "inverted_cat"]
]
# Map teams to ID
TEAM_NAMES = {
    1: "ZION",
    2: "EHC",
    3: "GKG",
    4: "COI",
    5: "SQ",
    6: "RIHI",
    7: "GROO",
    8: "EDDY",
    9: "WIN",
    10: "AG",
    11: "WUIL",
    12: "FLIP"
}


def extract_matchup_scores(league, dest):
    """
    Collect Weekly scores in all categories for each player.
    :param league: league object from espn_api library
    :param dest: 3D numpy array to store the matchup scores. It has the form:
     - axis 0 (rows): player score for a given week (player_id = row_idx + 1)
     - axis 1 (columns): categories
     - axis 3 ("depth"): matchup week
    """
    # todo use league/settings to find matchup numbers?
    # todo use league.scoreboard(week_number) to get each weeks results
    # todo adjust categories
    current_week = league.currentMatchupPeriod
    for matchup in league.data["schedule"]:
        week_number = matchup["matchupPeriodId"]

        # don't consider current matchup
        if week_number >= current_week:
            break

        for team in ["home", "away"]:
            player_id = matchup[team]["teamId"]
            data = matchup[team]["cumulativeScore"]["scoreByStat"]
            for i, cat in enumerate(CATEGORIES):
                dest[player_id - 1, i, week_number - 1] = data[cat[1]]["score"]


def round_robin(scores):
    """
    Calculate W, L, T, Pts, CatsWon if every team played every other team
    simultaneously in the given week.

    :param scores: Scores summary of a single week.
    :return: Summary statistics
    """
    rr_cats = ["W", "L", "T", "CatsWon", "Pts"]
    number_of_teams = scores.shape[0]
    rr_summary = np.zeros((number_of_teams, len(rr_cats)), dtype=np.int)

    for i in range(number_of_teams):
        for k in range(number_of_teams):
            if i == k:
                # don't match teams against themselves
                continue

            # match player i against all other players k, accumulate scores
            rr_summary[i, :-1] += matchup_result(scores[i], scores[k])
        rr_summary[i, -1] = 2 * rr_summary[i, 0] + rr_summary[i, 2]  # calculate points

    rr_summary = pd.DataFrame(rr_summary)
    rr_summary.columns = rr_cats
    rr_summary["Player"] = [TEAM_NAMES[i+1] for i in range(len(TEAM_NAMES))]
    return rr_summary


def matchup_result(player_stats, opponent_stats):
    """
    Given accumulated stats of a player and his opponent in a week,
    compute W, L, T, CatsWon.

    :param player_stats: 1D numpy array containing category scores
    :param opponent_stats: 1D numpy array containing category scores
    :return: 1D numpy array [W, L, T, CatsWon]
    """
    cats_won = 0
    cats_tied = 0
    W = 0
    L = 0
    T = 0

    for i, cat in enumerate(CATEGORIES):
        # check if cat is inverted (length 3) or not (length 2)
        # and accumulate number of won/tied cats
        if len(cat) == 2:
            cats_won += int(player_stats[i] > opponent_stats[i])
        else:
            cats_won += int(player_stats[i] < opponent_stats[i])
        cats_tied += int(player_stats[i] == opponent_stats[i])

    W = int(cats_won > len(CATEGORIES) - cats_tied - cats_won)
    L = int(cats_won < len(CATEGORIES) - cats_tied - cats_won)
    T = int(not (W or L))
    return np.array([W, L, T, cats_won])


if __name__ == "__main__":

    maythebestteamwin = League(league_id=LEAGUE_ID, year=YEAR, espn_s2=ESPN_S2, swid=SWID)
    maythebestteamwin.fetch_league()
    curr_week = maythebestteamwin.currentMatchupPeriod
    scoreboard = maythebestteamwin.scoreboard(curr_week)
    box_scores = maythebestteamwin.box_scores(curr_week)

    #  Collect Weekly scores in all categories for each player
    # axis 0 (rows): player score for a given week (player_id = row_idx + 1)
    # axis 1 (columns): categories
    # axis 3 ("depth"): matchup week
    weekly_cat_scores = np.zeros((12, 12, curr_week - 1))

    extract_matchup_scores(maythebestteamwin, weekly_cat_scores)

    rr_cumulative = pd.DataFrame()

    with pd.option_context('display.max_rows', 20, 'display.max_columns', 20):
        #print(week_1_scores)
        for i in range(curr_week-1):
            print("\n-------Week " + str(i+1) + ":")
            rr_week_i = round_robin(weekly_cat_scores[:, :, i])
            print(rr_week_i)
            if i == 0:
                rr_cumulative = rr_week_i
            else:
                rr_cumulative = rr_cumulative.add(rr_week_i[["W", "L", "T", "CatsWon", "Pts"]])

    rr_cumulative["Player"] = rr_week_i["Player"]
    rr_cumulative.sort_values(by=["Pts"], ascending=False, inplace=True)
    rr_cumulative = rr_cumulative[["Player", "W", "L", "T", "CatsWon", "Pts"]]
    print("\n #### Accumulated Scores:")
    print(rr_cumulative)
