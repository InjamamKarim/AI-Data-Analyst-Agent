"""Small, deterministic data profile injected before SQL generation (ablation arm E)."""

from __future__ import annotations

import re

from sqlalchemy import text

from backend.db.connection import get_reader_engine
from backend.schema.catalog import Table

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Unsafe identifier: {name}")
    return f'"{name}"'


def build_profile(tables: list[Table], limit_tables: int = 6) -> str:
    engine = get_reader_engine()
    lines = ["Data profile (measured from the database, not guessed):"]
    shown = 0
    with engine.connect() as conn:
        for table in tables:
            if table.is_view or shown >= limit_tables:
                continue
            shown += 1
            ident = quote_ident(table.name)
            count = conn.execute(text(f"SELECT COUNT(*) FROM {ident}")).scalar()
            lines.append(f"- {table.name}: {count} rows")
            for column in table.columns:
                if _is_date(column.name):
                    col = quote_ident(column.name)
                    low, high = conn.execute(
                        text(f"SELECT MIN({col}), MAX({col}) FROM {ident}")
                    ).one()
                    lines.append(f"  - {column.name} ranges from {low} to {high}")
                elif _is_category(column.name) and column.name.endswith("_id") is False:
                    col = quote_ident(column.name)
                    distinct = conn.execute(
                        text(f"SELECT COUNT(DISTINCT {col}) FROM {ident}")
                    ).scalar()
                    if distinct is not None and int(distinct) <= 12:
                        top = conn.execute(
                            text(
                                f"SELECT {col} AS value, COUNT(*) AS n FROM {ident} "
                                f"GROUP BY {col} ORDER BY n DESC, {col} ASC LIMIT 6"
                            )
                        ).fetchall()
                        rendered = ", ".join(f"{row[0]} ({row[1]})" for row in top)
                        lines.append(f"  - {column.name} values: {rendered}")
    if shown == 0:
        return ""
    return "\n".join(lines)


def _is_date(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith("_date") or lowered.endswith("_at") or lowered == "date"


def _is_category(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"region", "segment", "status", "channel", "category", "priority", "department"}
