from __future__ import annotations

import datetime as dt
from pathlib import Path

from ..artifacts import _atomic_replace


def save_transcript(results: Path, text: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = results / f"transcript-{stamp}.txt"
    _atomic_replace(path, text.rstrip() + "\n")
    return path

