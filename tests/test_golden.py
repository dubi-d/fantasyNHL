"""End-to-end terminal transcripts of every tool on a synthetic league.

Each case drives the real menu with scripted answers and compares everything
the session produced - console output with its colors, prompts and their
choices, fetch calls, figure inputs - with a stored transcript, so a
refactoring that changes any visible behavior fails here.

Transcripts depend on the installed rich version. After an intended change
regenerate them with ``UPDATE_GOLDEN=1 pytest tests/test_golden.py`` and
review the diff.
"""
import contextlib
import inspect
import os
import textwrap
from dataclasses import dataclass
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest
import questionary
from rich.console import Console

from fantasy_nhl.config import ScheduleCalibration
from support import (
    FakeLeague,
    finished,
    lookup,
    midseason,
    opening_day,
    patch_everywhere,
    pre_draft,
    preseason,
    undrafted,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
BACK = lookup("BACK")
FIGURES = ("power_rankings_figure", "schedule_heatmap_figure",
           "schedule_combined_figure", "category_radar_figure",
           "level_spec_figure")
PROMPTS = ("select", "checkbox", "confirm", "text", "autocomplete")


@dataclass(frozen=True)
class Reject:
    """A scripted free-text answer the prompt's validator must refuse."""
    text: str


class _ScriptEnd(Exception):
    pass


class _Today(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 4)


class _Console(Console):
    def status(self, status, **kwargs):
        # the real spinner animates on a timer
        self.file.write(f"[status] {status}\n")
        return contextlib.nullcontext()


@dataclass
class _Question:
    kind: str
    message: str
    choices: list
    kwargs: dict


def _title(choice) -> str:
    return choice if isinstance(choice, str) else choice.title


def _dump(value) -> str:
    if isinstance(value, pd.DataFrame):
        return (f"DataFrame {[str(t) for t in value.dtypes]}\n"
                + value.to_csv())
    if isinstance(value, pd.Series):
        return f"Series {value.name!r} {value.dtype}\n" + value.to_csv()
    if isinstance(value, dict):
        return "\n".join(f"{key!r}: {_dump(item)}"
                         for key, item in value.items())
    if isinstance(value, (set, frozenset)):
        return repr(sorted(value))
    return repr(value)


class Session:
    """One scripted run of the menu; ``transcript`` records all of it."""

    def __init__(self, monkeypatch, league: FakeLeague, script: list) -> None:
        self.league = league
        self.script = list(script)
        self._out = StringIO()
        console = _Console(file=self._out, force_terminal=True,
                           color_system="truecolor", width=240,
                           no_color=False)
        patch_everywhere(monkeypatch, "console", console)
        patch_everywhere(monkeypatch, "ask", self._ask)
        patch_everywhere(monkeypatch, "date", _Today)
        patch_everywhere(monkeypatch, "load_config",
                         lambda: list(league.sources))
        patch_everywhere(monkeypatch, "save_calibration", self._save)
        patch_everywhere(monkeypatch, "save_figure", lambda fig, path: None)
        for kind in PROMPTS:
            monkeypatch.setattr(questionary, kind, self._prompt(kind))
        for name in FakeLeague.FETCHERS:
            patch_everywhere(monkeypatch, name, self._fetcher(name))
        for name in FIGURES:
            patch_everywhere(monkeypatch, name,
                             self._figure(name, lookup(name)))

    @property
    def transcript(self) -> str:
        return self._out.getvalue().replace("\x1b", "␛")

    def run(self) -> None:
        try:
            lookup("run_menu")(self.league.data, lookup("TOOLS"),
                               select=self._prompt("select"))
        except _ScriptEnd:
            self._write("[end of script]")
        else:
            self._write("[quit]")
            assert not self.script, f"unused answers: {self.script}"

    def _write(self, text: str) -> None:
        self._out.write(text + "\n")

    def _prompt(self, kind: str):
        def prompt(message, choices=(), **kwargs):
            return _Question(kind, message, list(choices), kwargs)
        return prompt

    def _fetcher(self, name: str):
        def fetch(*args):
            shown = [getattr(a, "name", a) for a in args
                     if a is not self.league.data]
            self._write(f"[fetch] {name}"
                        f"({', '.join(repr(a) for a in shown)})")
            return getattr(self.league, name)(*args)
        return fetch

    def _figure(self, name: str, original):
        signature = inspect.signature(original)

        def figure(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            self._write(f"[figure] {name}")
            for key, value in bound.arguments.items():
                if key != "path":
                    self._write(textwrap.indent(f"{key} = {_dump(value)}",
                                                "    "))
        return figure

    def _save(self, league_name: str, calibration: ScheduleCalibration) -> None:
        self._write(f"[save_calibration] {league_name}: {calibration}")

    def _ask(self, question: _Question):
        extras = {key: (value if isinstance(value, (bool, int, str))
                        else _title(value) if hasattr(value, "title")
                        else "<set>")
                  for key, value in sorted(question.kwargs.items())}
        self._write(f"? {question.message} [{question.kind}"
                    + "".join(f", {k}={v!r}" for k, v in extras.items())
                    + "]")
        for choice in question.choices:
            mark = "-" if getattr(choice, "disabled", None) else "*"
            self._write(f"    {mark} {_title(choice)}")
        while True:
            if not self.script:
                raise _ScriptEnd
            answer = self.script.pop(0)
            if isinstance(answer, Reject):
                message = question.kwargs["validate"](answer.text)
                assert message is not True, f"{answer} was accepted"
                self._write(f"  > {answer.text!r} rejected: {message}")
                continue
            self._write("  > " + ("ESC" if answer is BACK else repr(answer)))
            return self._resolve(question, answer)

    def _resolve(self, question: _Question, answer):
        if answer is BACK:
            return BACK
        if question.kind == "select":
            return self._value(question, answer)
        if question.kind == "checkbox":
            return [self._value(question, title) for title in answer]
        if question.kind == "confirm":
            assert isinstance(answer, bool), answer
            return answer
        validate = question.kwargs.get("validate")
        if validate is not None:
            assert validate(answer) is True, validate(answer)
        return answer

    @staticmethod
    def _value(question: _Question, answer: str):
        """The value of the choice titled ``answer`` (or, if no title
        matches exactly, the only one starting with it)."""
        assert isinstance(answer, str), (
            f"{answer!r} is no answer to {question.message!r}")
        enabled = [c for c in question.choices
                   if not getattr(c, "disabled", None)]
        matches = ([c for c in enabled if _title(c) == answer]
                   or [c for c in enabled if _title(c).startswith(answer)])
        assert len(matches) == 1, (
            f"{answer!r} matches {len(matches)} choices of "
            f"{question.message!r}: {[_title(c) for c in enabled]}")
        return getattr(matches[0], "value", matches[0])


CALIBRATION = ScheduleCalibration(source="Old League", calibrated="2026-09-01",
                                  curve={4: 2.6, 8: 1.9, 18: 0.2})
SEASON_ONLY = ["Player stats", "This season only"]
REVIEW = "Players, rosters & draft"
PREVIEW = ["Roster planning", "Show matchup preview"]
PLANNER = ["Roster planning", "Plan streaming week"]
SCHEDULE = ["Roster planning", "Show NHL schedule outlook"]


# case -> (league factory, scripted answers); a script that runs out ends
# the session wherever it is
CASES = {
    "weekly_scores": (midseason, ["Weekly", "Show weekly scores", BACK,
                                  "Quit"]),
    "weekly_scores_finished": (finished, ["Weekly", "Show weekly scores"]),
    "weekly_awards": (midseason, [
        "Weekly", "Generate weekly awards", "Matchup 4", "Matchup 2",
        "Matchup 1", BACK]),
    "standings": (midseason, [
        "Season standings", "Show accumulated scores", "Show luck ranking",
        "Show category strength profile"]),
    "standings_finished": (finished, [
        "Season standings", "Show accumulated scores", "Show luck ranking",
        "Show category strength profile"]),
    "power_rankings": (midseason, [
        "Season standings", "Show power rankings over time", Reject("1"),
        Reject("x"), Reject("5"), "3", "2", BACK]),
    "power_rankings_finished": (finished, [
        "Season standings", "Show power rankings over time", "4"]),
    "preview": (midseason, [
        *PREVIEW, "Matchup 5", "Matchup 2", "Matchup 6", "Matchup 7"]),
    "preview_season_only": (midseason, [
        *SEASON_ONLY, *PREVIEW, "Matchup 5", "Matchup 6"]),
    "preview_opening_day": (opening_day, [
        *PREVIEW, "Matchup 1", BACK, BACK, *SEASON_ONLY, *PREVIEW,
        "Matchup 1"]),
    "planner": (midseason, [
        *PLANNER, "Matchup 5", "Alpha", ["Alpha C2", "Alpha D3"], True, True,
        True, "Matchup 5", "Bravo", [], True, False]),
    "planner_back_navigation": (midseason, [
        *PLANNER, "Matchup 5", "Delta", [], BACK, ["Delta LW1"], False, BACK,
        BACK, "Quit"]),
    "planner_season_only": (midseason, [
        *SEASON_ONLY, *PLANNER, "Matchup 5", "Charlie", ["Charlie RW1"],
        True, False]),
    "planner_next_matchup": (midseason, [
        *PLANNER, "Matchup 6", "Alpha", [], True, False, "Matchup 2",
        "Alpha", "No, just show the roster grid"]),
    "planner_finished": (finished, [
        *PLANNER, "Matchup 8", "Delta", "No, just show the roster grid",
        "Matchup 8", "Alpha", "Plan as if today were Wed 25",
        ["Alpha LW1"], True, False]),
    "planner_opening_day": (opening_day, [
        *SEASON_ONLY, *PLANNER, "Matchup 1", "Alpha", [], True, False]),
    "schedule": (midseason, [
        *SCHEDULE, "Full season", Reject("2"), Reject("half"), "0.4",
        "Remaining", "0.25", "Skip", "Reg Score next 4", "Playoffs only",
        "Skip"]),
    "schedule_calibrated": (lambda: midseason(calibration=CALIBRATION), [
        *SCHEDULE, "Remaining", "0.4", "Alpha", "Fit next 4",
        "Remaining", "0.4", "Bravo", "Combined rest of season",
        "Playoffs only", "Charlie", "Full season", "0"]),
    "schedule_calibration": (midseason, [
        *SCHEDULE, "Calibrate scoring", "Old League (2026)", False,
        "Calibrate scoring", "Test League (2027)", True, "Playoffs only",
        "Skip", "Full season", "1"]),
    "schedule_finished": (finished, [
        *SCHEDULE, "Full season", "0.4", "Playoffs only", "Skip",
        "Remaining", "Skip", "Remaining", "Alpha"]),
    "review_leaders": (midseason, [
        REVIEW,
        "Category leaderboard", "Whole pool", "Forwards", "Score",
        "Percentiles",
        "Category leaderboard", "Free agents", "Goalies", "Elite",
        "Per-game rates",
        "Category leaderboard", "One team", "Alpha", "Skaters (F + D)", "HIT",
        "Per-game rates",
        "Category leaderboard", "Whole pool", "Defense", "Spec",
        "Percentiles"]),
    "review_compare": (midseason, [
        REVIEW,
        "Compare players", Reject(""), Reject("nobody"), "Twin (LW, Bravo)",
        Reject("Twin (LW, Bravo)"), Reject("Alpha G1 (G, Alpha)"),
        "Twin (C, FA)", "Twin (C, FA) #908", "",
        "Compare players", "Alpha G1 (G, Alpha)", "Bravo G2 (G, Bravo)",
        "Delta G2 (G, Delta)", "Free G1 (G, FA)"]),
    "review_league": (midseason, [
        REVIEW, "Roster origins", "Category outlook", "As drafted",
        "Category outlook", "Current", "Waiver pickups", "Trade haul"]),
    "review_draft": (midseason, [
        REVIEW, "Draft grades vs ADP", "Draft hits & busts"]),
    "review_team": (midseason, [
        REVIEW, "Team roster", "Bravo", "As drafted", "Team roster", "Bravo",
        "Current", "Drop candidates & free agents", "Charlie", BACK, BACK]),
    "review_season_only": (midseason, [
        *SEASON_ONLY, REVIEW,
        "Category leaderboard", "One team", "Bravo", "Forwards", "G",
        "Season totals",
        "Category leaderboard", "Whole pool", "Goalies", "SV%",
        "Season totals",
        "Compare players", "Alpha C1 (C, Alpha)", "Bravo C1 (C, Bravo)",
        "Charlie D1 (D, Charlie)", "",
        "Category outlook", "As drafted", "Category outlook", "Current",
        "Draft hits & busts", "Waiver pickups", "Team roster", "Delta",
        "Current", "Drop candidates & free agents", "Delta"]),
    "review_undrafted": (undrafted, [
        REVIEW, "Draft grades vs ADP", "Draft hits & busts",
        "Category outlook", "Trade haul", "Team roster", "Delta",
        "Team roster", "Alpha", "Drop candidates & free agents", "Delta",
        "Category leaderboard", "One team", "Delta", "Forwards", "Score",
        "Percentiles", "Roster origins"]),
    "review_finished": (finished, [
        REVIEW, "Draft grades vs ADP", "Draft hits & busts", "Team roster",
        "Charlie", "As drafted", "Category outlook", "Current",
        "Category leaderboard", "Whole pool", "Skaters (F + D)", "Score",
        "Per-game rates"]),
    "review_opening_day": (opening_day, [
        REVIEW, "Category leaderboard", "Whole pool", "Forwards", "Score",
        "Percentiles", "Draft hits & busts"]),
    "review_opening_day_season_only": (opening_day, [
        *SEASON_ONLY, REVIEW, "Category leaderboard", "Whole pool",
        "Forwards", "Score", "Season totals", "Team roster", "Alpha",
        "Current"]),
    "empty_states": (preseason, [
        "Weekly", "Show weekly scores", "Generate weekly awards", BACK,
        "Season standings", "Show accumulated scores", "Show luck ranking",
        "Show power rankings over time", "Show category strength profile",
        BACK, REVIEW, *PREVIEW, "Matchup 1"]),
    "review_pre_draft": (pre_draft, [
        REVIEW, "Category leaderboard", "Free agents", "Forwards",
        "Score", "Percentiles", "Category leaderboard", "One team", "Alpha",
        "Forwards", "Score", "Percentiles", "Roster origins",
        "Category outlook", "Waiver pickups", "Team roster", "Alpha",
        "Draft grades vs ADP"]),
    "stats_setting": (midseason, [
        "Player stats: Blended", "This season only",
        "Player stats: This season only", BACK,
        "Player stats: This season only", "Blended", BACK]),
}


@pytest.mark.parametrize("case", CASES)
def test_transcript(case, monkeypatch, tmp_path):
    factory, script = CASES[case]
    monkeypatch.chdir(tmp_path)  # figures are saved relative to the cwd
    session = Session(monkeypatch, factory(), script)
    try:
        session.run()
    except Exception:
        print(session.transcript[-4000:])  # where the script went wrong
        raise
    golden = GOLDEN_DIR / f"{case}.txt"
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN_DIR.mkdir(exist_ok=True)
        golden.write_text(session.transcript, encoding="utf-8")
    assert golden.exists(), f"no transcript for {case}: run with UPDATE_GOLDEN=1"
    assert session.transcript == golden.read_text(encoding="utf-8")
