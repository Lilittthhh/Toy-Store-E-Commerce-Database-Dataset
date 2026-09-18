from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable


CENT = Decimal("0.01")


def decimal_to_cents(value: Decimal | int | str | None) -> int:
    """Convert PostgreSQL NUMERIC money to cents without binary float."""
    if value is None:
        return 0
    if isinstance(value, float):
        raise TypeError("Monetary conversion must not receive binary float")
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    return int((amount.quantize(CENT, rounding=ROUND_HALF_UP) * 100).to_integral_exact())


def cents_to_decimal(value: int) -> Decimal:
    return Decimal(value) / Decimal(100)


def datetime_to_iso(value: datetime | str) -> str:
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def compact_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]
