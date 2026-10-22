import pytest
import uuid
from server.app.schemas.policy import PolicyConfig, PolicyRule, PolicyLimits
from server.app.services.policy_engine import (
    evaluate_policy,
    parse_policy_yaml,
    RunState,
    PolicyDecisionResult,
)
from server.app.services.rate_limiter import increment_rate_limit_counter, get_rate_limit_counts_for_run
from server.app.models.policy import PolicyVersion
from server.app.config import settings
from tests.conftest import TEST_API_KEY
import agentshield
from agentshield import trace_tool_call
from agentshield.exceptions import PolicyViolationError, GatewayUnreachableError


# =====================================================================
# 1. Pure Function Policy Check Tests
# =====================================================================

def test_pure_function_evaluate_policy_allow_and_deny():
    yaml_text = """
version: 1
default_action: deny
rules:
  - id: allow_search
    tool: web_search
    action: allow
    constraints:
      query:
        regex: "^[a-z0-9 ]+$"
  - id: ask_email
    tool: send_email
    action: require_approval
    timeout_seconds: 45
"""
    policy = parse_policy_yaml(yaml_text)
    state = RunState(run_id="run-1")

    # Allowed tool call
    res_allowed = evaluate_policy("web_search", {"query": "python tutorials"}, policy, state)
    assert res_allowed.decision == "allow"
    assert res_allowed.rule_id == "allow_search"

    # Regex constraint violation -> falls back to default deny
    res_violation = evaluate_policy("web_search", {"query": "DELETE * FROM users;"}, policy, state)
    assert res_violation.decision == "deny"

    # Require approval tool
    res_appr = evaluate_policy("send_email", {"to": "boss@corp.com"}, policy, state)
    assert res_appr.decision == "require_approval"
    assert res_appr.rule_id == "ask_email"
    assert res_appr.timeout_seconds == 45

    # Unlisted tool -> default deny
    res_unlisted = evaluate_policy("shell_exec", {"cmd": "whoami"}, policy, state)
    assert res_unlisted.decision == "deny"
    assert res_unlisted.rule_id == "default_policy"


def test_pure_function_budget_limits_enforced():
    yaml_text = """
version: 1
default_action: allow
limits:
  max_cost_per_run: 1.50
  max_tokens_per_run: 10000
  max_steps_per_run: 5
  max_wall_time_seconds: 60.0
rules:
  - id: allow_all
    tool: "*"
    action: allow
"""
    policy = parse_policy_yaml(yaml_text)

    # 1. Cost limit breach
    state_cost = RunState(run_id="r1", current_cost=1.55)
    res_cost = evaluate_policy("tool_a", {}, policy, state_cost)
    assert res_cost.decision == "deny"
    assert "limit:max_cost_per_run" in res_cost.rule_id

    # 2. Token limit breach
    state_tokens = RunState(run_id="r2", current_tokens=10500)
    res_tok = evaluate_policy("tool_a", {}, policy, state_tokens)
    assert res_tok.decision == "deny"
    assert "limit:max_tokens_per_run" in res_tok.rule_id

    # 3. Step limit breach
    state_steps = RunState(run_id="r3", current_steps=5)
    res_steps = evaluate_policy("tool_a", {}, policy, state_steps)
    assert res_steps.decision == "deny"
    assert "limit:max_steps_per_run" in res_steps.rule_id

    # 4. Wall-clock limit breach
    state_time = RunState(run_id="r4", elapsed_wall_time_seconds=65.0)
    res_time = evaluate_policy("tool_a", {}, policy, state_time)
    assert res_time.decision == "deny"
    assert "limit:max_wall_time_seconds" in res_time.rule_id


# =====================================================================
# 2. YAML Validation & Resilience Tests
# =====================================================================

def test_policy_yaml_validation_errors():
    # Empty YAML
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_policy_yaml("")

    # Syntax error
    with pytest.raises(ValueError, match="Invalid YAML syntax"):
        parse_policy_yaml("version: 1\n  bad_indent:\n- invalid")

    # Duplicate rule IDs
    dup_yaml = """
version: 1
default_action: deny
rules:
  - id: rule_one
    tool: tool_a
    action: allow
  - id: rule_one
    tool: tool_b
    action: allow
"""
    with pytest.raises(ValueError, match="Duplicate rule ID"):
        parse_policy_yaml(dup_yaml)

    # Unreachable rule after unconditional wildcard
    unreachable_yaml = """
version: 1
default_action: deny
rules:
  - id: allow_everything
    tool: "*"
    action: allow
  - id: unreachable_rule
    tool: specific_tool
    action: deny
"""
    with pytest.raises(ValueError, match="Unreachable rule"):
        parse_policy_yaml(unreachable_yaml)


# =====================================================================
# 3. Policy API & Admin Token Tests
# =====================================================================

def test_policy_admin_token_auth_and_versioning(client, db_session):
    admin_token = settings.ADMIN_TOKEN

    valid_policy_yaml = """
version: 2
default_action: deny
rules:
  - id: safe_echo
    tool: echo_tool
    action: allow
"""

    # 1. Missing Admin Token -> 403
    resp_no_token = client.post("/policies", json={"yaml_content": valid_policy_yaml})
    assert resp_no_token.status_code == 403

    # 2. Invalid Admin Token -> 403
    resp_bad_token = client.post(
        "/policies",
        json={"yaml_content": valid_policy_yaml},
        headers={"X-Admin-Token": "wrong-token-abc"},
    )
    assert resp_bad_token.status_code == 403

    # 3. Valid Admin Token -> 201 Created
    resp_ok = client.post(
        "/policies",
        json={"yaml_content": valid_policy_yaml, "change_note": "Added echo_tool rule"},
        headers={"X-Admin-Token": admin_token},
    )
    assert resp_ok.status_code == 201
    created_ver = resp_ok.json()["version_number"]

    # 4. Invalid YAML rejected with 422; previous active version preserved
    resp_invalid = client.post(
        "/policies",
        json={"yaml_content": "version: 2\ndefault_action: invalid_action\nrules: []"},
        headers={"X-Admin-Token": admin_token},
    )
    assert resp_invalid.status_code == 422

    # Active policy should still be version created_ver
    active_resp = client.get("/policies")
    assert active_resp.status_code == 200
    assert active_resp.json()["version_number"] == created_ver

    # 5. Rollback with Admin Token
    rollback_resp = client.post(
        "/policies/rollback",
        json={"target_version_number": 1},
        headers={"X-Admin-Token": admin_token},
    )
    assert rollback_resp.status_code == 200
    assert rollback_resp.json()["active_version"] == 1


def test_verify_admin_token_hmac_comparison():
    from unittest.mock import patch
    from fastapi import HTTPException
    from server.app.services.auth import verify_admin_token

    with patch.object(settings, "ADMIN_TOKEN", "secure-admin-token-xyz"):
        # Valid token
        assert verify_admin_token("secure-admin-token-xyz") == "secure-admin-token-xyz"
        # Valid token with whitespace trimming
        assert verify_admin_token("  secure-admin-token-xyz  ") == "  secure-admin-token-xyz  "

        # Invalid token (wrong value)
        with pytest.raises(HTTPException) as exc:
            verify_admin_token("wrong-token")
        assert exc.value.status_code == 403

        # Invalid token (prefix only)
        with pytest.raises(HTTPException) as exc:
            verify_admin_token("secure-admin-token")
        assert exc.value.status_code == 403

        # Missing token (None)
        with pytest.raises(HTTPException) as exc:
            verify_admin_token(None)
        assert exc.value.status_code == 403

        # Empty token ("")
        with pytest.raises(HTTPException) as exc:
            verify_admin_token("")
        assert exc.value.status_code == 403

    # Server unconfigured ADMIN_TOKEN -> 500
    with patch.object(settings, "ADMIN_TOKEN", None):
        with pytest.raises(HTTPException) as exc:
            verify_admin_token("any-token")
        assert exc.value.status_code == 500



# =====================================================================
# 4. Atomic DB Rate Limit Counter Tests
# =====================================================================

def test_atomic_db_rate_limit_increments(db_session):
    run_id = str(uuid.uuid4())
    tool_name = "crawler"

    c1 = increment_rate_limit_counter(db_session, run_id, tool_name)
    assert c1 == 1

    c2 = increment_rate_limit_counter(db_session, run_id, tool_name)
    assert c2 == 2

    c3 = increment_rate_limit_counter(db_session, run_id, tool_name)
    assert c3 == 3

    counts = get_rate_limit_counts_for_run(db_session, run_id)
    assert counts[tool_name] == 3


# =====================================================================
# 5. Gateway Check via TestClient & Policy Span Logging
# =====================================================================

def test_gateway_check_logs_decision_and_rule_on_span(client, db_session):
    # Ensure active policy has sql_query rule
    policy_yaml = """
version: 10
default_action: deny
rules:
  - id: allow_read_queries
    tool: sql_query
    action: allow
    sql_check:
      blocked_operations: [DROP, TRUNCATE, ALTER]
      require_where_clause_on: [UPDATE, DELETE]
"""
    client.post(
        "/policies",
        json={"yaml_content": policy_yaml, "change_note": "Test SQL policy"},
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
    )

    # Initialize SDK pointing to in-memory FastAPI TestClient
    agentshield.init(
        server_url="http://testserver",
        api_key=TEST_API_KEY,
        http_client=client,
        check_policy=True,
    )

    # 1. Allowed tool call
    @trace_tool_call(name="sql_query")
    def run_safe_query(query: str):
        return [{"id": 1, "name": "Alice"}]


    with agentshield.run(task_id="sql-task-safe") as ctx:
        res = run_safe_query("SELECT id, name FROM users WHERE id = 1;")
        assert len(res) == 1

    span = ctx.spans[0]
    assert span["policy_decision"] == "allow"
    assert span["policy_rule_id"] == "allow_read_queries"
    assert span["policy_version_id"] is not None

    # 2. Blocked tool call (destructive SQL DROP)
    @trace_tool_call(name="sql_query")
    def run_destructive_query(query: str):
        return "dropped"

    with pytest.raises(PolicyViolationError) as exc_info:
        with agentshield.run(task_id="sql-task-unsafe") as ctx_unsafe:
            run_destructive_query("DROP TABLE users;")

    assert "allow_read_queries" in exc_info.value.rule_id
    assert "Destructive SQL operation" in exc_info.value.reason or "Blocked SQL operation" in exc_info.value.reason
    blocked_span = ctx_unsafe.spans[0]
    assert blocked_span["policy_decision"] == "deny"
    assert blocked_span["policy_rule_id"] == "allow_read_queries"
    assert blocked_span["policy_version_id"] is not None


# =====================================================================
# 6. SDK Fail-Closed & Fail-Open Option Tests
# =====================================================================

def test_sdk_fail_closed_when_gateway_unreachable():
    agentshield.init(
        server_url="http://127.0.0.1:59999",
        fail_mode="fail_closed",
        check_policy=True,
        gateway_timeout=0.1,
        timeout=0.1,
    )

    @trace_tool_call(name="dangerous_action")
    def run_action():
        return "executed"

    with pytest.raises(GatewayUnreachableError):
        with agentshield.run(task_id="test-fail-closed") as ctx:
            run_action()

    assert len(ctx.spans) == 1
    assert ctx.spans[0]["policy_decision"] == "deny"


def test_sdk_fail_open_option():
    agentshield.init(
        server_url="http://127.0.0.1:59999",
        fail_mode="fail_open",
        check_policy=True,
        gateway_timeout=0.1,
        timeout=0.1,
    )

    @trace_tool_call(name="non_critical_action")
    def run_safe_action():
        return "allowed_under_fail_open"

    with agentshield.run(task_id="test-fail-open") as ctx:
        result = run_safe_action()
        assert result == "allowed_under_fail_open"


# =====================================================================
# 7. Explicit Named Argument Binding & Bypass Prevention Tests
# =====================================================================

def test_named_argument_binding_and_bypass_prevention():
    yaml_text = """
version: 1
default_action: deny
rules:
  - id: check_raw_sql
    tool: db_exec
    action: allow
    sql_check:
      arg: raw_sql
      allowed_operations: [SELECT]
  - id: check_restricted_path
    tool: file_reader
    action: allow
    path_arg: target_file
    path_allowlist: ["./sandbox"]
  - id: check_target_domain
    tool: http_fetch
    action: allow
    domain_arg: dest_url
    domain_allowlist: ["api.stripe.com"]
"""
    policy = parse_policy_yaml(yaml_text)
    state = RunState(run_id="run-bypass-test")

    # A. SQL Check: safe decoy in 'query', dangerous SQL in bound 'raw_sql'
    tool_args_attack = {
        "query": "SELECT * FROM users;",
        "raw_sql": "DROP TABLE users;",
    }
    res_attack = evaluate_policy("db_exec", tool_args_attack, policy, state)
    assert res_attack.decision == "deny"
    assert "Blocked SQL operation" in res_attack.reason or "SQL safety check failed" in res_attack.reason

    # B. SQL Check: bound argument 'raw_sql' is missing -> must fail closed (deny)
    tool_args_missing = {"query": "SELECT * FROM users;"}
    res_missing = evaluate_policy("db_exec", tool_args_missing, policy, state)
    assert res_missing.decision == "deny"
    assert "missing" in res_missing.reason

    # C. SQL Check: legitimate query in bound 'raw_sql' -> allow
    tool_args_legit = {"raw_sql": "SELECT id, name FROM users WHERE id = 10;"}
    res_legit = evaluate_policy("db_exec", tool_args_legit, policy, state)
    assert res_legit.decision == "allow"
    assert res_legit.rule_id == "check_raw_sql"

    # D. Path Check: decoy path in 'path', traversal in bound 'target_file'
    path_args_attack = {
        "path": "./sandbox/good.txt",
        "target_file": "./sandbox/../../etc/passwd",
    }
    res_path = evaluate_policy("file_reader", path_args_attack, policy, state)
    assert res_path.decision == "deny"
    assert "outside authorized directories" in res_path.reason

    # E. Path Check: bound argument 'target_file' missing -> fail closed
    res_path_missing = evaluate_policy("file_reader", {"path": "./sandbox/good.txt"}, policy, state)
    assert res_path_missing.decision == "deny"
    assert "missing" in res_path_missing.reason

    # F. Domain Check: decoy in 'url', unauthorized domain in bound 'dest_url'
    domain_args_attack = {
        "url": "https://api.stripe.com/v1/charges",
        "dest_url": "https://evil-exfiltration.com/steal",
    }
    res_domain = evaluate_policy("http_fetch", domain_args_attack, policy, state)
    assert res_domain.decision == "deny"
    assert "not in allowlist" in res_domain.reason

    # G. Domain Check: bound argument 'dest_url' missing -> fail closed
    res_domain_missing = evaluate_policy("http_fetch", {"url": "https://api.stripe.com"}, policy, state)
    assert res_domain_missing.decision == "deny"
    assert "missing" in res_domain_missing.reason


# =====================================================================
# 8. Rate Limit Concurrency Test (SQLite Table Locking)
# =====================================================================

def test_rate_limit_concurrency_sqlite(db_session):
    """
    Test atomic DB rate limit increments under concurrent execution threads.
    Note: Testing against SQLite on the Windows host. SQLite applies database/table
    locks during write transactions, whereas production PostgreSQL uses row-level
    locks via 'SELECT ... FOR UPDATE'.
    """
    import concurrent.futures

    run_id = f"concurrent-run-{uuid.uuid4()}"
    tool_name = "concurrent_crawler"
    total_calls = 20

    from server.app.database import SessionLocal

    def worker():
        s = SessionLocal()
        try:
            return increment_rate_limit_counter(s, run_id, tool_name)
        finally:
            s.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker) for _ in range(total_calls)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == total_calls
    # Verify final count in fresh session
    verify_session = SessionLocal()
    try:
        final_counts = get_rate_limit_counts_for_run(verify_session, run_id)
        assert final_counts[tool_name] == total_calls
    finally:
        verify_session.close()


# =====================================================================
# 9. Empty Active Policy Deny-All Test
# =====================================================================

def test_gateway_denies_everything_when_no_active_policy(client, db_session):
    # Deactivate any active policy records in DB
    db_session.query(PolicyVersion).update({"is_active": False})
    db_session.commit()

    resp = client.post(
        "/gateway/check",
        headers={"X-API-Key": TEST_API_KEY},
        json={
            "run_id": str(uuid.uuid4()),
            "tool_name": "any_tool",
            "tool_args": {"arg": "value"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "deny"
    assert data["rule_id"] == "no_active_policy"
    assert "No active security policy configured" in data["reason"]


# =====================================================================
# 10. Auth Guards: Mandatory Admin Token & ENV-Scoped Dev Key
# =====================================================================

def test_admin_token_mandatory_and_env_dev_key(client):
    # 1. When ADMIN_TOKEN is not configured (None or empty), admin endpoints return 500
    original_admin_token = settings.ADMIN_TOKEN
    try:
        settings.ADMIN_TOKEN = None
        resp_upload = client.post(
            "/policies",
            headers={"X-Admin-Token": "some-secret"},
            json={"yaml_content": "version: 1\nrules: []\n"},
        )
        assert resp_upload.status_code == 500
        assert "administrator token is not configured" in resp_upload.json()["detail"]
    finally:
        settings.ADMIN_TOKEN = original_admin_token

    # 2. When ENV is prod, default dev key is not accepted / seeded
    original_env = settings.ENV
    try:
        settings.ENV = "prod"
        resp_dev_key = client.post(
            "/ingest/spans",
            headers={"X-API-Key": settings.DEFAULT_API_KEY},
            json={"task_id": "test-task", "spans": []},
        )
        assert resp_dev_key.status_code == 403
        assert "Invalid or revoked API key" in resp_dev_key.json()["detail"]
    finally:
        settings.ENV = original_env


def test_simulate_policy_call_pure_and_admin_protected(client, db_session):
    from server.app.models.span import Span
    from server.app.models.rate_limit import RateLimitCounter
    from server.app.models.approval import Approval

    # 1. Missing admin token -> 403
    resp = client.post(
        "/policies/simulate-call",
        json={"tool_name": "sql_query", "tool_args": {"query": "SELECT 1;"}},
    )
    assert resp.status_code == 403

    # 2. Authorized call with destructive SQL -> returns deny
    initial_spans = db_session.query(Span).count()
    initial_counters = db_session.query(RateLimitCounter).count()
    initial_approvals = db_session.query(Approval).count()

    admin_headers = {"X-Admin-Token": settings.ADMIN_TOKEN}
    resp_deny = client.post(
        "/policies/simulate-call",
        headers=admin_headers,
        json={"tool_name": "sql_query", "tool_args": {"query": "DROP TABLE users;"}},
    )
    assert resp_deny.status_code == 200
    data_deny = resp_deny.json()
    assert data_deny["decision"] == "deny"
    assert "DROP" in data_deny["reason"]
    assert "latency_ms" in data_deny

    # 3. Authorized call with benign query -> returns allow
    resp_allow = client.post(
        "/policies/simulate-call",
        headers=admin_headers,
        json={"tool_name": "sql_query", "tool_args": {"query": "SELECT id, name FROM users WHERE id=1;"}},
    )
    assert resp_allow.status_code == 200
    assert resp_allow.json()["decision"] == "allow"

    # 4. Verify ZERO side-effects: no spans, no rate-limit counters, no approvals created
    assert db_session.query(Span).count() == initial_spans
    assert db_session.query(RateLimitCounter).count() == initial_counters
    assert db_session.query(Approval).count() == initial_approvals


