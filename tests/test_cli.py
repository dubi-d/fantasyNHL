"""Tests for the wizard runner and nested menu navigation in cli.py."""
import pytest

from fantasy_nhl.cli import run_menu, run_tool
from fantasy_nhl.prompts import BACK, Ask, Do


def scripted(*answers):
    """Return an Ask thunk factory replaying ``answers`` in order; a
    fake stdin for the wizard under test."""
    queue = list(answers)

    def make(label):
        def thunk():
            if not queue:
                raise AssertionError(f"unexpected prompt {label}")
            return queue.pop(0)
        return Ask(thunk)
    make.queue = queue
    return make


class TestRunTool:
    def test_plain_function_runs_once(self):
        calls = []
        run_tool("data", lambda data: calls.append(data))
        assert calls == ["data"]

    def test_forward_pass_then_back_at_first_prompt_returns(self):
        log = []
        prompt = scripted("a", "b", BACK)

        def wizard(data):
            x = yield prompt("first")
            y = yield prompt("second")
            log.append((x, y))
            yield Do(lambda: log.append("done"))
        run_tool(None, wizard)
        # finished once (a, b), restarted, BACK at first prompt -> return
        assert log == [("a", "b"), "done"]
        assert prompt.queue == []

    def test_do_after_popped_prompt_is_rerun(self):
        fetches = []
        prompt = scripted(1, BACK, 2, BACK, BACK)

        def wizard(data):
            week = yield prompt("week")
            preview = yield Do(lambda: fetches.append(week) or f"p{week}")
            team = yield prompt("team")
            yield Do(lambda: fetches.append(("render", preview, team)))
        run_tool(None, wizard)
        # week=1 -> fetch once; BACK at team -> back to week prompt; fetch
        # (a Do after the popped prompt) is discarded and re-run for week=2
        assert fetches == [1, 2]

    def test_back_keeps_do_before_the_popped_prompt(self):
        runs = []
        prompt = scripted("x", BACK, "y", BACK, BACK)

        def wizard(data):
            yield Do(lambda: runs.append("setup"))
            a = yield prompt("a")
            b = yield prompt("b")
            runs.append((a, b))
        run_tool(None, wizard)
        # setup Do precedes the first prompt: memoized across all replays
        assert runs == ["setup"]

    def test_finished_wizard_restarts_from_first_prompt(self):
        renders = []
        prompt = scripted("a", "b", BACK)

        def wizard(data):
            v = yield prompt("v")
            yield Do(lambda: renders.append(v))
        run_tool(None, wizard)
        assert renders == ["a", "b"]

    def test_generator_returning_before_first_prompt_returns(self):
        printed = []

        def wizard(data):
            printed.append("nothing to do")
            return
            yield  # pragma: no cover - makes this a generator

        run_tool(None, wizard)
        assert printed == ["nothing to do"]

    def test_do_only_wizard_runs_once(self):
        runs = []

        def wizard(data):
            yield Do(lambda: runs.append(1))
        run_tool(None, wizard)
        assert runs == [1]

    def test_early_return_after_prompt_restarts(self):
        prompt = scripted("skip", "go", BACK)
        log = []

        def wizard(data):
            mode = yield prompt("mode")
            if mode == "skip":
                log.append("skipped")
                return
            yield Do(lambda: log.append("ran"))
        run_tool(None, wizard)
        assert log == ["skipped", "ran"]

    def test_yield_from_helper_back_navigates_one_step(self):
        prompt = scripted("outer", "inner1", BACK, "inner2", "ok", BACK, BACK)
        log = []

        def helper():
            inner = yield prompt("inner")
            return inner.upper()

        def wizard(data):
            outer = yield prompt("outer")
            inner = yield from helper()
            ok = yield prompt("confirm")
            log.append((outer, inner, ok))
        run_tool(None, wizard)
        # BACK at confirm returns to the helper's prompt, not to outer
        assert log == [("outer", "INNER2", "ok")]

    def test_unknown_step_type_raises(self):
        def wizard(data):
            yield "not a step"
        with pytest.raises(TypeError):
            run_tool(None, wizard)


class TestRunMenu:
    @staticmethod
    def fake_select(answers):
        """A questionary.select stand-in; ``answers`` are the labels to pick
        (BACK for ESC). Returns a select() replacement whose result object
        exposes .application/.unsafe_ask like a Question."""
        queue = list(answers)

        class Question:
            def __init__(self, choices):
                self.choices = choices
                self.application = type("App", (), {"key_bindings": None})()

            def unsafe_ask(self):
                pick = queue.pop(0)
                if pick is BACK:
                    return BACK
                for choice in self.choices:
                    if choice.title == pick:
                        return choice.value
                raise AssertionError(f"no choice {pick!r}")

        def select(message, choices, **kwargs):
            return Question(choices)
        select.queue = queue
        return select

    def test_group_navigation_and_esc_levels(self, monkeypatch):
        import fantasy_nhl.cli as cli
        # ask() installs key bindings; bypass with a passthrough
        monkeypatch.setattr(cli, "ask", lambda q: q.unsafe_ask())
        ran = []
        items = [("Group", [("Tool", lambda data: ran.append(data))]),
                 ("Top tool", lambda data: ran.append("top"))]
        select = self.fake_select(["Group", "Tool", BACK, "Top tool", BACK])
        run_menu("d", items, select=select)
        assert ran == ["d", "top"]
        assert select.queue == []

    def test_quit_choice_exits(self, monkeypatch):
        import fantasy_nhl.cli as cli
        monkeypatch.setattr(cli, "ask", lambda q: q.unsafe_ask())
        select = self.fake_select(["Quit"])
        run_menu(None, [("Tool", lambda data: None)], select=select)
        assert select.queue == []
