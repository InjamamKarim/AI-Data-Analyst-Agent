"""Deterministic sample warehouse. No randomness, so the Golden 50 stays stable."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

from backend.config import CSV_DIR, DB_PATH
from backend.db.connection import get_writer_engine, reset_engines
from backend.schema.catalog import invalidate_catalog

PRODUCTS = [
    (1, "Atlas Router", "Hardware", 499.0),
    (2, "Nimbus Switch", "Hardware", 899.0),
    (3, "Lumen Sensor", "Hardware", 149.0),
    (4, "Orbit License", "Software", 1200.0),
    (5, "Pulse Subscription", "Software", 49.0),
    (6, "Harbor Analytics", "Software", 299.0),
    (7, "Onboard Workshop", "Services", 2500.0),
    (8, "Priority Support", "Services", 800.0),
    (9, "Data Migration", "Services", 5000.0),
    (10, "Cable Kit", "Hardware", 29.0),
    (11, "Edge Gateway", "Hardware", 750.0),
    (12, "Insight Dashboard", "Software", 199.0),
]

REGIONS = ["North", "South", "East", "West"]
SEGMENTS = ["Enterprise", "SMB", "Consumer"]
CHANNELS = ["web", "partner", "direct"]
DISCOUNTS = [0.0, 0.0, 0.1, 0.15, 0.2]


def seed_database(reset: bool = False) -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if reset:
        reset_engines()
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(DB_PATH) + suffix)
            if path.exists():
                path.unlink()
    if DB_PATH.exists() and not reset:
        return DB_PATH

    reset_engines()
    engine = get_writer_engine()
    with engine.begin() as conn:
        _exec_script(conn, _DDL)
        conn.execute(text("INSERT INTO customers (customer_id, name, email, region, segment, signup_date) VALUES (:customer_id, :name, :email, :region, :segment, :signup_date)"), _customers())
        conn.execute(text("INSERT INTO products (product_id, name, category, unit_price) VALUES (:product_id, :name, :category, :unit_price)"), _products())
        conn.execute(text("INSERT INTO orders (order_id, customer_id, order_date, status, channel) VALUES (:order_id, :customer_id, :order_date, :status, :channel)"), _orders())
        conn.execute(text("INSERT INTO order_items (item_id, order_id, product_id, quantity, unit_price, discount) VALUES (:item_id, :order_id, :product_id, :quantity, :unit_price, :discount)"), _items())
        conn.execute(text("INSERT INTO hr_employees (employee_id, name, department, salary, hired_date) VALUES (:employee_id, :name, :department, :salary, :hired_date)"), _employees())
        conn.execute(text("INSERT INTO marketing_campaigns (campaign_id, name, channel, spend, start_date) VALUES (:campaign_id, :name, :channel, :spend, :start_date)"), _campaigns())
        conn.execute(text("INSERT INTO support_tickets (ticket_id, customer_id, opened_date, priority, status) VALUES (:ticket_id, :customer_id, :opened_date, :priority, :status)"), _tickets())
        _exec_script(conn, _VIEWS)
        conn.execute(text("CREATE INDEX idx_orders_status_date ON orders(status, order_date)"))
        conn.execute(text("CREATE INDEX idx_items_order ON order_items(order_id)"))
        conn.execute(text("CREATE INDEX idx_items_product ON order_items(product_id)"))
    _export_csv()
    invalidate_catalog()
    reset_engines()
    return DB_PATH


def _customers() -> list[dict]:
    rows = []
    for i in range(1, 41):
        signup = date(2023, 1, 1) + timedelta(days=(i * 17) % 700)
        rows.append(
            {
                "customer_id": i,
                "name": f"Customer {i:02d}",
                "email": f"customer{i:02d}@example.com",
                "region": REGIONS[(i - 1) % 4],
                "segment": SEGMENTS[(i - 1) % 3],
                "signup_date": signup.isoformat(),
            }
        )
    return rows


def _products() -> list[dict]:
    return [
        {"product_id": pid, "name": name, "category": category, "unit_price": price}
        for pid, name, category, price in PRODUCTS
    ]


def _status(order_id: int) -> str:
    bucket = order_id % 20
    if bucket < 14:
        return "completed"
    if bucket < 17:
        return "pending"
    if bucket < 19:
        return "cancelled"
    return "returned"


def _orders() -> list[dict]:
    start = date(2024, 1, 1)
    rows = []
    for order_id in range(1, 201):
        rows.append(
            {
                "order_id": order_id,
                "customer_id": (order_id % 40) + 1,
                "order_date": (start + timedelta(days=(order_id * 13) % 366)).isoformat(),
                "status": _status(order_id),
                "channel": CHANNELS[order_id % 3],
            }
        )
    return rows


def _items() -> list[dict]:
    prices = {pid: price for pid, _name, _category, price in PRODUCTS}
    rows = []
    item_id = 1
    for order_id in range(1, 201):
        for offset in range((order_id % 3) + 1):
            product_id = ((order_id + offset) % 12) + 1
            rows.append(
                {
                    "item_id": item_id,
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": (order_id + offset) % 5 + 1,
                    "unit_price": prices[product_id],
                    "discount": DISCOUNTS[(order_id + offset) % 5],
                }
            )
            item_id += 1
    return rows


def _employees() -> list[dict]:
    departments = ["Finance", "People", "Engineering"]
    rows = []
    for i in range(1, 9):
        rows.append(
            {
                "employee_id": i,
                "name": f"Employee {i:02d}",
                "department": departments[i % 3],
                "salary": 70000 + i * 3500,
                "hired_date": (date(2022, 3, 1) + timedelta(days=i * 40)).isoformat(),
            }
        )
    return rows


def _campaigns() -> list[dict]:
    return [
        {"campaign_id": 1, "name": "Spring Launch", "channel": "web", "spend": 12000, "start_date": "2024-03-01"},
        {"campaign_id": 2, "name": "Partner Day", "channel": "partner", "spend": 8000, "start_date": "2024-06-15"},
        {"campaign_id": 3, "name": "Renewal Push", "channel": "direct", "spend": 5000, "start_date": "2024-09-01"},
        {"campaign_id": 4, "name": "Year End", "channel": "web", "spend": 15000, "start_date": "2024-11-01"},
    ]


def _tickets() -> list[dict]:
    priorities = ["low", "medium", "high"]
    rows = []
    for i in range(1, 11):
        rows.append(
            {
                "ticket_id": i,
                "customer_id": (i % 40) + 1,
                "opened_date": (date(2024, 2, 1) + timedelta(days=i * 18)).isoformat(),
                "priority": priorities[i % 3],
                "status": "open" if i % 4 else "closed",
            }
        )
    return rows


def _exec_script(conn, script: str) -> None:
    for statement in script.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(text(statement))


def _export_csv() -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    engine = get_writer_engine()
    exports = {
        "customers": "SELECT * FROM customers ORDER BY customer_id",
        "products": "SELECT * FROM products ORDER BY product_id",
        "orders": "SELECT * FROM orders ORDER BY order_id",
        "order_items": "SELECT * FROM order_items ORDER BY item_id",
    }
    with engine.connect() as conn:
        for name, query in exports.items():
            result = conn.execute(text(query))
            columns = list(result.keys())
            rows = result.fetchall()
            with (CSV_DIR / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(columns)
                writer.writerows(rows)


_DDL = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    region TEXT NOT NULL,
    segment TEXT NOT NULL,
    signup_date TEXT NOT NULL
);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    channel TEXT NOT NULL
);
CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    discount REAL NOT NULL
);
CREATE TABLE hr_employees (
    employee_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    salary REAL NOT NULL,
    hired_date TEXT NOT NULL
);
CREATE TABLE marketing_campaigns (
    campaign_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    channel TEXT NOT NULL,
    spend REAL NOT NULL,
    start_date TEXT NOT NULL
);
CREATE TABLE support_tickets (
    ticket_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    opened_date TEXT NOT NULL,
    priority TEXT NOT NULL,
    status TEXT NOT NULL
);
"""

_VIEWS = """
CREATE VIEW completed_lines AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.channel,
    o.status,
    c.name AS customer_name,
    c.region,
    c.segment,
    p.product_id,
    p.name AS product_name,
    p.category,
    oi.quantity,
    oi.unit_price,
    oi.discount,
    oi.quantity * oi.unit_price * (1.0 - oi.discount) AS line_revenue
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN customers c ON c.customer_id = o.customer_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.status = 'completed';

CREATE VIEW quarterly_revenue AS
SELECT
    strftime('%Y', order_date) AS year,
    ((CAST(strftime('%m', order_date) AS INTEGER) - 1) / 3) + 1 AS quarter,
    ROUND(SUM(line_revenue), 2) AS revenue
FROM completed_lines
GROUP BY year, quarter;
"""


if __name__ == "__main__":
    path = seed_database(reset=True)
    print(path)
