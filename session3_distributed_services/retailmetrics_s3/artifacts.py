from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


def _atomic_replace(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value: Any) -> None:
    _atomic_replace(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def write_text(path: Path, value: str) -> None:
    _atomic_replace(path, value)


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    values = list(rows)
    if not values:
        raise ValueError(f"Cannot write empty CSV artifact: {path.name}")
    from io import StringIO
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(values[0]))
    writer.writeheader()
    writer.writerows(values)
    _atomic_replace(path, buffer.getvalue())
