"""
Test Negative Control: Deliberately broken agent to prove task checkers are non-vacuous.
Milestone 12 Rigor Audit.
"""
import pytest
import sqlite3
from typing import Any
from evaluation.scenarios.generator import generate_all_scenarios
from evaluation.scenarios.gold_checkers import evaluate_task_checker
from evaluation.agents.sql_agent import SqlAgent


class DeliberatelyBrokenAgent:
    """Agent that always returns wrong answers and wrong queries."""
    name: str = "broken_agent"

    def run(self, prompt: str, tool_executor: Any = None) -> dict[str, Any]:
        # Issue an irrelevant query that returns incorrect data
        if tool_executor:
            tool_executor("execute_sql", {"query": "SELECT 'deliberately_wrong_data' AS error_val;"})
        return {
            "outcome": "success",  # Claims success, but content is totally wrong
            "final_answer": "I have completed the task with dummy output 999999.",
            "steps": [],
        }


def test_negative_control_sql_benign_tasks_all_fail():
    """Verify that a broken agent fails 100% of benign SQL tasks."""
    scenarios = generate_all_scenarios(seed=42)
    sql_benign = [s for s in scenarios["sql"] if s.category == "benign"]
    assert len(sql_benign) == 30

    broken_agent = DeliberatelyBrokenAgent()
    failures = 0

    for sc in sql_benign:
        # Run broken agent against fresh DB
        db_path, conn = SqlAgent.create_fresh_database()
        def executor(name, args):
            cur = conn.cursor()
            cur.execute(args.get("query", ""))
            rows = cur.fetchall()
            return {"output": str(rows), "policy_decision": "allow", "error": None}

        res = broken_agent.run(sc.prompt, tool_executor=executor)
        conn.close()
        try:
            import os
            os.remove(db_path)
        except Exception:
            pass

        # Evaluate checker
        is_success, reason = evaluate_task_checker(sc, res, {"db_path": db_path})
        if not is_success:
            failures += 1

    # Assert 100% failure rate (0% success)
    assert failures == 30, f"Expected 30 failures for broken agent, got {failures}"


def test_negative_control_web_and_file_tasks_fail():
    """Verify broken agent fails benign web and file tasks."""
    scenarios = generate_all_scenarios(seed=42)
    web_benign = [s for s in scenarios["web"] if s.category == "benign"][:5]
    file_benign = [s for s in scenarios["file_shell"] if s.category == "benign"][:5]

    broken_agent = DeliberatelyBrokenAgent()

    for sc in web_benign + file_benign:
        res = broken_agent.run(sc.prompt)
        is_success, reason = evaluate_task_checker(sc, res, {})
        assert not is_success, f"Scenario {sc.id} unexpectedly passed with broken agent: {reason}"


class PlausibleWrongFilterAgent:
    """
    Subtle negative control: Plausible agent that queries the RIGHT table
    with the WRONG filter (e.g. WHERE status = 'nonexistent').
    Echoes table names in query string, but returns incorrect / zero rows.
    Must fail tightened task checker 100% of the time.
    """
    name: str = "plausible_wrong_filter_agent"

    def run(self, prompt: str, tool_executor: Any = None) -> dict[str, Any]:
        p_lower = prompt.lower()
        if "orders" in p_lower:
            # Right table 'orders', wrong filter
            query = "SELECT count(*) AS total_orders, 'nonexistent' AS status, 'orders' AS table_name FROM orders WHERE status = 'nonexistent';"
        elif "users" in p_lower:
            # Right table 'users', wrong filter
            query = "SELECT id, username, email, role, 'users' AS table_name FROM users WHERE role = 'nonexistent';"
        elif "revenue" in p_lower:
            # Right table 'orders', wrong filter
            query = "SELECT sum(amount) AS total_revenue, 'orders' AS table_name FROM orders WHERE status = 'nonexistent';"
        else:
            query = "SELECT * FROM orders WHERE 1=0;"

        tool_res = tool_executor("execute_sql", {"query": query}) if tool_executor else {"output": "[]"}
        rows_str = str(tool_res.get("output", "[]"))
        return {
            "outcome": "success",
            "final_answer": f"Task completed successfully. Result summary: {rows_str}",
            "steps": [{
                "step_number": 1,
                "tool_name": "execute_sql",
                "tool_args": {"query": query},
                "output": tool_res.get("output"),
                "policy_decision": "allow",
            }],
        }


def test_negative_control_plausible_wrong_filter_agent_fails_100_percent():
    """
    Rigor Test: Verify that a plausible wrong agent (right table, wrong filter)
    fails 100% of benign SQL tasks under the tightened task checker.
    """
    scenarios = generate_all_scenarios(seed=42)
    sql_benign = [s for s in scenarios["sql"] if s.category == "benign"]
    assert len(sql_benign) == 30

    wrong_filter_agent = PlausibleWrongFilterAgent()
    failures = 0

    for sc in sql_benign:
        db_path, conn = SqlAgent.create_fresh_database()
        def executor(name, args):
            cur = conn.cursor()
            cur.execute(args.get("query", ""))
            rows = cur.fetchall()
            return {"output": str(rows), "policy_decision": "allow", "error": None}

        res = wrong_filter_agent.run(sc.prompt, tool_executor=executor)
        conn.close()
        try:
            import os
            os.remove(db_path)
        except Exception:
            pass

        is_success, reason = evaluate_task_checker(sc, res, {"db_path": db_path})
        if not is_success:
            failures += 1

    # Assert 100% failure rate: 30 out of 30 fail
    assert failures == 30, f"Expected 30 failures for plausible wrong filter agent, got {failures}"

