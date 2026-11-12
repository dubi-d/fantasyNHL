"""CLI tools. Register new tools in the TOOLS tree.

A tool is a plain function (prints and returns) or a generator function
yielding wizard steps from ``prompts``: ``answer = yield Ask(thunk)`` for a
prompt (ESC goes back one step) and ``result = yield Do(thunk)`` for any
side effect (fetch, render) so it is not repeated when the user steps back
and forth. Keep everything between yields free of side effects.
"""
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pandas as pd
import questionary

from .analysis import (
    ACQUIRED_ADD,
    ACQUIRED_TRADE,
    COMBINED_PLAYOFF_WEIGHT,
    GOALIE_CATEGORIES,
    RATIO_CATEGORIES,
    PreviewPlayer,
    StatBasis,
    StreamingContext,
    has_projection,
    has_season_games,
    lineup_game_counts,
    open_seat_counts,
    player_rate,
    position_open_seats,
    rank_streaming_candidates,
    team_gap_coverage,
)
from .config import Category, ScheduleCalibration, load_config, save_calibration
from .display import StyleFn, console, note_markup, print_df, tone_style
from .espn_data import (
    LeagueData,
    fetch_adds_used,
    fetch_calibration_data,
    fetch_daily_lineup_slots,
    fetch_free_agents,
    fetch_ir_roster,
    fetch_preview_data,
    fetch_roster_review,
    fetch_rosters_and_slots,
    fetch_schedule_data,
    fetch_week_dates,
    fetch_week_pairings,
)
from .prompts import BACK, Ask, Do, ask
from .views.common import INJURY_ABBREV as _INJURY_ABBREV
from .views.common import NO_PROJECTION as _NO_PROJECTION
from .views.common import NO_PROJECTION_NOTE as _NO_PROJECTION_NOTE
from .views.common import SLOT_ABBREV as _SLOT_ABBREV
from .views.common import SLOT_ORDER as _SLOT_ORDER
from .views.common import completed_matchups, no_season_stats_note, stat_basis
from .views.common import day_labels as _day_labels
from .views.common import position_label as _position_label
from .views.common import with_basis as _with_basis
from .views.draft import (
    build_draft_grades,
    build_draft_return,
    build_team_draft,
    not_drafted,
)
from .views.model import FigureBlock, Note, TableView, TextBlock, View
from .views.players import (
    COMPARE_MAX,
    GROUP_CHOICES,
    build_compare,
    build_leaders,
    cell_choices,
    check_pick,
    leader_sorts,
    player_labels,
)
from .views.preview import build_matchup_preview
from .views.review import build_review_context
from .views.rosters import (
    build_acquired,
    build_gaps,
    build_origins,
    build_outlook,
    build_team_roster,
)
from .views.schedule import (
    build_calibration,
    build_schedule_outlook,
    lead_choices,
    lead_with,
    roster_fit,
    schedule_scores,
    select_schedule,
)
from .views.standings import (
    build_accumulated_scores,
    build_category_profile,
    build_luck_ranking,
    build_power_rankings,
)
from .views.weekly import build_weekly_awards, build_weekly_scores

_STATS_BLENDED = "blended"
_STATS_SEASON = "season"
_STATS_CHOICES = {_STATS_BLENDED: "Blended (season + projection)",
                  _STATS_SEASON: "This season only"}


def _stats_key(data: LeagueData) -> str:
    return _STATS_SEASON if data.season_stats_only else _STATS_BLENDED


def player_stats_label(data: LeagueData) -> str:
    """Menu label of the player stats setting, showing its current value."""
    return f"Player stats: {_STATS_CHOICES[_stats_key(data)]}"


def choose_player_stats(data: LeagueData) -> None:
    """Session-wide setting: the player stats behind every Score, per-game
    rate and prediction - season stats blended with ESPN's projection, or
    this season's stats alone."""
    answer = ask(questionary.select(
        "Player stats for Scores, per-game rates and predictions:",
        choices=[questionary.Choice(label, value=key)
                 for key, label in _STATS_CHOICES.items()],
        default=_stats_key(data)))
    if answer is BACK:
        return
    data.season_stats_only = answer == _STATS_SEASON
    console.print(
        f"Player stats: [bold]{_STATS_CHOICES[answer]}[/] — "
        + ("ESPN's projections are ignored; players without games this "
           "season have no rate. Category outlook keeps its blended pace."
           if data.season_stats_only else
           "season rates weighted by the share of the season elapsed, "
           "ESPN's projection for the rest."))


def _stat_basis(data: LeagueData, season_fraction: float) -> StatBasis:
    return stat_basis(data.season_stats_only, season_fraction)


def _warn_no_season_stats(basis: StatBasis,
                          players: Iterable[PreviewPlayer]) -> None:
    warning = no_season_stats_note(basis, players)
    if warning:
        _show_note(warning)


def _show_note(block: Note) -> None:
    markup, style = note_markup(block)
    console.print(markup, style=style)


def _print_table(table: TableView,
                 widths: dict[str, int] | None = None) -> None:
    print_df(table.frame, table.title,
             cell_styles=(None if table.tones is None
                          else table.tones.map(tone_style)),
             footer=table.footer, widths=widths,
             header_styles={col: "dim" for col in table.muted})


def _save_figure(data: LeagueData, block: FigureBlock) -> None:
    from . import plots  # deferred: matplotlib import is slow
    path = _plot_path(data, block.prefix)
    with console.status("Rendering figure..."):
        figure = getattr(plots, f"{block.kind}_figure")(**block.inputs)
        plots.save_figure(figure, path)
    console.print(f"Saved [bold]{path}[/]")


def _show(data: LeagueData, view: View) -> None:
    """Render a view's blocks in order."""
    for block in view.blocks:
        if isinstance(block, TableView):
            _print_table(block)
        elif isinstance(block, Note):
            _show_note(block)
        elif isinstance(block, TextBlock):
            console.print(block.text, markup=False, highlight=False)
        else:
            _save_figure(data, block)


def weekly_scores(data: LeagueData) -> None:
    """Print the round-robin table for every week, including the ongoing one."""
    _show(data, build_weekly_scores(data))


def accumulated_scores(data: LeagueData) -> None:
    """Print actual matchup record and accumulated round-robin standings
    over all completed weeks."""
    _show(data, build_accumulated_scores(data))


def luck_ranking(data: LeagueData) -> None:
    """Print teams ranked by accumulated schedule luck (luckiest first)."""
    _show(data, build_luck_ranking(data))


def weekly_awards(data: LeagueData):
    """Print weekly awards (best/worst team, luckiest win, biggest choke)
    with a plain-text summary ready to paste into the league chat."""
    completed = completed_matchups(data)
    if completed == 0:
        console.print("No completed matchups yet.", style="yellow")
        return
    week = yield _ask_week(data, last_week=completed, default_week=completed)
    yield Do(lambda: _print_weekly_awards(data, week))


def _print_weekly_awards(data: LeagueData, week: int) -> None:
    with console.status("Fetching matchups..."):
        pairings = fetch_week_pairings(data, week)
    _show(data, build_weekly_awards(data, week, pairings))


def power_rankings(data: LeagueData):
    """Print a teams-x-matchups heatmap of round-robin points and save
    a shareable timeline PNG (hot-streak rank bump chart + average points)."""
    completed = completed_matchups(data)
    if completed < 2:
        console.print("Need at least 2 completed matchups.", style="yellow")
        return

    default = str(min(4, completed))
    answer = yield Ask(lambda: ask(questionary.text(
        f"Hot-streak window in matchups (2-{completed})?", default=default,
        validate=lambda v: (v.isdigit() and 2 <= int(v) <= completed)
        or f"Enter a number between 2 and {completed}")))
    yield Do(lambda: _show(data, build_power_rankings(data, completed,
                                                      int(answer))))


def category_profile(data: LeagueData) -> None:
    """Print each team's per-category round-robin win% over completed weeks,
    plus how contested each category is league-wide."""
    _show(data, build_category_profile(data))


def _ask_week(data: LeagueData, last_week: int | None = None,
              default_week: int | None = None) -> Ask:
    """Wizard step prompting for a matchup week."""
    weeks = last_week or data.total_weeks or data.current_week
    default_week = default_week or data.current_week
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
    return Ask(lambda: ask(questionary.select(
        "Select matchup:", choices=choices,
        default=choices[min(default_week, weeks) - 1])))


def matchup_preview(data: LeagueData):
    """Preview a matchup week: player games and predicted category scores per
    head-to-head pairing. Elapsed days use real data (scores and games actually
    played), remaining days per-game-rate predictions with the current roster
    filling all active slots."""
    week = yield _ask_week(data)
    yield Do(lambda: _print_matchup_preview(data, week))


def _fetch_preview(data: LeagueData, week: int):
    with console.status(f"Fetching preview data for week {week}..."):
        return fetch_preview_data(data, week)


def _print_matchup_preview(data: LeagueData, week: int) -> None:
    preview = _fetch_preview(data, week)
    _show(data, build_matchup_preview(
        data, preview, week, _stat_basis(data, preview.blend_weight)))


def streaming_planner(data: LeagueData):
    """Plan streamer moves for a matchup week: per-day roster grid with open
    active seats (with and without the designated streamers) and NHL teams
    ranked by how well their schedule covers the open days."""
    week = yield _ask_week(data)

    def fetch():
        with console.status(f"Fetching streaming data for week {week}..."):
            return fetch_preview_data(data, week), fetch_adds_used(data, week)
    preview, adds_used = yield Do(fetch)

    my_row = yield Ask(lambda: ask(questionary.select(
        "Select your team:",
        choices=[questionary.Choice(name, value=row)
                 for row, name in enumerate(data.team_names)])))
    roster = sorted(preview.rosters[my_row],
                    key=lambda p: min(_SLOT_ORDER.get(s, len(_SLOT_ORDER))
                                      for s in p.eligible_slots))
    ir_roster = sorted(fetch_ir_roster(data, my_row),
                       key=lambda p: min((_SLOT_ORDER.get(s, len(_SLOT_ORDER))
                                           for s in p.eligible_slots),
                                          default=len(_SLOT_ORDER)))

    actionable = [p for p in preview.periods if p >= preview.current_period]
    simulated_from = None
    if not actionable and preview.periods:
        labels = _day_labels(preview.periods, preview.period_dates)
        # 0 = no simulation (questionary swallows None values)
        sim = yield Ask(lambda: ask(questionary.select(
            "Week is over — simulate it as ongoing to preview the planner?",
            choices=[questionary.Choice("No, just show the roster grid",
                                        value=0)]
            + [questionary.Choice(f"Plan as if today were {labels[p]}",
                                  value=p) for p in preview.periods])))
        if sim:
            actionable = [p for p in preview.periods if p >= sim]
            simulated_from = labels[sim]

    daily_slots = {}
    if actionable:
        def fetch_lineups():
            with console.status("Fetching saved daily ESPN lineups..."):
                return fetch_daily_lineup_slots(data, my_row, actionable)
        daily_slots = yield Do(fetch_lineups)

    streamers: list[str] = []
    if actionable:
        streamers = yield Ask(lambda: ask(questionary.checkbox(
            "Mark your streamers (droppable roster spots):",
            choices=[p.name for p in roster])))

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
        daily_lineup_slots=daily_slots,
        ir_roster=ir_roster,
    )
    align = yield Do(lambda: _render_streaming_plan(
        context, week, data.team_names[my_row], streamers, simulated_from))

    if align is None:  # no open days to stream for
        return
    show_fa = yield Ask(lambda: ask(questionary.confirm(
        "Show free agent candidates for the open days?", default=True)))
    if not show_fa:
        return

    def show_candidates() -> None:
        with console.status("Fetching free agents..."):
            candidates = fetch_free_agents(data, preview.slot_counts)
        if simulated_from:
            console.print("FA pool and stats are today's, not those of the "
                          "simulated week.", style="dim")
        _render_candidates(context, candidates, data.config.categories,
                           _stat_basis(data, preview.blend_weight),
                           streamers, align)
    yield Do(show_candidates)


def _col_width(header: str, values: list) -> int:
    return max([len(header)] + [len(str(v)) for v in values])


def _lead(*col_widths: int) -> int:
    # rendered width of leading columns (content + padding + divider each)
    return sum(w + 3 for w in col_widths)


def _render_streaming_plan(ctx: StreamingContext, week: int, team_name: str,
                           streamers: list[str],
                           simulated_from: str | None = None) -> int | None:
    """Render the planner tables. Returns the shared day-column alignment
    width when there are open days worth streaming for, else None."""
    look = ctx.lookahead_periods
    labels = _day_labels(ctx.periods + look, ctx.period_dates)
    elapsed = [p for p in ctx.periods if p not in set(ctx.actionable_periods)]

    used = "?" if ctx.adds_used is None else ctx.adds_used
    limit = "\u221e" if ctx.adds_limit is None else ctx.adds_limit
    console.print(f"\n[bold]Week {week} streaming planner[/] — {team_name}, "
                  f"adds used this week: [bold]{used} / {limit}[/]")
    if simulated_from:
        console.print(f"SIMULATION — planning as if today were "
                      f"{simulated_from}; using the current roster/IR group "
                      "with saved assignments for those dates, not a "
                      "reconstructed historical roster.",
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

    console.print(
        "Games = remaining scheduled games in saved active ESPN slots "
        "(today included, no lookahead). [orange3]•[/] = saved Bench; "
        "[red]•[/] = IR; ? = lineup unavailable / incomplete total. "
        "Current IR rows are last, always Games 0. Inj = reported injury status.",
        style="dim")
    console.print(
        "Dots show NHL team schedules, not guaranteed player appearances or "
        "goalie starts. Open seats/coverage model capacity, not saved lineups; "
        "IR rows never fill seats.", style="dim")

    # Only the displayed rows include IR. All calculations keep ctx.roster.
    games = lineup_game_counts(ctx.roster, ctx.slot_counts,
                                ctx.playing_by_period, ctx.actionable_periods,
                                ctx.daily_lineup_slots)
    actionable = set(ctx.actionable_periods)

    def marker(player: PreviewPlayer, day: int, ir: bool) -> str:
        if player.pro_team not in ctx.playing_by_period.get(day, set()):
            return ""
        if ir:
            return "[red]•[/]"
        if day not in actionable:
            return "•"
        slot = ctx.daily_lineup_slots.get(day, {}).get(player.player_id)
        if player.player_id <= 0:
            return "?"
        if slot == "Bench":
            return "[orange3]•[/]"
        if slot == "IR":
            return "[red]•[/]"
        return "•" if slot in ctx.slot_counts else "?"

    rows = []
    for ir, players, counts in ((False, ctx.roster, games),
                                (True, ctx.ir_roster, [0] * len(ctx.ir_roster))):
        for player, count in zip(players, counts):
            rows.append({
                "Player": player.name + (" (IR)" if ir else
                          " *" if player.name in streamers else ""),
                "Pos": _position_label(player.eligible_slots)
                       or getattr(player, "position", ""),
                "Team": player.pro_team,
                "Games": "?" if count is None else str(count),
                "Inj": _INJURY_ABBREV.get(player.injury, player.injury[:3]),
                **{labels[d]: marker(player, d, ir) for d in ctx.periods + look},
            })
    grid = pd.DataFrame(rows, index=[""] * len(rows),
                        columns=["Player", "Pos", "Team", "Games", "Inj",
                                 *labels.values()])

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

    # Pad Team/Pos so day columns line up despite the roster summary columns.
    grid_team_w = _col_width("Team", list(grid["Team"]))
    grid_lead = _lead(1, _col_width("Player", list(grid["Player"])
                                    + [r["Player"] for r in footer_rows]),
                      _col_width("Pos", list(grid["Pos"])), grid_team_w,
                      _col_width("Games", list(grid["Games"])),
                      _col_width("Inj", list(grid["Inj"]))) \
        + sum(len(labels[d]) + 3 for d in elapsed)
    leads = [grid_lead]
    if pos_table is not None:
        pos_w = _col_width("Pos", list(pos_table["Pos"]) + ["(total)"])
        leads.append(_lead(1, pos_w))
    if cov_table is not None:
        cov_hash_w = max(1, len(str(len(cov_table))))
        cov_team_w = _col_width("Team", list(cov_table["Team"]))
        leads.append(_lead(cov_hash_w, cov_team_w))
    target = max(leads)

    look_dim = {labels[d]: "dim" for d in look}
    styles: dict[str, StyleFn] = {labels[d]: (lambda _: "dim")
                                  for d in elapsed + look}
    styles["Inj"] = _injury_style
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
             widths={"Pos": pos_w + target - _lead(1, pos_w)},
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
             widths={"Team": cov_team_w + target
                     - _lead(cov_hash_w, cov_team_w)},
             header_styles=look_dim)
    return target


def _injury_style(value: object) -> str:
    return "red" if value in ("OUT", "IR") else ("yellow" if value else "")


def _render_candidates(ctx: StreamingContext, candidates: list[PreviewPlayer],
                       categories: list[Category], basis: StatBasis,
                       streamers: list[str], align: int,
                       page_size: int = 15) -> None:
    """Render the free agent candidate table: schedule fit on the open days
    plus per-game rates (on the given stat basis) for the skater categories.
    Shown in pages of ``page_size``, extending on request."""
    look = ctx.lookahead_periods
    labels = _day_labels(ctx.periods + look, ctx.period_dates)
    keep = [p for p in ctx.roster if p.name not in streamers]
    ranked = rank_streaming_candidates(candidates, keep, ctx.slot_counts,
                                       ctx.playing_by_period,
                                       ctx.actionable_periods)
    ranked = ranked[ranked["Fit"] > 0]
    if ranked.empty:
        console.print("No free agent fills an open seat on the remaining "
                      "days.", style="yellow")
        return
    _warn_no_season_stats(basis, candidates)

    by_name = {c.name: c for c in candidates}
    marker = {"fit": "•", "play": "·", "": ""}
    # candidates are skaters only, so goalie categories carry no signal
    rate_cats = [c for c in categories
                 if c.name not in RATIO_CATEGORIES
                 and c.name not in GOALIE_CATEGORIES]
    rows = []
    for _, r in ranked.iterrows():
        cand = by_name[r["Player"]]
        rates = {cat.name: player_rate(cand, cat.name, basis)
                 for cat in rate_cats}
        unprojected = (not basis.season_only and has_season_games(cand)
                       and not has_projection(cand))
        rows.append({
            "Player": (f"{r['Player']} {_NO_PROJECTION}" if unprojected
                       else r["Player"]),
            "Pos": _position_label(r["Slots"]),
            "Team": r["Team"],
            **{labels[d]: marker[r[d]] for d in ctx.actionable_periods},
            **{labels[d]: "·" if r["Team"] in ctx.playing_by_period.get(d, set())
               else "" for d in look},
            "Fit": r["Fit"],
            "Games": r["Games"],
            **{name: None if v is None else round(v, 2)
               for name, v in rates.items()},
            "Inj": _INJURY_ABBREV.get(r["Injury"], r["Injury"][:3]),
        })
    table = pd.DataFrame(rows, index=range(1, len(rows) + 1))

    # widths from the full table so all pages align with the other tables
    hash_w = max(1, len(str(len(table))))
    team_w = _col_width("Team", list(table["Team"]))
    fa_lead = _lead(hash_w, _col_width("Player", list(table["Player"])),
                    _col_width("Pos", list(table["Pos"])), team_w)

    styles: dict[str, StyleFn] = {
        labels[d]: (lambda v: "bold green" if v == "•" else "")
        for d in ctx.actionable_periods}
    styles.update({labels[d]: (lambda _: "dim") for d in look})
    styles["Inj"] = _injury_style

    for start in range(0, len(table), page_size):
        page = table.iloc[start:start + page_size]
        print_df(page, _with_basis(
                     f"Free agent candidates {start + 1}–"
                     f"{start + len(page)} of {len(table)} by open days "
                     "filled (• = fills an open seat, · = plays)"
                     + (" — streamers dropped" if streamers else ""), basis),
                 styles=styles,
                 widths={"Team": team_w + max(0, align - fa_lead)},
                 header_styles={labels[d]: "dim" for d in look})
        if page["Player"].str.endswith(_NO_PROJECTION).any():
            console.print(_NO_PROJECTION_NOTE, style="dim")
        if start + page_size >= len(table):
            break
        if ask(questionary.confirm("Show more candidates?",
                                   default=True)) is not True:
            break

def _plot_path(data: LeagueData, prefix: str) -> Path:
    plots_dir = Path("plots")
    plots_dir.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", data.config.name.lower()).strip("_")
    return plots_dir / f"{prefix}_{slug}.png"


def _valid_weight(value: str) -> bool | str:
    try:
        return 0 <= float(value) <= 1 or "Enter a number between 0 and 1"
    except ValueError:
        return "Enter a number between 0 and 1"


def schedule_outlook(data: LeagueData):
    """Per-NHL-team games and off-night games per fantasy matchup: summary
    table in the terminal, full teams-x-matchups heatmap as a PNG."""
    def fetch():
        with console.status("Fetching NHL schedule..."):
            return fetch_schedule_data(data)
    schedule = yield Do(fetch)

    while True:
        scope = yield Ask(lambda: ask(questionary.select(
            "Scope:", choices=[
                questionary.Choice("Full season", value="full"),
                questionary.Choice(
                    f"Remaining matchups (from matchup {data.current_week})",
                    value="remaining"),
                questionary.Choice("Playoffs only", value="playoffs"),
                questionary.Choice("Calibrate scoring", value="calibrate"),
            ])))
        if scope != "calibrate":
            break
        yield from _calibrate_schedule_scoring(data)

    selection = select_schedule(data, schedule, scope)
    if selection is None:
        console.print("No matchups in the selected scope.", style="yellow")
        return
    calibration = data.config.calibration  # after a possible recalibration

    playoff_weight = COMBINED_PLAYOFF_WEIGHT
    if selection.blends_playoffs:
        answer = yield Ask(lambda: ask(questionary.text(
            "Playoff weight in Combined score (0-1)?",
            default=str(COMBINED_PLAYOFF_WEIGHT),
            validate=_valid_weight)))
        playoff_weight = float(answer)

    fit = None
    if scope != "full":
        fit = yield from _roster_fit(data, schedule.playing_by_period,
                                     selection.score_periods)
    scores = schedule_scores(schedule, selection, calibration,
                             playoff_weight, fit)
    leads = lead_choices(selection, scores)
    if leads:
        lead = leads[0]
        if len(leads) > 1:
            lead = yield Ask(lambda: ask(questionary.select(
                "Sort by:", choices=leads)))
        scores = lead_with(scores, lead)

    yield Do(lambda: _show(data, build_schedule_outlook(
        data, schedule, selection, scores, calibration, playoff_weight,
        fitted=fit is not None)))


_SKIP = object()  # "no roster" choice; never None (questionary quirk)


def _roster_fit(data: LeagueData, playing_by_period: dict[int, set[str]],
                week_periods: dict[int, list[int]]):
    """Wizard steps for the Fit score: effective games weighted by a
    roster's actual open lineup seats; returns None if skipped."""
    row = yield Ask(lambda: ask(questionary.select(
        "Weight the score by a fantasy roster's open seats (Fit)?",
        choices=[questionary.Choice("Skip", value=_SKIP)]
        + [questionary.Choice(name, value=i)
           for i, name in enumerate(data.team_names)])))
    if row is _SKIP:
        return None

    def compute() -> pd.Series:
        with console.status("Fetching rosters..."):
            slot_counts, rosters = fetch_rosters_and_slots(data)
        return roster_fit(playing_by_period, week_periods, rosters[row],
                          slot_counts)
    return (yield Do(compute))


# questionary's default dropdown is bold orange on light grey
_AUTOCOMPLETE_STYLE = questionary.Style([
    ("completion-menu", "bg:#303030"),
    # items also carry questionary's "answer"/"selected" classes, applied last
    ("completion-menu.completion answer", "fg:#e4e4e4 nobold"),
    ("completion-menu.completion.current selected",
     "bg:#0087af fg:#ffffff bold noreverse"),
    ("scrollbar.background", "bg:#444444"),
    ("scrollbar.button", "bg:#909090"),
])


def review_rosters(data: LeagueData):
    """Player, roster and draft review: per-category player profiles
    (leaderboard and head-to-head comparison), league-wide composition and
    projected category outlook (ranked by round-robin points), draft grades
    vs ADP and hits & busts, waiver pickups and trade hauls, and one team's
    roster or drop candidates - all valued by a stat-based Score, with
    ESPN roster% alongside."""
    def fetch():
        with console.status("Fetching rosters, free agents and draft..."):
            review = fetch_roster_review(data)
        if not any(review.rosters) and not review.picks:
            console.print("Rosters are empty and the league has not drafted "
                          "yet.", style="yellow")
            return None
        _warn_no_season_stats(
            _stat_basis(data, review.blend_weight),
            [p for roster in review.rosters for p in roster]
            + review.free_agents)
        return review
    review = yield Do(fetch)
    if review is None:
        return

    ctx = build_review_context(data, review,
                               _stat_basis(data, review.blend_weight))
    by_label = player_labels(ctx)

    def show(build, *args) -> Do:
        return Do(lambda: _show(data, build(ctx, *args)))

    def ask_player(picked: tuple[int, ...]):
        def run():
            answer = ask(questionary.autocomplete(
                f"Player {len(picked) + 1}"
                + ("" if len(picked) < 2 else " (Enter to finish)") + ":",
                choices=list(by_label),
                validate=lambda text: check_pick(ctx, by_label, picked, text),
                match_middle=True, style=_AUTOCOMPLETE_STYLE))
            return answer if answer is BACK else by_label.get(answer, _SKIP)
        return Ask(run)

    def ask_leaders():
        scope = yield Ask(lambda: ask(questionary.select(
            "Players:", choices=[
                questionary.Choice("Whole pool", value="all"),
                questionary.Choice("Free agents", value="fa"),
                questionary.Choice("One team", value="team"),
            ])))
        row = (yield ask_team()) if scope == "team" else None
        group = yield Ask(lambda: ask(questionary.select(
            "Position:", choices=[questionary.Choice(label, value=key)
                                  for key, label in GROUP_CHOICES.items()])))
        sort = yield Ask(lambda: ask(questionary.select(
            "Sort by:", choices=leader_sorts(ctx, group))))
        cells = yield Ask(lambda: ask(questionary.select(
            "Cells show:", choices=[
                questionary.Choice(label, value=key)
                for key, label in cell_choices(ctx.basis).items()])))
        return scope, row, group, sort, cells

    def ask_team():
        return Ask(lambda: ask(questionary.select(
            "Which team?",
            choices=[questionary.Choice(team, value=i)
                     for i, team in enumerate(data.team_names)])))

    def ask_source():
        return Ask(lambda: ask(questionary.select(
            "Rosters:", choices=[
                questionary.Choice("As drafted", value="draft"),
                questionary.Choice("Current", value="current"),
            ])))

    while True:  # ESC at the prompt leaves the tool
        view = yield Ask(lambda: ask(questionary.select(
            "View:", choices=[
                questionary.Separator("── Players ──"),
                questionary.Choice("Category leaderboard", value="leaders"),
                questionary.Choice("Compare players", value="compare"),
                questionary.Separator("── League ──"),
                questionary.Choice("Roster origins", value="origins"),
                questionary.Choice("Category outlook", value="balance"),
                questionary.Separator("── Draft ──"),
                questionary.Choice("Draft grades vs ADP", value="grades"),
                questionary.Choice("Draft hits & busts", value="return"),
                questionary.Separator("── Transactions ──"),
                questionary.Choice("Waiver pickups", value="adds"),
                questionary.Choice("Trade haul", value="trades"),
                questionary.Separator("── One team ──"),
                questionary.Choice("Team roster", value="team"),
                questionary.Choice("Drop candidates & free agents",
                                   value="gaps"),
            ])))
        if view in ("grades", "return") and not ctx.drafted:
            yield Do(lambda: _show(data, not_drafted()))
        elif view == "leaders":
            choice = yield from ask_leaders()
            yield show(build_leaders, *choice)
        elif view == "compare":
            picked: tuple[int, ...] = ()
            while len(picked) < COMPARE_MAX:
                pid = yield ask_player(picked)
                if pid is _SKIP:
                    break
                picked += (pid,)
            yield show(build_compare, picked)
        elif view == "origins":
            yield show(build_origins)
        elif view == "grades":
            yield show(build_draft_grades)
        elif view == "return":
            yield show(build_draft_return)
        elif view == "adds":
            yield show(build_acquired, ACQUIRED_ADD, "Waiver pickups")
        elif view == "trades":
            yield show(build_acquired, ACQUIRED_TRADE, "Traded-in players")
        elif view == "balance":
            source = "current" if not ctx.drafted else (yield ask_source())
            yield show(build_outlook, source)
        elif view == "team":
            row = yield ask_team()
            source = "current" if not ctx.drafted else (yield ask_source())
            yield show(build_team_draft if source == "draft"
                       else build_team_roster, row)
        else:
            row = yield ask_team()
            yield show(build_gaps, row)


def _calibrate_schedule_scoring(data: LeagueData):
    """Wizard steps calibrating the schedule-scoring night-value curve from
    a chosen league season and storing it in calibration.yaml."""
    leagues = load_config()
    source = yield Ask(lambda: ask(questionary.select(
        "Calibrate from which league season?",
        choices=[questionary.Choice(f"{cfg.name} ({cfg.year})", value=cfg)
                 for cfg in leagues])))

    def fit_curve() -> dict[int, float]:
        with console.status(f"Fetching {source.name} data..."):
            cal_data = fetch_calibration_data(source)
        view, curve = build_calibration(source.name, cal_data)
        _show(data, view)
        return curve
    curve = yield Do(fit_curve)

    save = yield Ask(lambda: ask(questionary.confirm(
        f"Save as calibration for {data.config.name}?", default=True)))
    if not save:
        return

    def persist() -> None:
        calibration = ScheduleCalibration(source=source.name,
                                          calibrated=date.today().isoformat(),
                                          curve=curve)
        save_calibration(data.config.name, calibration)
        data.config.calibration = calibration  # take effect immediately
        console.print("Saved to [bold]calibration.yaml[/]")
    yield Do(persist)


# (menu label, tool or submenu list) — nest lists to group tools
TOOLS = [
    ("Weekly", [
        ("Show weekly scores", weekly_scores),
        ("Generate weekly awards", weekly_awards),
    ]),
    ("Season standings", [
        ("Show accumulated scores", accumulated_scores),
        ("Show luck ranking", luck_ranking),
        ("Show power rankings over time", power_rankings),
        ("Show category strength profile", category_profile),
    ]),
    ("Roster planning", [
        ("Show matchup preview", matchup_preview),
        ("Plan streaming week", streaming_planner),
        ("Show NHL schedule outlook", schedule_outlook),
    ]),
    ("Players, rosters & draft", review_rosters),
    (player_stats_label, choose_player_stats),
]
