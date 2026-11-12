"""Four context layouts for the documentation ablation."""

from __future__ import annotations

from backend.schema.catalog import (
    BUSINESS_RULES,
    FULL_INSTRUCTION,
    TOOL_INSTRUCTION,
    VIEW_HINT,
    Table,
    get_catalog,
)
from backend.schema.filter import select_tables


def build_schema_context(question: str, *, filter_schema: bool, mode: str = "full") -> tuple[str, list[str]]:
    catalog = get_catalog()
    if mode == "tool":
        return TOOL_INSTRUCTION, []
    selected = select_tables(question, catalog, enabled=filter_schema)
    views = [table for table in catalog if table.is_view]
    if mode == "views":
        body = _render(selected, views)
        return f"{BUSINESS_RULES}\n{VIEW_HINT}\n\n{body}".strip(), [table.name for table in selected]
    if mode == "semantic":
        body = _render(selected, [])
        return f"{BUSINESS_RULES}\n{body}".strip(), [table.name for table in selected]
    body = _render(selected, [])
    return f"{FULL_INSTRUCTION}\n{BUSINESS_RULES}\n{body}".strip(), [table.name for table in selected]


def semantic_document(question: str, filter_schema: bool) -> str:
    text, _names = build_schema_context(question, filter_schema=filter_schema, mode="semantic")
    return text


def _render(tables: list[Table], views: list[Table]) -> str:
    blocks = []
    if views:
        blocks.append("Views:")
        blocks.extend(_table_block(table) for table in views)
    blocks.append("Tables:")
    blocks.extend(_table_block(table) for table in tables)
    return "\n".join(blocks)


def _table_block(table: Table) -> str:
    columns = ", ".join(f"{column.name} {column.type}".strip() for column in table.columns)
    parents = ", ".join(f"{local}->{parent}" for local, parent in table.foreign_keys) or "none"
    kind = "view" if table.is_view else "table"
    return (
        f"- {table.name} ({kind}): {columns}\n"
        f"  keys: {parents}\n"
        f"  meaning: {table.description}"
    )
