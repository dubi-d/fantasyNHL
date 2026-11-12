"""View tones render as exactly the styles the tools used directly."""
import numpy as np
import pandas as pd
import pytest

from fantasy_nhl.display import (
    diverging_style,
    heatmap_style,
    note_markup,
    result_style,
    tone_style,
)
from fantasy_nhl.views.model import (
    BAD,
    DANGER,
    EVEN,
    GOOD,
    INFO,
    MUTED,
    STRONG,
    Span,
    column_tones,
    diverging,
    heat,
    note,
)

VALUES = [-7.5, -2, -1.0, -0.26, -0.0, 0, 0.01, 0.5, 1, 3.3, 40,
          np.float64(-0.3), np.int64(2), float("nan"), None, pd.NA]


@pytest.mark.parametrize("scale", [0.5, 1, 1.5, 2, 3, 10, 50, 500, 0, -1])
def test_diverging_tone_matches_the_style(scale):
    for value in VALUES:
        assert tone_style(diverging(value, scale)) == diverging_style(
            value, scale), value


def test_heat_tone_matches_the_style():
    for rate in [0, 0.1, 0.25, 0.5, 0.501, 0.875, 1, 1.4, -0.2,
                 float("nan")]:
        assert tone_style(heat(rate)) == heatmap_style(rate), rate


def test_tags():
    assert [tone_style(tag) for tag in (GOOD, BAD, EVEN)] == [
        result_style(result) for result in "WLT"]
    assert tone_style(f"{MUTED} {DANGER}") == "dim red"
    assert tone_style(None) == tone_style("") == ""


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
