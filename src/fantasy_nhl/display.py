"""Rich console rendering helpers."""
import math
from collections.abc import Callable

import pandas as pd
from rich.console import Console
from rich.table import Table

from .views.model import (
    ALERT,
    BAD,
    BENCH,
    DANGER,
    EVEN,
    GOOD,
    HEADING,
    INFO,
    MUTED,
    STRONG,
    WARN,
    WARNING,
    Note,
    Tone,
)

console = Console()

# style callback: cell value -> rich style string
StyleFn = Callable[[object], str]

_NEUTRAL = (60, 60, 60)
_GREEN = (0, 135, 0)
_RED = (175, 0, 0)

_TAG_STYLES = {GOOD: "bold green", BAD: "bold red", EVEN: "bold yellow",
               WARN: "yellow", DANGER: "red", BENCH: "orange3", MUTED: "dim",
               STRONG: "bold"}
_LEVEL_STYLES = {INFO: "dim", WARNING: "yellow", ALERT: "bold magenta",
                 HEADING: "bold"}


def _blend(t: float, lo: tuple[int, int, int], hi: tuple[int, int, int]) -> str:
    channels = (round(a + t * (b - a)) for a, b in zip(lo, hi))
    return "white on rgb({},{},{})".format(*channels)


def tone_style(tone: Tone) -> str:
    """Rich style of a view tone (gradient background or tag styles)."""
    if tone is None or (isinstance(tone, float) and math.isnan(tone)):
        return ""
    if isinstance(tone, str):
        return " ".join(_TAG_STYLES[tag] for tag in tone.split())
    return _blend(abs(tone), _NEUTRAL, _GREEN if tone >= 0 else _RED)


def note_markup(note: Note) -> tuple[str, str | None]:
    """Rich markup and overall style of a view note."""
    text = "".join(f"[{tone_style(span.tone)}]{span.text}[/]" if span.tone
                   else span.text for span in note.spans)
    return ("\n" if note.space_before else "") + text, _LEVEL_STYLES.get(note.level)


def diverging_style(value: float, scale: float) -> str:
    """Gradient background: neutral at 0, green toward +scale, red toward -scale."""
    if scale <= 0 or pd.isna(value):
        return ""
    t = min(abs(value) / scale, 1.0)
    return _blend(t, _NEUTRAL, _GREEN if value >= 0 else _RED)


def heatmap_style(rate: float) -> str:
    """Win-rate gradient: 0.0 red, 0.5 neutral, 1.0 green."""
    return diverging_style(rate - 0.5, 0.5)


def result_style(result: str) -> str:
    return {"W": "bold green", "L": "bold red", "T": "bold yellow"}.get(result, "")


def print_df(df: pd.DataFrame, title: str,
             styles: dict[str, StyleFn] | None = None,
             footer: pd.DataFrame | None = None,
             widths: dict[str, int] | None = None,
             header_styles: dict[str, str] | None = None,
             cell_styles: pd.DataFrame | None = None) -> None:
    """Render a DataFrame as a rich table, index shown as '#'.

    styles maps column name -> (value -> style string) for per-cell styling.
    footer rows are appended dim in a separate section.
    widths maps column name -> minimum content width.
    header_styles maps column name -> extra style layered on the header.
    cell_styles (same rows, subset of columns) holds style strings that
    override styles where present (style a cell by another table's value).
    """
    styles = styles or {}
    widths = widths or {}
    header_styles = header_styles or {}
    table = Table(title=title, title_style="bold", title_justify="left",
                  header_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    for col in df.columns:
        justify = "left" if df[col].dtype == object else "right"
        table.add_column(str(col), justify=justify,
                         min_width=widths.get(str(col)),
                         header_style=header_styles.get(str(col)))

    def cell(i: int, col: str, value: object) -> str:
        style = styles.get(col, lambda _: "")(value)
        if cell_styles is not None and col in cell_styles.columns:
            # by position: row labels may repeat
            style = cell_styles[col].iat[i] or style
        text = "" if pd.isna(value) else str(value)
        return f"[{style}]{text}[/]" if style else text

    for i, (idx, row) in enumerate(df.iterrows()):
        table.add_row(str(idx), *(cell(i, col, row[col])
                                  for col in df.columns))

    if footer is not None:
        table.add_section()
        for idx, row in footer.iterrows():
            table.add_row(str(idx), *("" if pd.isna(row.get(col)) else str(row.get(col, ""))
                                      for col in df.columns), style="italic dim")

    console.print()
    console.print(table)
