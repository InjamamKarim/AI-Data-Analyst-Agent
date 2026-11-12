"""Live catalog plus the business meaning of the sample warehouse."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import inspect

from backend.db.connection import get_reader_engine

TABLE_DOCS: dict[str, dict[str, str]] = {
    "customers": {
        "description": (
            "Customer dimension. region is North, South, East, or West. "
            "segment is Enterprise, SMB, or Consumer. signup_date is the account open date."
        ),
        "keywords": "customer region segment enterprise smb consumer signup account",
    },
    "products": {
        "description": (
            "Product dimension. category is Hardware, Software, or Services. "
            "unit_price is the catalog list price, not the discounted selling price."
        ),
        "keywords": "product category hardware software services price sku catalog",
    },
    "orders": {
        "description": (
            "Order header. status is completed, pending, cancelled, or returned. "
            "channel is web, partner, or direct. order_date is the purchase date. "
            "Revenue questions use completed orders only. Quarters and months come from order_date."
        ),
        "keywords": "order revenue sales purchase channel status date quarter monthly q1 q2 q3 q4",
    },
    "order_items": {
        "description": (
            "Order lines. quantity, unit_price, and discount are stored on the line. "
            "Line revenue is quantity * unit_price * (1 - discount). discount is a fraction, so 0.2 is 20 percent."
        ),
        "keywords": "revenue line quantity discount price item units sold",
    },
    "hr_employees": {
        "description": "Internal staffing roster. Salary, department, and hire date.",
        "keywords": "employee salary department hired staff payroll",
    },
    "marketing_campaigns": {
        "description": "Advertising spend and campaign dates.",
        "keywords": "campaign advertising spend ads promotion budget",
    },
    "support_tickets": {
        "description": "Support workload. priority and status describe tickets, not orders.",
        "keywords": "ticket support priority helpdesk incident",
    },
    "uploaded_csv": {
        "description": "Latest analyst CSV upload. Formula characters were neutralized before load.",
        "keywords": "upload csv file spreadsheet imported",
    },
}

BUSINESS_RULES = """Business rules:
- Revenue means completed orders only. Pending, cancelled, and returned orders are excluded.
- Line revenue = quantity * unit_price * (1 - discount), using the price and discount stored on order_items.
- product.unit_price is the list price. Do not use it as revenue when order_items.unit_price is available.
- Q1 is January-March, Q2 April-June, Q3 July-September, Q4 October-December.
- Dates are ISO strings (YYYY-MM-DD). Compare them as text ranges.
- Staffing rosters and advertising spend are not sales. Do not use them for revenue.
"""

VIEW_HINT = (
    "Prefer completed_lines and quarterly_revenue when they answer the question. "
    "completed_lines already filters to completed orders and exposes line_revenue. "
    "Fall back to base tables when the view is missing a column you need."
)

FULL_INSTRUCTION = "Use only the tables and columns listed below. Do not invent tables."
TOOL_INSTRUCTION = (
    "Semantic documentation is not in this prompt. "
    "Set next_step to fetch_context before writing SQL or Python."
)


@dataclass
class Column:
    name: str
    type: str


@dataclass
class Table:
    name: str
    columns: list[Column]
    description: str = ""
    keywords: str = ""
    foreign_keys: list[tuple[str, str]] = field(default_factory=list)
    is_view: bool = False


_cache: list[Table] | None = None


def get_catalog(force: bool = False) -> list[Table]:
    global _cache
    if _cache is None or force:
        _cache = _load_catalog()
    return _cache


def invalidate_catalog() -> None:
    global _cache
    _cache = None


def _load_catalog() -> list[Table]:
    engine = get_reader_engine()
    info = inspect(engine)
    tables: list[Table] = []
    names = list(info.get_table_names()) + [name for name in info.get_view_names() if name not in info.get_table_names()]
    view_names = set(info.get_view_names())
    for name in names:
        docs = TABLE_DOCS.get(name, {})
        columns = [
            Column(name=col["name"], type=str(col.get("type", "")))
            for col in info.get_columns(name)
        ]
        foreign_keys: list[tuple[str, str]] = []
        if name not in view_names:
            for fk in info.get_foreign_keys(name):
                parent = fk.get("referred_table")
                local = (fk.get("constrained_columns") or [""])[0]
                if parent:
                    foreign_keys.append((local, parent))
        tables.append(
            Table(
                name=name,
                columns=columns,
                description=docs.get("description", "No extra description."),
                keywords=docs.get("keywords", ""),
                foreign_keys=foreign_keys,
                is_view=name in view_names,
            )
        )
    return tables
