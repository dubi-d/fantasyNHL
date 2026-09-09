"""End-to-end tests of the prompt primitives against real questionary
prompts driven through a prompt_toolkit pipe input."""
import pytest
import questionary
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from fantasy_nhl.prompts import BACK, ask


def _drive(make_question, keys: str):
    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        return ask(make_question(input=pipe, output=DummyOutput()))


@pytest.mark.parametrize("make", [
    lambda **kw: questionary.select("s", choices=["a", "b"], **kw),
    lambda **kw: questionary.checkbox("c", choices=["a", "b"], **kw),
    lambda **kw: questionary.confirm("y?", **kw),
    lambda **kw: questionary.text("t", **kw),
])
class TestAsk:
    def test_escape_returns_back(self, make):
        assert _drive(make, "\x1b") is BACK

    def test_ctrl_c_raises(self, make):
        with pytest.raises(KeyboardInterrupt):
            _drive(make, "\x03")


def test_select_enter_returns_value():
    assert _drive(lambda **kw: questionary.select(
        "s", choices=["a", "b"], **kw), "\r") == "a"


def test_text_input_then_enter():
    assert _drive(lambda **kw: questionary.text("t", **kw), "0.4\r") == "0.4"


def test_escape_after_typing_still_backs_out():
    assert _drive(lambda **kw: questionary.text("t", **kw), "0.4\x1b") is BACK
