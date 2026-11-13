"""Views as JSON: the response models and the conversion from a View."""
import math
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, create_model

from ..views.model import (
    FigureBlock,
    Note,
    TableView,
    TextBlock,
    View,
    cell_text,
    cell_texts,
)

Scalar = float | int | str | bool | None


class Cell(BaseModel):
    text: str  # as the terminal shows it
    value: Scalar  # what is shown, unformatted; None if missing
    tone: float | str | None  # diverging intensity in [-1, 1] or tags


class Column(BaseModel):
    key: str  # identifies the column within its table
    name: str
    type: Literal["number", "text"]  # what the values of its cells are
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


class FrameData(BaseModel):
    type: Literal["frame"] = "frame"
    index: list[Scalar]  # row labels
    columns: list[str]
    rows: list[list[Scalar]]


class SeriesData(BaseModel):
    type: Literal["series"] = "series"
    index: list[Scalar]
    values: list[Scalar]


FigureValue = (FrameData | SeriesData | dict[str, SeriesData] | list[Scalar]
               | Scalar)


class FigureBlockModel(BaseModel):
    type: Literal["figure"] = "figure"
    kind: str  # which chart: what ``data`` holds depends on it
    title: str
    url: str  # the figure as PNG
    data: dict[str, FigureValue]  # what the figure is drawn from, by name


class ViewModel(BaseModel):
    blocks: list[TableBlock | NoteBlock | TextBlockModel | FigureBlockModel]


def view_model(meta: type[BaseModel] | None) -> type[ViewModel]:
    """The response model of a view whose ``meta`` follows a model."""
    if meta is None:
        return ViewModel
    return create_model(meta.__name__.removesuffix("Meta") + "View",
                        __base__=ViewModel, meta=(meta, ...))


def _value(value: Any) -> Scalar:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if isinstance(value, (bool, int, float, str)) else str(value)


def _tone(tone: Any) -> float | str | None:
    return None if pd.isna(tone) else tone if isinstance(tone, str) else float(tone)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _columns(table: TableView, values: list[list[Scalar]]) -> list[Column]:
    columns, keys = [], set()
    for j, col in enumerate(table.frame.columns):
        key = str(col)
        while key in keys:  # repeated names stay tellable apart
            key += "'"
        keys.add(key)
        present = [row[j] for row in values if row[j] is not None]
        columns.append(Column(
            key=key, name=str(col),
            type="number" if present and all(map(_is_number, present))
            else "text",
            align="left" if table.frame.iloc[:, j].dtype == object
            else "right",
            muted=str(col) in table.muted))
    return columns


def _table(table: TableView) -> TableBlock:
    frame, tones = table.frame, table.tones
    toned = set() if tones is None else set(tones.columns)
    values = [[_value(value) for value in row]
              for row in frame.itertuples(index=False, name=None)]
    rows = [
        Row(label=str(label), cells=[
            Cell(text=text, value=value,
                 tone=_tone(tones[col].iat[i]) if col in toned else None)
            for col, text, value in zip(frame.columns, texts, values[i])])
        for i, (label, texts) in enumerate(zip(frame.index,
                                               cell_texts(frame)))]
    footer = []
    if table.footer is not None:
        for label, row in table.footer.iterrows():
            footer.append(Row(label=str(label), cells=[
                Cell(text=cell_text(row.get(col)), value=_value(row.get(col)),
                     tone=None) for col in frame.columns]))
    return TableBlock(key=table.key, title=table.title, rows=rows,
                      footer=footer, columns=_columns(table, values))


def _figure_value(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return FrameData(
            index=[_value(label) for label in value.index],
            columns=[str(col) for col in value.columns],
            rows=[[_value(cell) for cell in row]
                  for row in value.itertuples(index=False, name=None)])
    if isinstance(value, pd.Series):
        return SeriesData(index=[_value(label) for label in value.index],
                          values=[_value(cell) for cell in value])
    if isinstance(value, dict):
        return {str(key): _figure_value(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(_value(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return _value(value)


def serialize_view(view: View,
                   figure_url: Callable[[int, FigureBlock], str] | None = None,
                   model: type[ViewModel] = ViewModel) -> ViewModel:
    """
    :param figure_url: where the n-th figure of the view is served as PNG
    :param model: the response model (see view_model)
    """
    blocks: list = []
    figures = 0
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
                kind=block.kind, title=block.inputs["title"],
                url=figure_url(figures, block) if figure_url else "",
                data={name: _figure_value(value)
                      for name, value in block.inputs.items()
                      if name != "title"}))
            figures += 1
    if model is ViewModel:
        return ViewModel(blocks=blocks)
    return model(blocks=blocks, meta=view.meta)
