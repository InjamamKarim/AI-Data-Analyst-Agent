"""Execution accuracy and a simplified valid-efficiency score.

VES here is the guide's idea in a form we can compute without the official BIRD
scorer: a correct result scores sqrt(gold_time / predicted_time), capped at 1.
A wrong result scores 0. Faster than gold does not score above 1.
"""

from __future__ import annotations

import math
from typing import Any


def normalize_value(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 2)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value)
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    if number.is_integer() and "." not in text and "e" not in text.lower():
        return int(number)
    return round(number, 2)


def row_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(normalize_value(value) for value in row.values())


def rows_equal(actual: list[dict] | None, expected: list[dict] | None, ordered: bool = False) -> bool:
    left = [row_signature(row) for row in actual or []]
    right = [row_signature(row) for row in expected or []]
    if len(left) != len(right):
        return False
    if ordered:
        return left == right
    return sorted(left, key=str) == sorted(right, key=str)


def valid_efficiency_score(correct: bool, gold_seconds: float, predicted_seconds: float) -> float:
    if not correct:
        return 0.0
    if predicted_seconds <= 0:
        return 1.0
    ratio = max(gold_seconds, 1e-6) / predicted_seconds
    return round(max(0.0, min(1.0, math.sqrt(ratio))), 4)


def safe_sql_rate(decisions: list[bool]) -> float:
    if not decisions:
        return 1.0
    return round(sum(1 for item in decisions if item) / len(decisions), 4)
