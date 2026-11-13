"""Rich console rendering helpers."""
import math

import pandas as pd
from rich.console import Console
from rich.table import Table

from ..views.model import (
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
    cell_text,
    cell_texts,
)

console = Console()

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


def print_df(df: pd.DataFrame, title: str,
             footer: pd.DataFrame | None = None,
             widths: dict[str, int] | None = None,
             header_styles: dict[str, str] | None = None,
             cell_styles: pd.DataFrame | None = None) -> None:
    """Render a DataFrame as a rich table, index shown as '#'.

    footer rows are appended dim in a separate section.
    widths maps column name -> minimum content width.
    header_styles maps column name -> extra style layered on the header.
    cell_styles (same rows, subset of columns) holds the style strings of
    the cells.
    """
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

    def cell(i: int, col: str, text: str) -> str:
        style = ""
        if cell_styles is not None and col in cell_styles.columns:
            # by position: row labels may repeat
            style = cell_styles[col].iat[i]
        return f"[{style}]{text}[/]" if style else text

    for i, (idx, texts) in enumerate(zip(df.index, cell_texts(df))):
        table.add_row(str(idx), *(cell(i, col, text)
                                  for col, text in zip(df.columns, texts)))

    if footer is not None:
        table.add_section()
        for idx, row in footer.iterrows():
            table.add_row(str(idx), *(cell_text(row.get(col))
                                      for col in df.columns), style="italic dim")

    console.print()
    console.print(table)
