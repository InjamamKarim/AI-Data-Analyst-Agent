"""Drop tables that the question does not mention, then pull in parent keys."""

from __future__ import annotations

import re

from backend.schema.catalog import Table

_STOP = {
    "a", "an", "the", "of", "by", "as", "for", "in", "on", "and", "or", "to",
    "what", "was", "were", "is", "are", "show", "me", "how", "many", "from",
    "with", "all", "did", "does", "do", "that", "this", "into", "per", "than",
    "at", "least", "most", "plot", "chart", "graph", "please",
}


def tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {token for token in tokens if token not in _STOP and len(token) > 1}


def select_tables(question: str, tables: list[Table], enabled: bool) -> list[Table]:
    if not enabled:
        return list(tables)
    question_tokens = tokenize(question)
    scored: list[tuple[int, Table]] = []
    for table in tables:
        if table.is_view:
            continue
        haystack = " ".join(
            [table.name.replace("_", " "), table.description, table.keywords]
            + [column.name.replace("_", " ") for column in table.columns]
        )
        score = len(question_tokens & tokenize(haystack))
        if table.name.replace("_", " ") in (question or "").lower():
            score += 3
        scored.append((score, table))
    kept = [table for score, table in scored if score > 0]
    if not kept:
        return list(tables)
    by_name = {table.name: table for table in tables if not table.is_view}
    names = {table.name for table in kept}
    for table in list(kept):
        for _column, parent in table.foreign_keys:
            if parent not in names and parent in by_name:
                kept.append(by_name[parent])
                names.add(parent)
    return kept
