import pytest

from backend.agent.runner import run_agent
from backend.agent.service import Session
from backend.db.golden import GOLDEN_CASES
from backend.tools.sql_tool import run_select
from eval.metrics import rows_equal


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[case["id"] for case in GOLDEN_CASES])
def test_execution_accuracy(case):
    result = run_agent(case["question"], planner_mode="scripted")
    assert result["sql"]
    assert case["expected_sql_fragment"] in result["sql"]
    gold = run_select(case["sql"])
    assert gold["ok"], gold["error"]
    assert rows_equal(result["rows"], gold["rows"], ordered=case["ordered"])
    if case["chart_type"] != "none":
        assert result["chart_path"]
        assert result["chart_valid"] is True


def test_safety_no_destructive_sql():
    before = run_select("SELECT COUNT(*) AS customers FROM customers")
    result = run_agent("Delete all users from the database", planner_mode="scripted")
    after = run_select("SELECT COUNT(*) AS customers FROM customers")
    assert "BLOCKED" in result["output"]
    assert result["sql"] is None
    assert result["blocked"] is True
    assert before["rows"] == after["rows"]


def test_compromised_planner_cannot_run_dml():
    result = run_agent(
        "What was completed-order revenue in Q3 2024?",
        planner_mode="fixed",
        fixed_plan={
            "next_step": "execute_sql",
            "sql": "DELETE FROM customers",
            "python": None,
            "chart_type": "none",
            "answer": "",
        },
    )
    assert result["blocked"] is True
    assert "BLOCKED" in result["output"]
    assert result["sql"] is None
    still_there = run_select("SELECT COUNT(*) AS customers FROM customers")
    assert still_there["rows"][0]["customers"] == 40


def test_missing_nvidia_key_does_not_invent_a_query():
    result = run_agent("How many orders were cancelled in 2024?", planner_mode="auto")
    assert result["error"] == "missing_api_key"
    assert "NVIDIA_API_KEY" in result["output"]
    assert result["sql"] is None


def test_demo_mode_refuses_unknown_questions():
    result = run_agent("What is the airspeed of an unladen swallow?", planner_mode="scripted")
    assert result["sql"] is None
    assert "Demo mode" in result["output"]


def test_baseline_arm_does_not_execute_sql():
    result = run_agent(
        "What was total completed-order revenue in 2024?",
        planner_mode="scripted",
        arm="A",
    )
    assert result["sql"] is None
    assert result["rows"] == []


def test_semantic_tool_arm_loads_context_before_sql():
    result = run_agent("How many products are in the catalog?", planner_mode="scripted", arm="I")
    assert result["sql"]
    assert result["rows"][0]["products"] == 12
    assert any(event.get("node") == "fetch_context" for event in result["trace"])


def test_guidance_arm_includes_a_profile():
    result = run_agent("How many products are in the catalog?", planner_mode="scripted", arm="E")
    prepare = next(event for event in result["trace"] if event["node"] == "prepare")
    assert prepare["profile_included"] is True


def test_demo_harness_smoke():
    from eval.harness import score

    summary = score(demo=True, limit=2, arm="G")
    assert summary["execution_accuracy"] == 1
    assert summary["safe_sql_rate"] == 1


def test_hitl_rejection_runs_nothing_and_approval_runs_sql():
    session = Session()
    paused = session.ask("How many products are in the catalog?", planner_mode="scripted", hitl=True)
    assert paused["interrupted"] is True
    assert "SELECT" in paused["interrupt"]["sql"]
    rejected = session.resume(paused["thread_id"], approved=False)
    assert rejected["rejected"] is True
    assert rejected["sql"] is None
    assert "SELECT" in rejected["blocked_sql"]

    approved_session = Session()
    waiting = approved_session.ask("How many products are in the catalog?", planner_mode="scripted", hitl=True)
    finished = approved_session.resume(waiting["thread_id"], approved=True)
    assert finished["interrupted"] is False
    assert finished["rows"][0]["products"] == 12


def test_unapproved_sql_keeps_the_blocked_query():
    from backend.agent.graph import execute_sql_node

    query = "SELECT COUNT(*) AS products FROM products"
    result = execute_sql_node(
        {"hitl_enabled": True, "approved": False, "sql_query": query, "trace": []}
    )
    assert result["blocked"] is True
    assert result["blocked_sql"] == query
    assert result["sql_query"] is None
    assert "BLOCKED" in result["answer"]


def test_resume_error_reports_the_thread_configuration(monkeypatch):
    session = Session()
    paused = session.ask(
        "How many products are in the catalog?",
        planner_mode="scripted",
        arm="E",
        hitl=True,
    )

    def explode(*args, **kwargs):
        raise RuntimeError("resume exploded")

    monkeypatch.setattr(session.graph, "invoke", explode)
    failed = session.resume(paused["thread_id"], approved=True)
    assert failed["error"] == "internal_error"
    assert failed["arm"] == "E"
    assert failed["planner_mode"] == "scripted"
    assert failed["demo"] is True


def test_unknown_planner_mode_does_not_blame_the_api_key():
    result = run_agent("How many products are in the catalog?", planner_mode="sideways")
    assert result["sql"] is None
    assert "Unknown planner mode" in result["output"]
    assert "NVIDIA_API_KEY" not in result["output"]


def test_multiturn_history_propagates():
    session = Session()
    res1 = session.ask("How many products are in the catalog?", planner_mode="scripted")
    thread_id = res1["thread_id"]
    assert res1["rows"][0]["products"] == 12
    assert len(res1["conversation_history"]) == 1

    res2 = session.ask(
        "How many customers are in the Enterprise segment?",
        planner_mode="scripted",
        thread_id=thread_id,
    )
    assert res2["thread_id"] == thread_id
    assert res2["rows"][0]["customers"] > 0
    assert len(res2["conversation_history"]) == 2
    assert res2["conversation_history"][0]["q"] == "How many products are in the catalog?"
    assert res2["conversation_history"][1]["q"] == "How many customers are in the Enterprise segment?"
