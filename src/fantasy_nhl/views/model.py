"""The view model: ordered blocks (tables, notes, text, figures) with
semantic cell tones instead of terminal styles."""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# A cell tone: None (plain), a float in [-1, 1] (diverging intensity: 0 is
# neutral, +1 fully good, -1 fully bad) or space-separated tags.
Tone = float | str | None

GOOD = "good"  # the better side, a win
BAD = "bad"  # the worse side, a loss
EVEN = "even"  # a tie
WARN = "warn"  # needs attention
DANGER = "danger"  # unavailable
BENCH = "bench"  # scheduled but not in an active slot
MUTED = "muted"  # informational only
STRONG = "strong"  # emphasis

PLAIN = "plain"
INFO = "info"
WARNING = "warning"
ALERT = "alert"
HEADING = "heading"


def diverging(value: Any, scale: float) -> float | None:
    """Tone of a signed value that saturates at +-scale (None if missing)."""
    if scale <= 0 or pd.isna(value):
        return None
    return float(max(-1.0, min(1.0, value / scale)))


def heat(rate: Any) -> float | None:
    """Tone of a 0..1 rate: 0 bad, 0.5 neutral, 1 good."""
    return diverging(rate - 0.5, 0.5)


def column_tones(frame: pd.DataFrame,
                 rules: dict[str, Callable[[Any], Tone]]) -> pd.DataFrame:
    """Per-cell tones from one rule per column (value -> tone); rules for
    columns the frame lacks are ignored."""
    return pd.DataFrame({col: [rule(value) for value in frame[col]]
                         for col, rule in rules.items() if col in frame},
                        index=frame.index, dtype=object)


@dataclass
class TableView:
    title: str
    frame: pd.DataFrame  # display values; the index is the row label
    tones: pd.DataFrame | None = None  # Tone per cell, row-aligned with frame
    footer: pd.DataFrame | None = None  # summary rows below the body
    muted: tuple[str, ...] = ()  # columns with a de-emphasized header
    key: str = ""  # identifies the table within its view


@dataclass(frozen=True)
class Span:
    text: str
    tone: str | None = None  # tags


@dataclass
class Note:
    spans: list[Span]
    level: str = PLAIN
    space_before: bool = False


def note(*parts: str | Span, level: str = PLAIN,
         space_before: bool = False) -> Note:
    return Note([part if isinstance(part, Span) else Span(part)
                 for part in parts], level, space_before)


@dataclass
class TextBlock:
    """Text to show verbatim (e.g. for copy-pasting)."""
    text: str


@dataclass
class FigureBlock:
    kind: str  # built by plots.<kind>_figure
    prefix: str  # file name stem when saved
    inputs: dict[str, Any]  # that function's keyword arguments


Block = TableView | Note | TextBlock | FigureBlock


@dataclass
class View:
    blocks: list[Block] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
