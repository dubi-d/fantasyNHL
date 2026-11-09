"""Offline streaming-planner rendering and wizard regressions."""
from dataclasses import replace
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from rich.console import Console
from rich.text import Text

from fantasy_nhl import display, tools
from fantasy_nhl.analysis import PreviewPlayer, RosterPlayer, StreamingContext
from fantasy_nhl.cli import run_tool
from fantasy_nhl.config import Category
from fantasy_nhl.prompts import BACK, Ask, Do


def _context():
    return StreamingContext(
        roster=[PreviewPlayer("First", "BOS", ["Center"], injury="DAY_TO_DAY", player_id=1),
                PreviewPlayer("Second", "BOS", ["Center"], injury="OUT", player_id=2),
                PreviewPlayer("Goalie", "DAL", ["Goalie"], player_id=3),
                PreviewPlayer("Unknown", "BOS", ["Center"], player_id=4)],
        slot_counts={"Center": 2, "Forward": 1, "Util": 1, "Goalie": 1},
        playing_by_period={1: {"BOS"}, 2: {"BOS", "DAL"}, 3: {"BOS"},
                           4: {"DAL"}, 5: {"BOS"}},
        periods=[1, 2, 3, 4], actionable_periods=[2, 3, 4], period_dates={},
        lookahead_periods=[5],
        daily_lineup_slots={2: {1: "Center", 2: "Bench", 3: "Goalie", 5: "Center"},
                            3: {1: "Bench", 2: "Center", 5: "Center"},
                            4: {3: "Goalie"}},
        ir_roster=[RosterPlayer("Reserved", "BOS", [], player_id=5,
                                position="Center", lineup_slot="IR", injury="ACTIVE")],
    )


@pytest.fixture
def rendered(monkeypatch):
    output = StringIO()
    console = Console(file=output, force_terminal=True, color_system="truecolor", width=240)
    monkeypatch.setattr(tools, "console", console)
    monkeypatch.setattr(display, "console", console)
    calls = []

    def capture(df, title, **kwargs):
        calls.append((df.copy(), title, kwargs))
        display.print_df(df, title, **kwargs)

    monkeypatch.setattr(tools, "print_df", capture)
    return console, output, calls


def test_roster_games_colors_injuries_ir_order_and_blanks(rendered):
    console, output, calls = rendered
    ctx = _context()
    assert tools._render_streaming_plan(ctx, 1, "Test", ["First"]) is not None
    grid, _, kwargs = calls[0]
    assert list(grid.columns[:5]) == ["Player", "Pos", "Team", "Games", "Inj"]
    assert grid["Games"].tolist() == ["1", "1", "2", "?", "0"]
    assert grid["Player"].tolist() == ["First *", "Second", "Goalie", "Unknown", "Reserved (IR)"]
    assert grid["Inj"].tolist() == ["DTD", "OUT", "", "", ""]
    assert grid.iloc[-1]["Pos"] == "Center"  # IR without active eligibility
    assert grid.iloc[0]["Day 2"] == "•"
    assert grid.iloc[0]["Day 3"] == "[orange3]•[/]"
    assert grid.iloc[1]["Day 2"] == "[orange3]•[/]"
    assert grid.iloc[3]["Day 2"] == "?"
    assert grid.iloc[-1]["Day 2"] == "[red]•[/]"  # wins over future activation
    assert grid.iloc[-1]["Day 4"] == ""
    assert "Games" not in kwargs["footer"] and "Inj" not in kwargs["footer"]
    assert "lineup unavailable" in Text.from_ansi(output.getvalue()).plain

    # Inspect actual terminal-rendered spans, including nested dim+red styles.
    lines = [Text.from_ansi(line) for line in output.getvalue().splitlines()]
    ir_line = next(line for line in lines if "Reserved (IR)" in line.plain)
    dots = [i for i, c in enumerate(ir_line.plain) if c == "•"]
    assert len(dots) == 4
    for i in dots:
        assert ir_line.get_style_at_offset(console, i).color.get_truecolor() == console.get_style("red").color.get_truecolor()
    assert ir_line.get_style_at_offset(console, dots[0]).dim
    assert not ir_line.get_style_at_offset(console, dots[1]).dim
    assert ir_line.get_style_at_offset(console, dots[-1]).dim
    bench_line = next(line for line in lines if "Second" in line.plain)
    dots = [i for i, c in enumerate(bench_line.plain) if c == "•"]
    assert bench_line.get_style_at_offset(console, dots[1]).color.get_truecolor() == console.get_style("orange3").color.get_truecolor()
    assert bench_line.get_style_at_offset(console, bench_line.plain.index("OUT")).color.get_truecolor() == console.get_style("red").color.get_truecolor()
    first_line = next(line for line in lines if "First *" in line.plain)
    assert first_line.get_style_at_offset(console, first_line.plain.index("DTD")).color.get_truecolor() == console.get_style("yellow").color.get_truecolor()


def test_ir_and_streamer_flags_do_not_change_saved_counts_or_capacity(rendered):
    _, _, calls = rendered
    ctx = _context()
    tools._render_streaming_plan(ctx, 1, "Test", [])
    with_ir = list(calls)
    calls.clear()
    tools._render_streaming_plan(replace(ctx, ir_roster=[]), 1, "Test", [])
    for full, without in zip(with_ir[1:], calls[1:]):
        pd.testing.assert_frame_equal(full[0], without[0])
    pd.testing.assert_frame_equal(with_ir[0][2]["footer"], calls[0][2]["footer"])
    original = calls[0][0]
    calls.clear()
    tools._render_streaming_plan(ctx, 1, "Test", ["Second"])
    assert calls[0][0]["Games"].tolist()[:4] == original["Games"].tolist()
    assert calls[0][0]["Day 2"].tolist()[:4] == original["Day 2"].tolist()


@pytest.mark.parametrize("ir_only", [False, True])
def test_empty_and_ir_only_rosters_render(rendered, ir_only):
    _, _, calls = rendered
    ctx = replace(_context(), roster=[], ir_roster=_context().ir_roster if ir_only else [])
    tools._render_streaming_plan(ctx, 1, "Test", [])
    assert len(calls[0][0]) == int(ir_only)
    assert list(calls[0][0].columns[:5]) == ["Player", "Pos", "Team", "Games", "Inj"]


def test_finished_matchup_and_simulation_cutoff(rendered):
    _, _, calls = rendered
    ctx = replace(_context(), actionable_periods=[])
    assert tools._render_streaming_plan(ctx, 1, "Test", []) is None
    assert calls[0][0]["Games"].tolist() == ["0"] * 5
    assert len(calls) == 1
    calls.clear()
    ctx = replace(ctx, actionable_periods=[4])
    tools._render_streaming_plan(ctx, 1, "Test", [], "Day 4")
    assert calls[0][0]["Games"].tolist() == ["0", "0", "1", "0", "0"]
    assert calls[0][0].iloc[0]["Day 3"] == "•"  # elapsed, no orange


def test_future_ir_assignment_is_red_and_not_counted(rendered):
    _, _, calls = rendered
    ctx = _context()
    ctx.daily_lineup_slots[2][1] = "IR"
    tools._render_streaming_plan(ctx, 1, "Test", [])
    assert calls[0][0].iloc[0]["Day 2"] == "[red]•[/]"
    assert calls[0][0].iloc[0]["Games"] == "0"


def test_actionable_day_columns_align_including_candidates(rendered):
    _, output, _ = rendered
    ctx = _context()
    align = tools._render_streaming_plan(ctx, 1, "Test", ["First"])
    candidate = PreviewPlayer("Candidate", "BOS", ["Center", "Forward", "Util"],
                              injury="SUSPENSION", player_id=9)
    tools._render_candidates(ctx, [candidate], [], 0.0, ["First"], align)
    lines = Text.from_ansi(output.getvalue()).plain.splitlines()
    headers = [line for line in lines if "#" in line and "Day 2" in line]
    assert len(headers) == 4
    for day in (2, 3, 4, 5):
        assert len({line.index(f"Day {day}") for line in headers}) == 1


@pytest.mark.parametrize("width", [60, 100])
def test_narrow_terminal_still_renders(rendered, width):
    console, _, _ = rendered
    console.width = width
    tools._render_streaming_plan(_context(), 1, "Test", [])


@pytest.mark.parametrize("cutoff,simulation,expected", [
    (2, None, [2, 3, 4]), (10, 3, [3, 4]), (10, 0, [])])
def test_planner_fetches_only_actionable_dates_in_do(monkeypatch, cutoff, simulation, expected):
    ctx = _context()
    preview = SimpleNamespace(rosters=[ctx.roster], periods=ctx.periods,
                              current_period=cutoff, period_dates={},
                              slot_counts=ctx.slot_counts, playing_by_period=ctx.playing_by_period,
                              add_limit=3, next_periods=[5, 6])
    monkeypatch.setattr(tools, "_ask_week", lambda data: Ask(lambda: 1))
    monkeypatch.setattr(tools, "fetch_preview_data", lambda data, week: preview)
    monkeypatch.setattr(tools, "fetch_adds_used", lambda data, week: [0])
    monkeypatch.setattr(tools, "fetch_ir_roster", lambda data, row: ctx.ir_roster)
    fetch = Mock(return_value=ctx.daily_lineup_slots)
    monkeypatch.setattr(tools, "fetch_daily_lineup_slots", fetch)
    render = Mock(return_value=None)
    monkeypatch.setattr(tools, "_render_streaming_plan", render)
    data = SimpleNamespace(team_names=["Test"])
    wizard = tools.streaming_planner(data)
    assert isinstance(next(wizard), Ask)
    step = wizard.send(1)
    assert isinstance(step, Do)
    # Do is a dataclass holding its action; avoid executing UI prompts.
    step = wizard.send((preview, [0]))
    assert isinstance(step, Ask)
    step = wizard.send(0)
    if simulation is not None:
        assert isinstance(step, Ask)
        step = wizard.send(simulation)
    if expected:
        assert isinstance(step, Do)
        fetch.assert_not_called()  # not a side effect during generator replay
        slots = step.run()
        fetch.assert_called_once_with(data, 0, expected)
        step = wizard.send(slots)
        assert isinstance(step, Ask)
        choices = []
        monkeypatch.setattr(tools.questionary, "checkbox",
                            lambda prompt, **kw: choices.extend(kw["choices"]))
        monkeypatch.setattr(tools, "ask", lambda question: [])
        step.run()
        assert "Reserved" not in choices
        step = wizard.send([])
    else:
        fetch.assert_not_called()
    assert isinstance(step, Do)
    step.run()
    actual_ctx = render.call_args.args[0]
    assert actual_ctx.actionable_periods == expected
    assert actual_ctx.ir_roster == ctx.ir_roster
    assert all(p.name != "Reserved" for p in actual_ctx.roster)
    assert actual_ctx.daily_lineup_slots == (ctx.daily_lineup_slots if expected else {})
    with pytest.raises(StopIteration):
        wizard.send(None)


def test_back_to_streamers_reuses_daily_lineup_snapshot(monkeypatch, rendered):
    ctx = _context()
    preview = SimpleNamespace(rosters=[ctx.roster], periods=ctx.periods,
                              current_period=2, period_dates={},
                              slot_counts=ctx.slot_counts,
                              playing_by_period=ctx.playing_by_period,
                              add_limit=3, next_periods=[5])
    # Week, team, streamers, BACK from FA confirmation, new streamers,
    # decline FA, then leave the restarted tool at the first prompt.
    answers = iter([1, 0, [], BACK, ["First"], False, BACK])
    monkeypatch.setattr(tools, "_ask_week", lambda data: Ask(lambda: next(answers)))
    monkeypatch.setattr(tools, "ask", lambda question: next(answers))
    for name in ("select", "checkbox", "confirm"):
        monkeypatch.setattr(tools.questionary, name, lambda *args, **kwargs: None)
    preview_fetch = Mock(return_value=preview)
    daily_fetch = Mock(return_value=ctx.daily_lineup_slots)
    render = Mock(return_value=80)
    monkeypatch.setattr(tools, "fetch_preview_data", preview_fetch)
    monkeypatch.setattr(tools, "fetch_adds_used", lambda data, week: [0])
    monkeypatch.setattr(tools, "fetch_ir_roster", lambda data, row: ctx.ir_roster)
    monkeypatch.setattr(tools, "fetch_daily_lineup_slots", daily_fetch)
    monkeypatch.setattr(tools, "_render_streaming_plan", render)
    data = SimpleNamespace(team_names=["Test"])
    run_tool(data, tools.streaming_planner)
    preview_fetch.assert_called_once_with(data, 1)
    daily_fetch.assert_called_once_with(data, 0, [2, 3, 4])
    assert [call.args[3] for call in render.call_args_list] == [[], ["First"]]
    assert all(call.args[0].daily_lineup_slots is ctx.daily_lineup_slots
               for call in render.call_args_list)


def _profile_player(pid, name, g, hit, team_row=None, slots=("Center",)):
    return RosterPlayer(name, "BOS", list(slots), player_id=pid,
                        position=slots[0], team_row=team_row,
                        season_stats={"G": g, "A": g, "HIT": hit, "GP": 30})


def test_player_profile_views(monkeypatch, rendered, tmp_path):
    _, output, calls = rendered
    rosters = [[_profile_player(1, "Sniper", 20, 5, 0),
                _profile_player(2, "Banger", 2, 90, 0)],
               [_profile_player(3, "Twin", 10, 40, 1)]]
    free_agents = [_profile_player(4, "Twin", 1, 1),
                   _profile_player(5, "Wall", 0, 0, slots=("Goalie",))]
    review = SimpleNamespace(rosters=rosters, free_agents=free_agents, picks=[],
                             drafted_players={}, counters=[], blend_weight=1.0,
                             slot_counts={}, n_teams=2)
    monkeypatch.setattr(tools, "fetch_roster_review", lambda data: review)
    monkeypatch.setattr(tools, "_plot_path", lambda data, prefix: tmp_path / f"{prefix}.png")
    data = SimpleNamespace(team_names=["Alpha", "Beta"], config=SimpleNamespace(
        categories=[Category("G"), Category("A"), Category("HIT")],
        name="Test", year=2026))

    wizard = tools.review_rosters(data)
    step = next(wizard)
    step = wizard.send(step.run())  # view prompt
    for answer in ("leaders", "team", 0, "F", "HIT", "total"):
        step = wizard.send(answer)
    assert isinstance(step, Do)
    step.run()
    leaders, title, kwargs = calls[-1]
    assert "Alpha" in title and "HIT percentile" in title
    assert leaders["Player"].tolist() == ["Banger", "Sniper"]
    assert leaders["HIT"].tolist() == [90, 5]  # season totals
    # colored by percentile (Banger tops HIT), not by the displayed total
    assert kwargs["cell_styles"].loc[1, "HIT"] == display.heatmap_style(0.875)
    assert (tmp_path / "player_map.png").exists()

    # compare: autocomplete labels disambiguate the two "Twin"s
    questions = []
    monkeypatch.setattr(tools.questionary, "autocomplete",
                        lambda message, **kw: questions.append(kw) or kw)
    step = wizard.send(None)
    step = wizard.send("compare")
    labels = iter(["Sniper (C, Alpha)", "Twin (C, FA)", ""])
    monkeypatch.setattr(tools, "ask", lambda question: next(labels))
    for _ in range(3):
        step = wizard.send(step.run())
    validate = questions[-1]["validate"]
    assert validate("") is True  # two picked: Enter finishes
    assert validate("Wall (G, FA)") == "Can't mix skaters and goalies"
    assert validate("Sniper (C, Alpha)") == "Already picked"
    assert questions[0]["validate"]("") == "Pick a player"
    assert isinstance(step, Do)
    step.run()
    cells, _, _ = calls[-2]
    assert list(cells.columns) == ["Cat", "Sniper", "Twin"]
    assert cells["Sniper"].tolist() == ["20 · 0.67 · 88", "20 · 0.67 · 88",
                                       "5 · 0.17 · 38"]
    assert (tmp_path / "player_radar.png").exists()

def test_autocomplete_dropdown_is_readable():
    from prompt_toolkit.styles import default_ui_style, merge_styles
    from questionary.styles import merge_styles_default
    style = merge_styles([default_ui_style(),
                          merge_styles_default([tools._AUTOCOMPLETE_STYLE])])
    # class order as prompt_toolkit's completion menu renders the items
    item = style.get_attrs_for_style_str(
        "class:completion-menu class:completion-menu.completion class:answer")
    current = style.get_attrs_for_style_str(
        "class:completion-menu class:completion-menu.completion.current "
        "class:answer class:selected")
    assert (item.color, item.bgcolor, item.bold) == ("e4e4e4", "303030", False)
    assert (current.color, current.bgcolor, current.reverse) == ("ffffff", "0087af", False)
