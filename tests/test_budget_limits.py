import pytest
import uuid
from datetime import datetime, timezone
from server.app.config import settings
from tests.conftest import TEST_API_KEY
import agentshield
from agentshield import trace_tool_call, trace_model_call
from agentshield.exceptions import PolicyViolationError


@pytest.fixture
def configure_budget_policy(client):
    """Upload a policy with strict budget, token, step, and wall-clock limits."""
    policy_yaml = """
version: 1
default_action: allow
limits:
  max_cost_per_run: 0.05
  max_tokens_per_run: 500
  max_steps_per_run: 3
  max_wall_time_seconds: 2.0
rules:
  - id: allow_all_tools
    tool: "*"
    action: allow
"""
    client.post(
        "/policies",
        json={"yaml_content": policy_yaml, "change_note": "Budget test policy"},
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
    )


def test_budget_cost_limit_rejection(client, configure_budget_policy):
    """Ensure tool execution is blocked when running cost exceeds max_cost_per_run."""
    agentshield.init(
        server_url="http://testserver",
        api_key=TEST_API_KEY,
        http_client=client,
        check_policy=True,
    )

    @trace_tool_call(name="paid_api_call")
    def execute_api():
        return "api_ok"

    with pytest.raises(PolicyViolationError) as exc_info:
        with agentshield.run(task_id="cost-limit-task") as ctx:
            # Simulate high prior cost
            ctx.running_cost = 0.10
            execute_api()

    assert "limit:max_cost_per_run" in exc_info.value.rule_id
    assert "Cost limit exceeded" in exc_info.value.reason
    assert ctx.spans[0]["policy_decision"] == "deny"
    assert "limit:max_cost_per_run" in ctx.spans[0]["policy_rule_id"]


def test_budget_token_limit_rejection(client, configure_budget_policy):
    """Ensure tool execution is blocked when running tokens exceed max_tokens_per_run."""
    agentshield.init(
        server_url="http://testserver",
        api_key=TEST_API_KEY,
        http_client=client,
        check_policy=True,
    )

    @trace_tool_call(name="data_processing")
    def process_data():
        return "processed"

    with pytest.raises(PolicyViolationError) as exc_info:
        with agentshield.run(task_id="token-limit-task") as ctx:
            # Simulate high prior token consumption
            ctx.running_tokens = 750
            process_data()

    assert "limit:max_tokens_per_run" in exc_info.value.rule_id
    assert "Token limit exceeded" in exc_info.value.reason
    assert ctx.spans[0]["policy_decision"] == "deny"


def test_budget_step_limit_rejection(client, configure_budget_policy):
    """Ensure runaway tool loop is terminated when max_steps_per_run is reached."""
    agentshield.init(
        server_url="http://testserver",
        api_key=TEST_API_KEY,
        http_client=client,
        check_policy=True,
    )

    @trace_tool_call(name="crawler_step")
    def crawl_page(url: str):
        return f"content of {url}"

    with agentshield.run(task_id="step-limit-task") as ctx:
        # Step 1: OK
        res1 = crawl_page("http://site.com/1")
        assert res1 is not None

        # Step 2: OK
        res2 = crawl_page("http://site.com/2")
        assert res2 is not None

        # Step 3: Hits max_steps_per_run limit (limit is 3)
        with pytest.raises(PolicyViolationError) as exc_info:
            crawl_page("http://site.com/3")

        assert "limit:max_steps_per_run" in exc_info.value.rule_id
        assert "Step limit reached" in exc_info.value.reason


def test_budget_wall_time_limit_rejection(client, db_session, configure_budget_policy):
    """Ensure long-running agent execution is terminated when max_wall_time_seconds is exceeded (server-side)."""
    import time
    from datetime import timedelta
    from server.app.models.run import Run

    agentshield.init(
        server_url="http://testserver",
        api_key=TEST_API_KEY,
        http_client=client,
        check_policy=True,
    )

    @trace_tool_call(name="timed_tool")
    def slow_action():
        return "done"

    with pytest.raises(PolicyViolationError) as exc_info:
        with agentshield.run(task_id="wall-time-task") as ctx:
            # Pre-seed run with an aged started_at in the database to test server-side elapsed time computation
            aged_time = datetime.now(timezone.utc) - timedelta(seconds=5)
            aged_run = Run(id=ctx.run_id, started_at=aged_time, outcome="in_progress")
            db_session.add(aged_run)
            db_session.commit()

            slow_action()

    assert "limit:max_wall_time_seconds" in exc_info.value.rule_id
    assert "Wall-clock time limit exceeded" in exc_info.value.reason


def test_budget_clean_execution_within_limits(client, configure_budget_policy):
    """Ensure agent runs within all budget, token, step, and time limits execute without hindrance."""
    agentshield.init(
        server_url="http://testserver",
        api_key=TEST_API_KEY,
        http_client=client,
        check_policy=True,
    )

    @trace_tool_call(name="safe_calc")
    def calculate(x: int):
        return x * 2

    with agentshield.run(task_id="within-limits-task") as ctx:
        out = calculate(21)
        assert out == 42
        assert len(ctx.spans) == 1
        assert ctx.spans[0]["policy_decision"] == "allow"
