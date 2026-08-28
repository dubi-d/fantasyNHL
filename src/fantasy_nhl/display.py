"""Rich console rendering helpers."""
from collections.abc import Callable

import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

# style callback: cell value -> rich style string
StyleFn = Callable[[object], str]

_NEUTRAL = (60, 60, 60)
_GREEN = (0, 135, 0)
_RED = (175, 0, 0)


def _blend(t: float, lo: tuple[int, int, int], hi: tuple[int, int, int]) -> str:
    channels = (round(a + t * (b - a)) for a, b in zip(lo, hi))
    return "white on rgb({},{},{})".format(*channels)


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
             footer: pd.DataFrame | None = None) -> None:
    """Render a DataFrame as a rich table, index shown as '#'.

    styles maps column name -> (value -> style string) for per-cell styling.
    footer rows are appended dim in a separate section.
    """
    styles = styles or {}
    table = Table(title=title, title_style="bold", title_justify="left",
                  header_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    for col in df.columns:
        justify = "left" if df[col].dtype == object else "right"
        table.add_column(str(col), justify=justify)

    def cell(col: str, value: object) -> str:
        style = styles.get(col, lambda _: "")(value)
        text = "" if pd.isna(value) else str(value)
        return f"[{style}]{text}[/]" if style else text

    for idx, row in df.iterrows():
        table.add_row(str(idx), *(cell(col, row[col]) for col in df.columns))

    if footer is not None:
        table.add_section()
        for idx, row in footer.iterrows():
            table.add_row(str(idx), *("" if pd.isna(row.get(col)) else str(row.get(col, ""))
                                      for col in df.columns), style="italic dim")

    console.print()
    console.print(table)
