"""Read-only SQL gate.

The database role is the first control. This parser is the second: it rejects
anything that is not a single SELECT/WITH statement, including comment and
string tricks that try to hide a write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Words that must never survive as real SQL tokens. REPLACE is intentionally
# absent: SQLite's REPLACE() function is not a write.
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|MERGE|COPY|CALL|EXECUTE|EXEC|"
    r"INTO|LOAD_EXTENSION)\b",
    re.IGNORECASE,
)

_DESTRUCTIVE_REQUEST = re.compile(
    r"\b("
    r"delete\s+(all\s+)?(the\s+)?(rows|users|records|data|tables?|database)|"
    r"drop\s+(the\s+)?(table|database|schema)|"
    r"truncate\s+|"
    r"wipe\s+(the\s+)?(database|table|data)|"
    r"destroy\s+(the\s+)?(database|table|data)|"
    r"remove\s+all\s+(users|rows|records|data)"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SQLDecision:
    allowed: bool
    reason: str
    statement: str


def user_requests_destruction(question: str) -> bool:
    return bool(_DESTRUCTIVE_REQUEST.search(question or ""))


def review_sql(query: str) -> SQLDecision:
    raw = (query or "").strip()
    if not raw:
        return SQLDecision(False, "BLOCKED: empty SQL is not permitted.", "")

    cleaned, masked = _strip_comments_and_mask_strings(raw)
    pieces = [part.strip() for part in cleaned.split(";") if part.strip()]
    if len(pieces) != 1:
        return SQLDecision(False, "BLOCKED: only a single SQL statement is permitted.", "")

    statement = pieces[0]
    masked_pieces = [part.strip() for part in masked.split(";") if part.strip()]
    masked_statement = masked_pieces[0] if masked_pieces else statement

    if _FORBIDDEN.search(masked_statement):
        return SQLDecision(
            False,
            "BLOCKED: Destructive operations are not permitted.",
            "",
        )

    head = masked_statement.lstrip("(").strip().split(None, 1)[0].upper() if masked_statement.strip() else ""
    if head not in {"SELECT", "WITH"}:
        return SQLDecision(False, "BLOCKED: only SELECT statements are permitted.", "")
    if head == "WITH" and not re.search(r"\bSELECT\b", masked_statement, re.IGNORECASE):
        return SQLDecision(False, "BLOCKED: a WITH query must contain SELECT.", "")

    return SQLDecision(True, "ok", statement)


def _strip_comments_and_mask_strings(sql: str) -> tuple[str, str]:
    """Return comment-free SQL and a copy whose string literals cannot hide keywords."""
    cleaned: list[str] = []
    masked: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if ch == "-" and nxt == "-":
            i += 2
            while i < n and sql[i] not in "\n\r":
                i += 1
            cleaned.append(" ")
            masked.append(" ")
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            cleaned.append(" ")
            masked.append(" ")
            continue
        if ch == "'":
            cleaned.append(ch)
            masked.append("'")
            i += 1
            while i < n:
                if sql[i] == "'" and i + 1 < n and sql[i + 1] == "'":
                    cleaned.append("''")
                    i += 2
                    continue
                if sql[i] == "'":
                    cleaned.append("'")
                    masked.append("'")
                    i += 1
                    break
                cleaned.append(sql[i])
                i += 1
            continue
        cleaned.append(ch)
        masked.append(ch)
        i += 1
    return "".join(cleaned), "".join(masked)
