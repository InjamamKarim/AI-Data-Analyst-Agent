"""Neutralize spreadsheet formulas in uploaded CSV cells."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

_NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_FORMULA_STARTS = ("=", "+", "@", "\t", "\r")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_COLUMNS = 50
MAX_ROWS = 50_000


def sanitize_cell(value: Any) -> Any:
    if value is None:
        return value
    try:
        if pd.isna(value):
            return value
    except TypeError:
        pass
    if not isinstance(value, str):
        return value
    text = value.replace("\x00", "")
    stripped = text.lstrip(" \t")
    if not stripped:
        return text
    if stripped[0] in _FORMULA_STARTS:
        return "'" + text
    if stripped[0] == "-" and _NUMBER.match(stripped) is None:
        return "'" + text
    return text


def sanitize_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    if cleaned.shape[1] > MAX_COLUMNS:
        cleaned = cleaned.iloc[:, :MAX_COLUMNS]
    if len(cleaned) > MAX_ROWS:
        cleaned = cleaned.iloc[:MAX_ROWS, :]
    columns = []
    for index, name in enumerate(cleaned.columns):
        label = sanitize_cell(str(name)).strip().strip("'")
        label = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_")
        if not label or label[0].isdigit():
            label = f"col_{index + 1}_{label}".strip("_")
        columns.append(label[:64] or f"col_{index + 1}")
    cleaned.columns = _dedupe(columns)
    for column in cleaned.columns:
        cleaned[column] = cleaned[column].map(sanitize_cell)
    return cleaned


def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for name in names:
        count = seen.get(name, 0)
        seen[name] = count + 1
        result.append(name if count == 0 else f"{name}_{count + 1}")
    return result
