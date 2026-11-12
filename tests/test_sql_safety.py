import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.db.connection import get_reader_engine
from backend.security.sql_guard import review_sql, user_requests_destruction


def test_select_is_allowed():
    decision = review_sql("SELECT name FROM products WHERE name = 'Delete me'")
    assert decision.allowed
    assert "SELECT name FROM products" in decision.statement


def test_keyword_hidden_in_a_string_is_not_a_write():
    decision = review_sql("SELECT 'DROP TABLE orders' AS example")
    assert decision.allowed


def test_comment_cannot_hide_a_second_statement():
    decision = review_sql("SELECT 1; -- keep\nDROP TABLE orders")
    assert not decision.allowed
    assert "BLOCKED" in decision.reason


def test_block_comment_cannot_hide_drop():
    decision = review_sql("/* harmless */ DELETE FROM orders")
    assert not decision.allowed


def test_destructive_keywords_are_blocked():
    samples = [
        "DELETE FROM customers",
        "DROP TABLE orders",
        "UPDATE customers SET name = 'x'",
        "INSERT INTO customers (customer_id) VALUES (1)",
        "TRUNCATE TABLE orders",
        "ALTER TABLE orders ADD COLUMN x TEXT",
        "CREATE TABLE stolen (id INTEGER)",
        "GRANT SELECT ON orders TO PUBLIC",
        "PRAGMA writable_schema = ON",
        "ATTACH DATABASE 'evil.db' AS evil",
        "SELECT 1 INTO OUTFILE '/tmp/x'",
        "WITH x AS (SELECT 1) DELETE FROM orders",
    ]
    for sample in samples:
        decision = review_sql(sample)
        assert not decision.allowed, sample
        assert "BLOCKED" in decision.reason


def test_with_select_is_allowed():
    decision = review_sql("WITH recent AS (SELECT order_id FROM orders) SELECT * FROM recent")
    assert decision.allowed


def test_multiple_statements_are_blocked():
    decision = review_sql("SELECT 1; SELECT 2")
    assert not decision.allowed


def test_user_destruction_phrases():
    assert user_requests_destruction("Delete all users from the database")
    assert user_requests_destruction("Please drop the table orders")
    assert not user_requests_destruction("What products should we drop from the catalog if sales are low?")
    assert not user_requests_destruction("What was completed-order revenue in Q3 2024?")


def test_reader_connection_rejects_writes():
    engine = get_reader_engine()
    with pytest.raises(SQLAlchemyError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO customers (customer_id, name, email, region, segment, signup_date) "
                    "VALUES (99999, 'x', 'x@example.com', 'North', 'SMB', '2024-01-01')"
                )
            )
