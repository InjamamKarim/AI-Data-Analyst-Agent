from backend.schema.context import FULL_INSTRUCTION, build_schema_context
from backend.schema.profile import build_profile
from backend.schema.catalog import get_catalog


QUESTION = "What was completed-order revenue in Q3 2024?"


def test_schema_filter_drops_unrelated_tables():
    _text, names = build_schema_context(QUESTION, filter_schema=True, mode="full")
    assert "order_items" in names
    assert "orders" in names
    assert "customers" in names
    assert "products" in names
    assert "hr_employees" not in names
    assert "marketing_campaigns" not in names
    assert "support_tickets" not in names


def test_filtering_shrinks_the_prompt():
    full, _full_names = build_schema_context(QUESTION, filter_schema=False, mode="full")
    filtered, _names = build_schema_context(QUESTION, filter_schema=True, mode="full")
    assert len(filtered) < len(full)
    assert "hr_employees" in full
    assert "hr_employees" not in filtered


def test_context_modes_change_the_prompt():
    semantic, _names = build_schema_context(QUESTION, filter_schema=True, mode="semantic")
    tool, _empty = build_schema_context(QUESTION, filter_schema=True, mode="tool")
    views, _view_names = build_schema_context(QUESTION, filter_schema=True, mode="views")
    assert "Business rules:" in semantic
    assert FULL_INSTRUCTION not in semantic
    assert "fetch_context" in tool
    assert "Business rules:" not in tool
    assert "quarterly_revenue" in views
    assert "completed_lines" in views


def test_profile_reports_measured_ranges():
    orders = next(table for table in get_catalog() if table.name == "orders")
    profile = build_profile([orders])
    assert "orders:" in profile
    assert "2024" in profile
    assert "completed" in profile
