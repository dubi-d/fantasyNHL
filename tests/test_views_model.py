"""View tones and the styles the terminal renders them with."""
import numpy as np
import pandas as pd
import pytest

from fantasy_nhl.cli.display import note_markup, tone_style
from fantasy_nhl.views.model import (
    BAD,
    DANGER,
    EVEN,
    GOOD,
    INFO,
    MUTED,
    STRONG,
    Span,
    cell_texts,
    column_tones,
    diverging,
    heat,
    note,
)


@pytest.mark.parametrize("value,scale,style", [
    (0, 2, "white on rgb(60,60,60)"),
    (-0.0, 2, "white on rgb(60,60,60)"),
    (1, 2, "white on rgb(30,98,30)"),
    (np.int64(2), 2, "white on rgb(0,135,0)"),
    (40, 2, "white on rgb(0,135,0)"),  # saturates at the scale
    (-1.0, 2, "white on rgb(118,30,30)"),
    (np.float64(-0.3), 1.5, "white on rgb(83,48,48)"),
    (-7.5, 1.5, "white on rgb(175,0,0)"),
    (float("nan"), 2, ""), (None, 2, ""), (pd.NA, 2, ""),
    (1, 0, ""), (1, -1, ""),  # no scale, no tone
])
def test_diverging_tone_styles(value, scale, style):
    assert tone_style(diverging(value, scale)) == style


@pytest.mark.parametrize("rate,style", [
    (0.5, "white on rgb(60,60,60)"), (1, "white on rgb(0,135,0)"),
    (0, "white on rgb(175,0,0)"), (0.875, "white on rgb(15,116,15)"),
    (0.25, "white on rgb(118,30,30)"), (1.4, "white on rgb(0,135,0)"),
    (-0.2, "white on rgb(175,0,0)"), (float("nan"), ""),
])
def test_heat_tone_styles(rate, style):
    assert tone_style(heat(rate)) == style


def test_tags():
    assert [tone_style(tag) for tag in (GOOD, BAD, EVEN)] == [
        "bold green", "bold red", "bold yellow"]
    assert tone_style(f"{MUTED} {DANGER}") == "dim red"
    assert tone_style(None) == tone_style("") == ""


def test_cell_texts_keep_whole_numbers_whole():
    frame = pd.DataFrame({"Teams": [4, 18], "Seats": [3.0, 0.22],
                          "Rank": pd.array([1, None], dtype="Int64"),
                          "Name": ["a", None]})
    assert cell_texts(frame) == [["4", "3.0", "1", "a"],
                                 ["18", "0.22", "", ""]]
    assert cell_texts(frame.iloc[:0]) == []
    assert cell_texts(pd.DataFrame(index=[1, 2])) == [[], []]

def test_column_tones_keep_row_order_and_skip_missing_columns():
    frame = pd.DataFrame({"A": [1.0, np.nan], "B": ["x", "y"]}, index=["", ""])
    tones = column_tones(frame, {"A": lambda v: diverging(v, 2),
                                 "B": lambda v: GOOD if v == "y" else None,
                                 "C": lambda v: BAD})
    assert list(tones.columns) == ["A", "B"]
    assert tones["A"].tolist() == [0.5, None]
    assert tones["B"].tolist() == [None, GOOD]


def test_note_markup():
    assert note_markup(note("plain")) == ("plain", None)
    assert note_markup(note(Span("Week 1", STRONG), " - 7 days", level=INFO,
                            space_before=True)) == (
        "\n[bold]Week 1[/] - 7 days", "dim")
