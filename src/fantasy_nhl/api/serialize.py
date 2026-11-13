"""Views as JSON: the response models and the conversion from a View."""
import math
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from ..views.model import FigureBlock, Note, TableView, TextBlock, View


class Cell(BaseModel):
    text: str  # as the terminal shows it
    value: float | int | str | bool | None  # unformatted, None if missing
    tone: float | str | None  # diverging intensity in [-1, 1] or tags


class Column(BaseModel):
    name: str
    align: Literal["left", "right"]
    muted: bool


class Row(BaseModel):
    label: str
    cells: list[Cell]


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    key: str
    title: str
    columns: list[Column]
    rows: list[Row]
    footer: list[Row]


class SpanModel(BaseModel):
    text: str
    tone: str | None


class NoteBlock(BaseModel):
    type: Literal["note"] = "note"
    level: str
    spans: list[SpanModel]
    space_before: bool


class TextBlockModel(BaseModel):
    type: Literal["text"] = "text"
    text: str


class FigureBlockModel(BaseModel):
    type: Literal["figure"] = "figure"
    kind: str
    title: str
    url: str  # the figure as PNG


class ViewModel(BaseModel):
    blocks: list[TableBlock | NoteBlock | TextBlockModel | FigureBlockModel]
    meta: dict[str, Any]


def _value(value: Any) -> float | int | str | bool | None:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if isinstance(value, (bool, int, float, str)) else str(value)


def _tone(tone: Any) -> float | str | None:
    return None if pd.isna(tone) else tone if isinstance(tone, str) else float(tone)


def _text(value: Any) -> str:
    return "" if pd.isna(value) else str(value)


def _table(table: TableView) -> TableBlock:
    frame, tones = table.frame, table.tones
    toned = set() if tones is None else set(tones.columns)
    rows = []
    # row-wise like the terminal renderer, so numbers format the same way
    for i, (label, row) in enumerate(frame.iterrows()):
        rows.append(Row(label=str(label), cells=[
            Cell(text=_text(row[col]), value=_value(row[col]),
                 tone=_tone(tones[col].iat[i]) if col in toned else None)
            for col in frame.columns]))
    footer = []
    if table.footer is not None:
        for label, row in table.footer.iterrows():
            footer.append(Row(label=str(label), cells=[
                Cell(text=_text(row.get(col)), value=_value(row.get(col)),
                     tone=None) for col in frame.columns]))
    return TableBlock(
        key=table.key, title=table.title, rows=rows, footer=footer,
        columns=[Column(name=str(col),
                        align="left" if frame[col].dtype == object else "right",
                        muted=str(col) in table.muted)
                 for col in frame.columns])


def serialize_view(view: View, figure_url: str) -> ViewModel:
    """
    :param figure_url: where the view's figure (if any) is served as PNG
    """
    blocks: list = []
    for block in view.blocks:
        if isinstance(block, TableView):
            blocks.append(_table(block))
        elif isinstance(block, Note):
            blocks.append(NoteBlock(
                level=block.level, space_before=block.space_before,
                spans=[SpanModel(text=span.text, tone=span.tone)
                       for span in block.spans]))
        elif isinstance(block, TextBlock):
            blocks.append(TextBlockModel(text=block.text))
        elif isinstance(block, FigureBlock):
            blocks.append(FigureBlockModel(
                kind=block.kind, title=block.inputs["title"], url=figure_url))
    return ViewModel(blocks=blocks, meta=view.meta)
