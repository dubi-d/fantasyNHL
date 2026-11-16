"""The figures of the views as PNG, rendered once per content."""
import hashlib
import threading
from collections import OrderedDict
from typing import Any

import pandas as pd

from ..views.model import FigureBlock

KEPT = 32  # rendered figures held in memory

_lock = threading.Lock()  # pyplot keeps global state
_rendered: OrderedDict[str, bytes] = OrderedDict()


def _feed(digest: Any, value: Any) -> None:
    if isinstance(value, (pd.DataFrame, pd.Series)):
        digest.update(value.to_csv().encode())
    elif isinstance(value, dict):  # in order: it is the order drawn
        for key, item in value.items():
            _feed(digest, key)
            _feed(digest, item)
    elif isinstance(value, (set, frozenset)):
        digest.update(repr(sorted(value)).encode())
    elif isinstance(value, (list, tuple)):
        for item in value:
            _feed(digest, item)
    else:
        digest.update(repr(value).encode())
    digest.update(b"\0")


def fingerprint(block: FigureBlock) -> str:
    """Identifies what a figure shows: equal for equal inputs."""
    digest = hashlib.sha1(block.kind.encode(), usedforsecurity=False)
    _feed(digest, block.inputs)
    return digest.hexdigest()[:16]


def render(block: FigureBlock, mark: str) -> bytes:
    """
    :param mark: the block's fingerprint
    """
    with _lock:
        png = _rendered.get(mark)
        if png is None:
            from .. import plots  # deferred: matplotlib import is slow
            png = plots.render_png(block.kind, block.inputs)
            _rendered[mark] = png
            while len(_rendered) > KEPT:
                _rendered.popitem(last=False)
        else:
            _rendered.move_to_end(mark)
        return png
