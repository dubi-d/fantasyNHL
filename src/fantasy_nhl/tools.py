"""CLI tools. Register new tools in the TOOLS list."""
import pandas as pd
import questionary

from .analysis import (
    RATIO_CATEGORIES,
    StreamingContext,
    category_contestedness,
    category_win_rates,
    luck,
    matchup_result,
    open_seat_counts,
    position_open_seats,
    preview_week,
    round_robin,
    team_gap_coverage,
)
from .display import (
    StyleFn,
    console,
    diverging_style,
    heatmap_style,
    print_df,
    result_style,
)
from .espn_data import (
    LeagueData,
    fetch_adds_used,
    fetch_preview_data,
    fetch_week_dates,
)

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


def _ask_week(data: LeagueData) -> int | None:
    """Prompt for a matchup week (None on Ctrl-C)."""
    weeks = data.total_weeks or data.current_week
    with console.status("Fetching matchup dates..."):
        week_dates = fetch_week_dates(data)

    def dates(week: int) -> str:
        if week not in week_dates:
            return ""
        start, end = week_dates[week]
        return f" ({start:%b %-d} – {end:%b %-d})"

    choices = [questionary.Choice(
        f"Matchup {week}" + dates(week)
        + (" (playoffs)" if 0 < data.regular_weeks < week else "")
        + (" (current)" if week == data.current_week else ""),
        value=week) for week in range(1, weeks + 1)]
    return questionary.select(
        "Select matchup:", choices=choices,
        default=choices[min(data.current_week, weeks) - 1]).ask()


def matchup_preview(data: LeagueData) -> None:
    """Preview a matchup week: player games and predicted category scores per
    head-to-head pairing. Elapsed days use real data (scores and games actually
    played), remaining days per-game-rate predictions with the current roster
    filling all active slots."""
    week = _ask_week(data)
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


# specific positions first; Forward/Util add no information for the label
_SLOT_ABBREV = {"Center": "C", "Left Wing": "LW", "Right Wing": "RW",
                "Defense": "D", "Goalie": "G", "Forward": "F", "Util": "U"}
_SLOT_ORDER = {slot: i for i, slot in enumerate(_SLOT_ABBREV)}


def _position_label(eligible_slots: list[str]) -> str:
    specific = [s for s in eligible_slots if s not in ("Forward", "Util")]
    slots = sorted(specific or eligible_slots, key=_SLOT_ORDER.get)
    return "/".join(_SLOT_ABBREV.get(s, s) for s in slots)


def _day_labels(periods: list[int],
                period_dates: dict[int, object]) -> dict[int, str]:
    return {p: (f"{period_dates[p]:%a %-d}" if p in period_dates
                else f"Day {p}") for p in periods}


def streaming_planner(data: LeagueData) -> None:
    """Plan streamer moves for a matchup week: per-day roster grid with open
    active seats (with and without the designated streamers) and NHL teams
    ranked by how well their schedule covers the open days."""
    week = _ask_week(data)
    if week is None:  # Ctrl-C
        return

    with console.status(f"Fetching streaming data for week {week}..."):
        preview = fetch_preview_data(data, week)
        adds_used = fetch_adds_used(data, week)

    my_row = questionary.select(
        "Select your team:",
        choices=[questionary.Choice(name, value=row)
                 for row, name in enumerate(data.team_names)]).ask()
    if my_row is None:  # Ctrl-C
        return
    roster = sorted(preview.rosters[my_row],
                    key=lambda p: min(_SLOT_ORDER.get(s, len(_SLOT_ORDER))
                                      for s in p.eligible_slots))

    actionable = [p for p in preview.periods if p >= preview.current_period]
    simulated_from = None
    if not actionable and preview.periods:
        labels = _day_labels(preview.periods, preview.period_dates)
        # 0 = no simulation (questionary swallows None values)
        sim = questionary.select(
            "Week is over — simulate it as ongoing to preview the planner?",
            choices=[questionary.Choice("No, just show the roster grid",
                                        value=0)]
            + [questionary.Choice(f"Plan as if today were {labels[p]}",
                                  value=p) for p in preview.periods]).ask()
        if sim:
            actionable = [p for p in preview.periods if p >= sim]
            simulated_from = labels[sim]

    streamers: list[str] = []
    if actionable:
        streamers = questionary.checkbox(
            "Mark your streamers (droppable roster spots):",
            choices=[p.name for p in roster]).ask() or []

    context = StreamingContext(
        roster=roster,
        slot_counts=preview.slot_counts,
        playing_by_period=preview.playing_by_period,
        periods=preview.periods,
        actionable_periods=actionable,
        period_dates=preview.period_dates,
        adds_used=adds_used[my_row],
        adds_limit=preview.add_limit,
        lookahead_periods=preview.next_periods[:2],
    )
    _render_streaming_plan(context, week, data.team_names[my_row], streamers,
                           simulated_from)


def _render_streaming_plan(ctx: StreamingContext, week: int, team_name: str,
                           streamers: list[str],
                           simulated_from: str | None = None) -> None:
    look = ctx.lookahead_periods
    labels = _day_labels(ctx.periods + look, ctx.period_dates)
    elapsed = [p for p in ctx.periods if p not in set(ctx.actionable_periods)]

    used = "?" if ctx.adds_used is None else ctx.adds_used
    limit = "\u221e" if ctx.adds_limit is None else ctx.adds_limit
    console.print(f"\n[bold]Week {week} streaming planner[/] — {team_name}, "
                  f"adds used this week: [bold]{used} / {limit}[/]")
    if simulated_from:
        console.print(f"SIMULATION — planning as if today were "
                      f"{simulated_from}; the grid shows the current roster, "
                      f"not the historical lineups of that week.",
                      style="bold magenta")
    elif not ctx.actionable_periods:
        console.print("Week is over — the grid shows the current roster, not "
                      "the historical lineups of that week.", style="yellow")
    elif elapsed:
        console.print("Dimmed days are elapsed and excluded from open seats "
                      "and coverage; today counts as actionable.", style="dim")
    if look and ctx.actionable_periods:
        console.print(f"Columns after {labels[max(ctx.periods)]} preview next "
                      "week's first days — informational only, excluded from "
                      "the coverage ranking.", style="dim")

    # roster grid: game markers per day, open seats as footer
    grid = pd.DataFrame([{
        "Player": p.name + (" *" if p.name in streamers else ""),
        "Pos": _position_label(p.eligible_slots),
        "Team": p.pro_team,
        **{labels[d]: "•" if p.pro_team in ctx.playing_by_period.get(d, set())
           else "" for d in ctx.periods + look},
    } for p in ctx.roster], index=[""] * len(ctx.roster))

    keep = [p for p in ctx.roster if p.name not in streamers]
    seat_periods = ctx.actionable_periods + look
    open_current = open_seat_counts(ctx.roster, ctx.slot_counts,
                                    ctx.playing_by_period, seat_periods)
    open_dropped = open_seat_counts(keep, ctx.slot_counts,
                                    ctx.playing_by_period, seat_periods)

    def open_row(name: str, opened: dict[int, tuple[int, int]],
                 part: int) -> dict[str, str]:
        return {"Player": name,
                **{labels[d]: str(seats[part]) if seats[part] else "-"
                   for d, seats in opened.items()}}

    footer_rows = [open_row("(open skater seats)", open_current, 0),
                   open_row("(open goalie seats)", open_current, 1)]
    if streamers:
        footer_rows += [open_row("(skater, streamers out)", open_dropped, 0),
                        open_row("(goalie, streamers out)", open_dropped, 1)]
    footer = pd.DataFrame(footer_rows, index=[""] * len(footer_rows)) \
        if ctx.actionable_periods else None

    # disjoint per-slot open seats; specific seats are filled before F/Util
    pos_table = totals = None
    if ctx.actionable_periods:
        open_slots = position_open_seats(keep, ctx.slot_counts,
                                         ctx.playing_by_period, seat_periods)
        pos_table = pd.DataFrame([{
            "Pos": _SLOT_ABBREV.get(slot, slot),
            **{labels[d]: str(open_slots[d][slot]) if open_slots[d][slot] else "-"
               for d in seat_periods},
        } for slot in ctx.slot_counts], index=[""] * len(ctx.slot_counts))
        totals = pd.DataFrame([{
            "Pos": "(total)",
            **{labels[d]: str(sum(open_slots[d].values()))
               if any(open_slots[d].values()) else "-"
               for d in seat_periods},
        }], index=[""])

    # coverage counts games on days that still have any open seat
    open_periods = {d for d in ctx.actionable_periods
                    if sum(open_dropped[d]) > 0}
    cov_table = None
    if ctx.actionable_periods and open_periods:
        coverage = team_gap_coverage(ctx.playing_by_period, open_periods,
                                     ctx.actionable_periods)
        coverage = coverage[coverage["Cover"] > 0].head(12)
        cov_table = pd.DataFrame({
            "Team": coverage["Team"],
            **{labels[d]: coverage[d].map({True: "•", False: ""})
               for d in ctx.actionable_periods},
            **{labels[d]: coverage["Team"].map(
                lambda t, d=d: "•" if t in ctx.playing_by_period.get(d, set())
                else "") for d in look},
            "Cover": coverage["Cover"],
            "Games": coverage["Games"],
        })
        cov_table.index = range(1, len(cov_table) + 1)

    # pad each table's last leading column so day columns line up across tables
    def width(header: str, values: list) -> int:
        return max([len(header)] + [len(str(v)) for v in values])

    def lead(*col_widths: int) -> int:
        # rendered width of leading columns (content + padding + divider each)
        return sum(w + 3 for w in col_widths)

    grid_team_w = width("Team", list(grid["Team"]))
    grid_lead = lead(1, width("Player", list(grid["Player"])
                              + [r["Player"] for r in footer_rows]),
                     width("Pos", list(grid["Pos"])), grid_team_w) \
        + sum(len(labels[d]) + 3 for d in elapsed)
    leads = [grid_lead]
    if pos_table is not None:
        pos_w = width("Pos", list(pos_table["Pos"]) + ["(total)"])
        leads.append(lead(1, pos_w))
    if cov_table is not None:
        cov_hash_w = max(1, len(str(len(cov_table))))
        cov_team_w = width("Team", list(cov_table["Team"]))
        leads.append(lead(cov_hash_w, cov_team_w))
    target = max(leads)

    look_dim = {labels[d]: "dim" for d in look}
    styles: dict[str, StyleFn] = {labels[d]: (lambda _: "dim")
                                  for d in elapsed + look}
    print_df(grid, f"Roster week {week}"
             + (" (* = streamer)" if streamers else ""),
             styles=styles, footer=footer,
             widths={"Team": grid_team_w + target - grid_lead},
             header_styles=look_dim)

    if not ctx.actionable_periods:
        return

    print_df(pos_table, "Open seats by lineup slot"
             + (" — streamers dropped" if streamers else ""),
             styles={labels[d]: (lambda _: "dim") for d in look},
             footer=totals,
             widths={"Pos": pos_w + target - lead(1, pos_w)},
             header_styles=look_dim)

    if cov_table is None:
        console.print("No open seats on the remaining days — mark streamers "
                      "to see which teams could cover their spots.",
                      style="yellow")
        return

    marker_styles: dict[str, StyleFn] = {
        labels[d]: (lambda v: "bold green" if v == "•" else "")
        for d in open_periods}
    marker_styles.update({labels[d]: (lambda _: "dim") for d in look})
    open_labels = ", ".join(labels[d] for d in sorted(open_periods))
    print_df(cov_table, f"NHL teams covering the open days ({open_labels})"
             + (" — streamers dropped" if streamers else ""),
             styles=marker_styles,
             widths={"Team": cov_team_w + target - lead(cov_hash_w, cov_team_w)},
             header_styles=look_dim)


# (menu label, callable) — extend here for new tools
TOOLS = [
    ("Show weekly scores", weekly_scores),
    ("Show accumulated scores", accumulated_scores),
    ("Show luck ranking", luck_ranking),
    ("Show category strength profile", category_profile),
    ("Show matchup preview", matchup_preview),
    ("Plan streaming week", streaming_planner),
]
