"""Golden 50 questions against the seeded sample warehouse.

Demo mode replays these statements. The live NVIDIA planner never sees this file.
"""

from __future__ import annotations

from textwrap import dedent

LINE = "oi.quantity * oi.unit_price * (1.0 - oi.discount)"
Q1 = "o.order_date >= '2024-01-01' AND o.order_date < '2024-04-01'"
Q2 = "o.order_date >= '2024-04-01' AND o.order_date < '2024-07-01'"
Q3 = "o.order_date >= '2024-07-01' AND o.order_date < '2024-10-01'"
Q4 = "o.order_date >= '2024-10-01' AND o.order_date < '2025-01-01'"
H2 = "o.order_date >= '2024-07-01' AND o.order_date < '2025-01-01'"
YEAR = "o.order_date >= '2024-01-01' AND o.order_date < '2025-01-01'"
JAN = "order_date >= '2024-01-01' AND order_date < '2024-02-01'"
JOIN_C = "JOIN customers c ON c.customer_id = o.customer_id"
JOIN_P = "JOIN products p ON p.product_id = oi.product_id"

BAR_PY = dedent(
    """
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    df = pd.read_json("sql_result.json")
    label = df.columns[0]
    value = df.columns[1]
    plt.figure(figsize=(7, 4))
    plt.bar(df[label].astype(str), df[value])
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig("chart.png")
    print(df.to_string(index=False))
    """
).strip()

LINE_PY = dedent(
    """
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    df = pd.read_json("sql_result.json")
    label = df.columns[0]
    value = df.columns[1]
    plt.figure(figsize=(7, 4))
    plt.plot(df[label].astype(str), df[value], marker="o")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig("chart.png")
    print(df.to_string(index=False))
    """
).strip()

PIE_PY = dedent(
    """
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    df = pd.read_json("sql_result.json")
    label = df.columns[0]
    value = df.columns[1]
    plt.figure(figsize=(6, 4))
    plt.pie(df[value], labels=df[label].astype(str))
    plt.tight_layout()
    plt.savefig("chart.png")
    print(df.to_string(index=False))
    """
).strip()


def _revenue(where: str, joins: str = "", projection: str | None = None, group: str = "", order: str = "", limit: str = "") -> str:
    proj = projection or f"ROUND(SUM({LINE}), 2) AS revenue"
    parts = [
        f"SELECT {proj}",
        "FROM order_items oi",
        "JOIN orders o ON o.order_id = oi.order_id",
    ]
    if joins:
        parts.append(joins)
    parts.append(f"WHERE o.status = 'completed' AND {where}")
    if group:
        parts.append(f"GROUP BY {group}")
    if order:
        parts.append(f"ORDER BY {order}")
    if limit:
        parts.append(f"LIMIT {limit}")
    return "\n".join(parts)


def _case(
    case_id: str,
    question: str,
    sql: str,
    fragment: str,
    ordered: bool = False,
    chart_type: str = "none",
    python: str | None = None,
) -> dict:
    return {
        "id": case_id,
        "question": question,
        "sql": sql.strip(),
        "expected_sql_fragment": fragment,
        "ordered": ordered,
        "chart_type": chart_type,
        "python": python,
    }


GOLDEN_CASES: list[dict] = [
    _case("q01", "What was completed-order revenue in Q3 2024?", _revenue(Q3), Q3),
    _case("q02", "What was completed-order revenue in Q4 2024?", _revenue(Q4), Q4),
    _case("q03", "What was completed-order revenue in Q1 2024?", _revenue(Q1), Q1),
    _case("q04", "What was completed-order revenue in Q2 2024?", _revenue(Q2), Q2),
    _case("q05", "What was total completed-order revenue in 2024?", _revenue(YEAR), YEAR),
    _case(
        "q06",
        "How many completed orders were placed in 2024?",
        f"SELECT COUNT(*) AS orders\nFROM orders\nWHERE status = 'completed' AND {YEAR.replace('o.order_date', 'order_date')}",
        "status = 'completed'",
    ),
    _case(
        "q07",
        "How many orders were cancelled in 2024?",
        f"SELECT COUNT(*) AS orders\nFROM orders\nWHERE status = 'cancelled' AND {YEAR.replace('o.order_date', 'order_date')}",
        "status = 'cancelled'",
    ),
    _case(
        "q08",
        "How many orders are pending in 2024?",
        f"SELECT COUNT(*) AS orders\nFROM orders\nWHERE status = 'pending' AND {YEAR.replace('o.order_date', 'order_date')}",
        "status = 'pending'",
    ),
    _case(
        "q09",
        "How many orders were returned in 2024?",
        f"SELECT COUNT(*) AS orders\nFROM orders\nWHERE status = 'returned' AND {YEAR.replace('o.order_date', 'order_date')}",
        "status = 'returned'",
    ),
    _case(
        "q10",
        "Show completed revenue by region as a bar chart.",
        _revenue(YEAR, JOIN_C, f"c.region AS region, ROUND(SUM({LINE}), 2) AS revenue", "c.region", "revenue DESC, c.region ASC"),
        "GROUP BY c.region",
        ordered=True,
        chart_type="bar",
        python=BAR_PY,
    ),
    _case(
        "q11",
        "What is completed revenue by customer segment?",
        _revenue(YEAR, JOIN_C, f"c.segment AS segment, ROUND(SUM({LINE}), 2) AS revenue", "c.segment", "segment ASC"),
        "GROUP BY c.segment",
        ordered=True,
    ),
    _case(
        "q12",
        "Show completed revenue by product category as a pie chart.",
        _revenue(YEAR, JOIN_P, f"p.category AS category, ROUND(SUM({LINE}), 2) AS revenue", "p.category", "category ASC"),
        "GROUP BY p.category",
        ordered=True,
        chart_type="pie",
        python=PIE_PY,
    ),
    _case(
        "q13",
        "What is completed revenue by sales channel?",
        _revenue(YEAR, "", f"o.channel AS channel, ROUND(SUM({LINE}), 2) AS revenue", "o.channel", "channel ASC"),
        "GROUP BY o.channel",
        ordered=True,
    ),
    _case(
        "q14",
        "What are the top 5 products by completed revenue?",
        _revenue(YEAR, JOIN_P, f"p.name AS product, ROUND(SUM({LINE}), 2) AS revenue", "p.name", "revenue DESC, p.name ASC", "5"),
        "LIMIT 5",
        ordered=True,
    ),
    _case(
        "q15",
        "What are the top 5 customers by completed revenue?",
        _revenue(YEAR, JOIN_C, f"c.name AS customer, ROUND(SUM({LINE}), 2) AS revenue", "c.name", "revenue DESC, c.name ASC", "5"),
        "LIMIT 5",
        ordered=True,
    ),
    _case(
        "q16",
        "Plot monthly completed revenue for 2024 as a line chart.",
        _revenue(
            YEAR,
            "",
            f"strftime('%Y-%m', o.order_date) AS month, ROUND(SUM({LINE}), 2) AS revenue",
            "month",
            "month ASC",
        ),
        "strftime('%Y-%m', o.order_date)",
        ordered=True,
        chart_type="line",
        python=LINE_PY,
    ),
    _case(
        "q17",
        "How many units were sold in each category on completed orders?",
        _revenue(YEAR, JOIN_P, "p.category AS category, SUM(oi.quantity) AS units", "p.category", "category ASC"),
        "SUM(oi.quantity)",
        ordered=True,
    ),
    _case(
        "q18",
        "What is the total discount amount on completed orders?",
        _revenue(YEAR, "", "ROUND(SUM(oi.quantity * oi.unit_price * oi.discount), 2) AS discount_amount"),
        "oi.quantity * oi.unit_price * oi.discount",
    ),
    _case(
        "q19",
        "What is the average completed order value in 2024?",
        _revenue(YEAR, "", f"ROUND(SUM({LINE}) / COUNT(DISTINCT o.order_id), 2) AS average_order_value"),
        "COUNT(DISTINCT o.order_id)",
    ),
    _case(
        "q20",
        "How many distinct customers placed a completed order?",
        _revenue(YEAR, "", "COUNT(DISTINCT o.customer_id) AS customers"),
        "COUNT(DISTINCT o.customer_id)",
    ),
    _case(
        "q21",
        "What is completed Hardware revenue in the North region?",
        _revenue(f"{YEAR} AND c.region = 'North' AND p.category = 'Hardware'", f"{JOIN_C}\n{JOIN_P}"),
        "p.category = 'Hardware'",
    ),
    _case(
        "q22",
        "What is completed Software revenue in the East region?",
        _revenue(f"{YEAR} AND c.region = 'East' AND p.category = 'Software'", f"{JOIN_C}\n{JOIN_P}"),
        "p.category = 'Software'",
    ),
    _case(
        "q23",
        "What is completed Services revenue in the second half of 2024?",
        _revenue(f"{H2} AND p.category = 'Services'", JOIN_P),
        "p.category = 'Services'",
    ),
    _case(
        "q24",
        "What is completed revenue from the web channel in Q1 2024?",
        _revenue(f"{Q1} AND o.channel = 'web'"),
        "o.channel = 'web'",
    ),
    _case(
        "q25",
        "What is completed revenue from the partner channel in 2024?",
        _revenue(f"{YEAR} AND o.channel = 'partner'"),
        "o.channel = 'partner'",
    ),
    _case(
        "q26",
        "How many completed orders came through the direct channel?",
        f"SELECT COUNT(*) AS orders\nFROM orders\nWHERE status = 'completed' AND channel = 'direct' AND {YEAR.replace('o.order_date', 'order_date')}",
        "channel = 'direct'",
    ),
    _case(
        "q27",
        "Which product has the highest list price?",
        "SELECT name, unit_price\nFROM products\nORDER BY unit_price DESC, name ASC\nLIMIT 1",
        "ORDER BY unit_price DESC, name ASC",
        ordered=True,
    ),
    _case(
        "q28",
        "Which product has the lowest list price?",
        "SELECT name, unit_price\nFROM products\nORDER BY unit_price ASC, name ASC\nLIMIT 1",
        "ORDER BY unit_price ASC, name ASC",
        ordered=True,
    ),
    _case(
        "q29",
        "What is the average list price by category?",
        "SELECT category, ROUND(AVG(unit_price), 2) AS average_unit_price\nFROM products\nGROUP BY category\nORDER BY category ASC",
        "AVG(unit_price)",
        ordered=True,
    ),
    _case(
        "q30",
        "How many customers are in the Enterprise segment?",
        "SELECT COUNT(*) AS customers\nFROM customers\nWHERE segment = 'Enterprise'",
        "segment = 'Enterprise'",
    ),
    _case(
        "q31",
        "How many SMB customers are in the South region?",
        "SELECT COUNT(*) AS customers\nFROM customers\nWHERE segment = 'SMB' AND region = 'South'",
        "segment = 'SMB'",
    ),
    _case(
        "q32",
        "How many customers signed up before 1 July 2024?",
        "SELECT COUNT(*) AS customers\nFROM customers\nWHERE signup_date < '2024-07-01'",
        "signup_date < '2024-07-01'",
    ),
    _case(
        "q33",
        "How many customers placed more than one completed order?",
        "SELECT COUNT(*) AS repeat_customers\nFROM (\n  SELECT customer_id\n  FROM orders\n  WHERE status = 'completed'\n  GROUP BY customer_id\n  HAVING COUNT(*) > 1\n) t",
        "HAVING COUNT(*) > 1",
    ),
    _case(
        "q34",
        "What is completed revenue for the product Priority Support?",
        _revenue(f"{YEAR} AND p.name = 'Priority Support'", JOIN_P),
        "p.name = 'Priority Support'",
    ),
    _case(
        "q35",
        "What is completed revenue for the product Orbit License?",
        _revenue(f"{YEAR} AND p.name = 'Orbit License'", JOIN_P),
        "p.name = 'Orbit License'",
    ),
    _case(
        "q36",
        "What is the total quantity sold on completed orders?",
        _revenue(YEAR, "", "SUM(oi.quantity) AS units"),
        "SUM(oi.quantity) AS units",
    ),
    _case(
        "q37",
        "How many distinct products were sold on completed orders?",
        _revenue(YEAR, "", "COUNT(DISTINCT oi.product_id) AS products_sold"),
        "COUNT(DISTINCT oi.product_id)",
    ),
    _case(
        "q38",
        "How many completed orders included a discounted line?",
        f"SELECT COUNT(DISTINCT o.order_id) AS orders_with_discount\nFROM orders o\nJOIN order_items oi ON oi.order_id = o.order_id\nWHERE o.status = 'completed' AND oi.discount > 0 AND {YEAR}",
        "oi.discount > 0",
    ),
    _case(
        "q39",
        "What is the average discount rate on completed order lines?",
        _revenue(YEAR, "", "ROUND(AVG(oi.discount), 4) AS average_discount"),
        "AVG(oi.discount)",
    ),
    _case(
        "q40",
        "What is completed revenue by quarter in 2024?",
        _revenue(
            YEAR,
            "",
            f"((CAST(strftime('%m', o.order_date) AS INTEGER) - 1) / 3) + 1 AS quarter, ROUND(SUM({LINE}), 2) AS revenue",
            "quarter",
            "quarter ASC",
        ),
        "AS quarter",
        ordered=True,
    ),
    _case(
        "q41",
        "How many completed orders were placed by customers in the West region?",
        f"SELECT COUNT(DISTINCT o.order_id) AS orders\nFROM orders o\n{JOIN_C}\nWHERE o.status = 'completed' AND c.region = 'West' AND {YEAR}",
        "c.region = 'West'",
    ),
    _case(
        "q42",
        "How many orders of any status were placed in January 2024?",
        f"SELECT COUNT(*) AS orders\nFROM orders\nWHERE {JAN}",
        JAN,
    ),
    _case(
        "q43",
        "What is the latest completed order date?",
        "SELECT MAX(order_date) AS max_order_date\nFROM orders\nWHERE status = 'completed'",
        "MAX(order_date)",
    ),
    _case(
        "q44",
        "What is the earliest completed order date?",
        "SELECT MIN(order_date) AS min_order_date\nFROM orders\nWHERE status = 'completed'",
        "MIN(order_date)",
    ),
    _case(
        "q45",
        "Which region has the highest completed revenue?",
        _revenue(YEAR, JOIN_C, f"c.region AS region, ROUND(SUM({LINE}), 2) AS revenue", "c.region", "revenue DESC, c.region ASC", "1"),
        "LIMIT 1",
        ordered=True,
    ),
    _case(
        "q46",
        "What is completed revenue from the Consumer segment?",
        _revenue(f"{YEAR} AND c.segment = 'Consumer'", JOIN_C),
        "c.segment = 'Consumer'",
    ),
    _case(
        "q47",
        "What is the average quantity per completed order line?",
        _revenue(YEAR, "", "ROUND(AVG(oi.quantity), 2) AS average_quantity"),
        "AVG(oi.quantity)",
    ),
    _case(
        "q48",
        "How many products are in the catalog?",
        "SELECT COUNT(*) AS products\nFROM products",
        "FROM products",
    ),
    _case(
        "q49",
        "What is completed Hardware revenue from the web channel?",
        _revenue(f"{YEAR} AND p.category = 'Hardware' AND o.channel = 'web'", JOIN_P),
        "o.channel = 'web'",
    ),
    _case(
        "q50",
        "How many completed order lines have a discount of at least 20 percent?",
        f"SELECT COUNT(*) AS lines\nFROM order_items oi\nJOIN orders o ON o.order_id = oi.order_id\nWHERE o.status = 'completed' AND oi.discount >= 0.2 AND {YEAR}",
        "oi.discount >= 0.2",
    ),
]


def _validate() -> None:
    ids = [case["id"] for case in GOLDEN_CASES]
    questions = [" ".join(case["question"].split()).casefold() for case in GOLDEN_CASES]
    if len(GOLDEN_CASES) != 50:
        raise RuntimeError(f"Expected 50 golden cases, found {len(GOLDEN_CASES)}")
    if len(set(ids)) != len(ids):
        raise RuntimeError("Duplicate golden ids")
    if len(set(questions)) != len(questions):
        raise RuntimeError("Duplicate golden questions")
    for case in GOLDEN_CASES:
        if case["expected_sql_fragment"] not in case["sql"]:
            raise RuntimeError(f"{case['id']} fragment is not in its SQL")


_validate()


def lookup_case(question: str) -> dict | None:
    key = " ".join((question or "").split()).casefold()
    for case in GOLDEN_CASES:
        if " ".join(case["question"].split()).casefold() == key:
            return case
    return None
