from __future__ import annotations

import re


def normalize_mobile(value: str | None) -> str | None:
    """Accept unambiguous Philippine mobile or already-E.164 numbers only."""
    if not value:
        return None
    raw = value.strip()
    if re.search(r"[^+0-9 .()-]", raw) or raw.count("+") > 1 or ("+" in raw and not raw.startswith("+")):
        return None
    compact = re.sub(r"[ .()-]", "", raw)
    if re.fullmatch(r"09\d{9}", compact):
        return "+63" + compact[1:]
    if re.fullmatch(r"639\d{9}", compact):
        return "+" + compact
    if re.fullmatch(r"\+[1-9]\d{7,14}", compact):
        return compact
    return None


def normalize_ph_mobile(value: str | None) -> str | None:
    """Brevo transactional SMS accepts only Philippine mobile destinations."""
    normalized = normalize_mobile(value)
    return normalized if normalized and re.fullmatch(r"\+639\d{9}", normalized) else None
