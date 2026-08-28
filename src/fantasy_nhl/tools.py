"""CLI tools. Register new tools in the TOOLS list."""
import pandas as pd
import questionary

from .analysis import (
    RATIO_CATEGORIES,
    category_contestedness,
    category_win_rates,
    luck,
    matchup_result,
    preview_week,
    round_robin,
)
from .display import (
    StyleFn,
    console,
    diverging_style,
    heatmap_style,
    print_df,
    result_style,
)
from .espn_data import LeagueData, fetch_preview_data

# points awarded for a real matchup result ("NA" -> no luck value yet)
RESULT_PTS = {"W": 2, "T": 1, "L": 0}


def _round_robin_week(data: LeagueData, week: int) -> pd.DataFrame:
    return round_robin(data.weekly_cat_scores[:, :, week - 1],
                       data.config.categories, data.team_names)


def _ranked(table: pd.DataFrame, by: str = "Pts") -> pd.DataFrame:
    """Sort by the given points column and use the rank as index."""
    table = table.sort_values(by=[by], ascending=False)
    table.index = range(1, len(table) + 1)
    return table


def weekly_scores(data: LeagueData) -> None:
    """Print the round-robin table for every week, including the ongoing one."""
    for week in range(1, data.current_week + 1):
        table = _round_robin_week(data, week)
        table["Result"] = [row_results[week - 1] for row_results in data.weekly_results]
        table = table.rename(columns={"W": "rrW", "L": "rrL", "T": "rrT"})
        actual_pts = table["Result"].map(RESULT_PTS)
        table["Luck"] = luck(actual_pts, table["Pts"], len(data.team_names) - 1).round(2)
        table = _ranked(
            table[["Player", "Result", "rrW", "rrL", "rrT", "CatsWon", "Pts", "Luck"]])
        ongoing = " (ongoing)" if week == data.current_week else ""
        # weekly luck is bounded by +-2
        print_df(table, f"Week {week}{ongoing}",
                 styles={"Result": result_style,
                         "Luck": lambda v: diverging_style(v, 2)})


def accumulated_scores(data: LeagueData) -> None:
    """Print actual matchup record and accumulated round-robin standings
    over all completed weeks."""
    accumulated = _accumulated_table(data)
    if accumulated is None:
        console.print("No completed weeks yet.", style="yellow")
        return

    accumulated = _ranked(
        accumulated[["Player", "W", "L", "T", "Pts",
                     "rrW", "rrL", "rrT", "CatsWon", "xPts", "Luck"]],
        by="xPts")
    luck_scale = accumulated["Luck"].abs().max()
    print_df(accumulated, "Accumulated Scores (matchup vs round-robin)",
             styles={"Luck": lambda v: diverging_style(v, luck_scale)})


def _accumulated_table(data: LeagueData) -> pd.DataFrame | None:
    """Accumulated round-robin stats, actual record and luck over completed
    weeks, or None if no week is completed yet."""
    completed_weeks = data.current_week - 1
    if completed_weeks == 0:
        return None

    stat_cols = ["W", "L", "T", "CatsWon", "Pts"]
    accumulated = _round_robin_week(data, 1)
    for week in range(2, completed_weeks + 1):
        accumulated[stat_cols] += _round_robin_week(data, week)[stat_cols]
    accumulated = accumulated.rename(columns={"W": "rrW", "L": "rrL", "T": "rrT"})

    # actual matchup record (completed weeks only)
    for result in ("W", "L", "T"):
        accumulated[result] = [row_results[:completed_weeks].count(result)
                               for row_results in data.weekly_results]
    num_opponents = len(data.team_names) - 1
    actual_pts = 2 * accumulated["W"] + accumulated["T"]
    accumulated["Luck"] = luck(actual_pts, accumulated["Pts"], num_opponents).round(2)
    # replace rr points with expected points; matchup points take the Pts name
    accumulated["xPts"] = (accumulated["Pts"] / num_opponents).round(2)
    accumulated["Pts"] = actual_pts
    return accumulated


def luck_ranking(data: LeagueData) -> None:
    """Print teams ranked by accumulated schedule luck (luckiest first)."""
    table = _accumulated_table(data)
    if table is None:
        console.print("No completed weeks yet.", style="yellow")
        return

    table = table.sort_values(by=["Luck"], ascending=False)
    table.index = range(1, len(table) + 1)
    table = table[["Player", "W", "L", "T", "Pts", "xPts", "Luck"]]
    luck_scale = table["Luck"].abs().max()
    print_df(table, "Luck Ranking (positive = favorable schedule)",
             styles={"Luck": lambda v: diverging_style(v, luck_scale)})


def category_profile(data: LeagueData) -> None:
    """Print each team's per-category round-robin win% over completed weeks,
    plus how contested each category is league-wide."""
    completed_weeks = data.current_week - 1
    if completed_weeks == 0:
        console.print("No completed weeks yet.", style="yellow")
        return

    scores = data.weekly_cat_scores[:, :, :completed_weeks]
    cat_names = [cat.name for cat in data.config.categories]
    table = category_win_rates(scores, data.config.categories, data.team_names)
    contested = category_contestedness(table, data.config.categories).round(2)
    table["Overall"] = table[cat_names].mean(axis=1)
    table[cat_names + ["Overall"]] = table[cat_names + ["Overall"]].round(2)
    table = _ranked(table[["Player"] + cat_names + ["Overall"]], by="Overall")

    footer = pd.DataFrame(
        [{"Player": "(contested)", **contested.to_dict()}], index=[""])
    print_df(table, "Category Strength Profile "
             "(win rate per category, completed weeks)",
             styles={col: heatmap_style for col in cat_names + ["Overall"]},
             footer=footer)


def _pair_style(home_raw: float, away_raw: float, inverted: bool,
                home_display: float, away_display: float) -> StyleFn:
    """Style callback coloring the better of two displayed category scores,
    judged on the raw (unrounded) values."""
    if home_raw == away_raw or home_display == away_display:
        return lambda _: "bold yellow"
    home_wins = home_raw < away_raw if inverted else home_raw > away_raw
    winner = home_display if home_wins else away_display
    return lambda value: "bold green" if value == winner else "bold red"


def matchup_preview(data: LeagueData) -> None:
    """Preview a matchup week: player games and predicted category scores per
    head-to-head pairing. Elapsed days use real data (scores and games actually
    played), remaining days per-game-rate predictions with the current roster
    filling all active slots."""
    weeks = data.total_weeks or data.current_week
    choices = [questionary.Choice(
        f"Week {week}"
        + (" (playoffs)" if 0 < data.regular_weeks < week else "")
        + (" (current)" if week == data.current_week else ""),
        value=week) for week in range(1, weeks + 1)]
    week = questionary.select(
        "Select matchup week:", choices=choices,
        default=choices[min(data.current_week, weeks) - 1]).ask()
    if week is None:  # Ctrl-C
        return

    with console.status(f"Fetching preview data for week {week}..."):
        preview = fetch_preview_data(data, week)
    if not preview.pairings:
        console.print("No matchups scheduled for this week yet (playoff "
                      "pairings appear once the bracket is seeded).",
                      style="yellow")
        return

    days_real = len(preview.periods) - len(preview.remaining_periods)
    if not preview.remaining_periods:
        status = "completed, real data"
    elif days_real == 0:
        status = "not started, predictions only"
    else:
        status = (f"{days_real} days real (live), "
                  f"{len(preview.remaining_periods)} days predicted")
    dates = ""
    if preview.start_date and preview.end_date:
        dates = (f", {preview.start_date:%a %b %-d} \u2013 "
                 f"{preview.end_date:%a %b %-d}")
    console.print(f"\n[bold]Week {week} preview[/] — {len(preview.periods)} "
                  f"days{dates}, {status}. Games = games actually played on "
                  f"elapsed days plus playable games of the current roster "
                  f"on remaining days.")

    categories = data.config.categories
    games = {}
    scores = {}  # raw values for results, so display rounding can't fake ties
    display = {}
    for row in range(len(data.team_names)):
        games[row], scores[row] = preview_week(
            preview.rosters[row], preview.slot_counts,
            preview.playing_by_period,
            preview.remaining_periods, preview.actual_scores[row],
            categories, preview.blend_weight,
            preview.actual_games[row], preview.actual_goalie_games[row])
        display[row] = [
            round(float(value), 2 if cat.name in RATIO_CATEGORIES else 1)
            for value, cat in zip(scores[row], categories)]

    for home_row, away_row in preview.pairings:
        rows = []
        for row, opponent in ((home_row, away_row), (away_row, home_row)):
            won, lost, _tied, cats_won = matchup_result(
                scores[row], scores[opponent], categories)
            rows.append({"Player": data.team_names[row], "Games": games[row],
                         **{cat.name: display[row][i]
                            for i, cat in enumerate(categories)},
                         "Cats": int(cats_won),
                         "Proj": "W" if won else ("L" if lost else "T")})
        styles: dict[str, StyleFn] = {"Proj": result_style}
        for i, cat in enumerate(categories):
            styles[cat.name] = _pair_style(scores[home_row][i],
                                           scores[away_row][i], cat.inverted,
                                           display[home_row][i],
                                           display[away_row][i])
        print_df(pd.DataFrame(rows, index=["", ""]),
                 f"{data.team_names[home_row]} vs {data.team_names[away_row]}",
                 styles=styles)


# (menu label, callable) — extend here for new tools
TOOLS = [
    ("Show weekly scores", weekly_scores),
    ("Show accumulated scores", accumulated_scores),
    ("Show luck ranking", luck_ranking),
    ("Show category strength profile", category_profile),
    ("Show matchup preview", matchup_preview),
]
