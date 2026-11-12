from fastapi.testclient import TestClient

from backend.main import app
from backend.tools.sql_tool import run_select


def test_health_hides_the_key_and_reports_the_host():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["nvidia_api_key_configured"] is False
    assert "nvidia_api_key" not in body
    assert body["e2b"] == "ignored"
    assert body["host"]["heavy_local_workload"] == "disabled"


def test_chat_demo_and_safety_and_page():
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    assert "Data analyst" in page.text

    demo = client.post("/api/chat", json={"message": "How many products are in the catalog?", "demo": True})
    assert demo.status_code == 200
    body = demo.json()
    assert body["demo"] is True
    assert body["rows"][0]["products"] == 12

    blocked = client.post(
        "/api/chat",
        json={"message": "Delete all users from the database", "demo": False},
    )
    assert blocked.status_code == 200
    assert "BLOCKED" in blocked.json()["output"]
    assert blocked.json()["sql"] is None


def test_csv_upload_is_queryable_and_neutralized():
    client = TestClient(app)
    payload = "=evil,amount\n=1+1,5\nProduct,6\n"
    response = client.post(
        "/api/upload",
        files={"file": ("notes.csv", payload, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["sql_table"] == "uploaded_csv"
    result = run_select("SELECT evil, amount FROM uploaded_csv ORDER BY amount")
    assert result["ok"], result["error"]
    assert str(result["rows"][0]["evil"]).startswith("'")
    from backend.db.connection import get_writer_engine
    from backend.schema.catalog import invalidate_catalog

    with get_writer_engine().begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS uploaded_csv")
    invalidate_catalog()


def test_request_id_header_is_present():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) == 8


def test_rate_limiter():
    from backend.main import RateLimiter
    limiter = RateLimiter(limit=2, window=10.0)
    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is False
    assert limiter.is_allowed("192.168.1.1") is True
