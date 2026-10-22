"""Tests for numeric/membership policy constraints and the live-agent HTTP endpoints.

Network egress is disabled so live-agent executions use labelled simulations, keeping the
suite hermetic while still exercising the real policy engine and DB write path.
"""

import pytest

from server.app.config import settings
from server.app.services import live_integrations as li
from server.app.services.policy_engine import evaluate_policy, parse_policy_yaml, RunState

NUMERIC_POLICY = """
version: 1
default_action: deny
rules:
  - id: allow_micro
    tool: stripe_payment
    action: allow
    constraints:
      amount: { lt: 100 }
  - id: review_mid
    tool: stripe_payment
    action: require_approval
    constraints:
      amount: { gte: 100, lt: 500 }
  - id: deny_large
    tool: stripe_payment
    action: deny
    constraints:
      amount: { gte: 500 }
"""

_ADMIN = {"X-Admin-Token": "test-admin-secret"}


@pytest.fixture(scope="module")
def numeric_policy():
    return parse_policy_yaml(NUMERIC_POLICY)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_ALLOW_NETWORK", False)
    li.reset_network_probe_cache()
    yield
    li.reset_network_probe_cache()


@pytest.fixture
def headers():
    return {"X-API-Key": "test-agent-key-secret-123"}


@pytest.fixture(autouse=True)
def _default_policy_active(client):
    """Other suites (budget limits, policy engine) POST policies that stay globally active
    because the session-scoped DB is shared. Re-activate the shipped default policy so this
    module's expectations on tool tiering and approvals hold regardless of test order.
    """
    with open("policies/default_policy.yaml", "r", encoding="utf-8") as fh:
        yaml_content = fh.read()
    resp = client.post(
        "/policies",
        json={"yaml_content": yaml_content, "change_note": "test: restore default policy"},
        headers=_ADMIN,
    )
    assert resp.status_code in (200, 201), resp.text


@pytest.mark.parametrize(
    "amount,expected",
    [
        (10.0, "allow"),
        (99.99, "allow"),
        (100.0, "require_approval"),
        (499.99, "require_approval"),
        (500.0, "deny"),
        (1250.0, "deny"),
        ("1250", "deny"),          # numeric string still tiers
        ("$1,250.00", "deny"),     # currency symbol + separators tolerated
        ("abc", "deny"),           # non-numeric never matches -> default deny
        (None, "deny"),            # missing arg never matches -> default deny
        (True, "deny"),            # bool must not satisfy a numeric constraint
    ],
)
def test_numeric_tiering_is_fail_closed(numeric_policy, amount, expected):
    args = {"amount": amount} if amount is not None else {}
    result = evaluate_policy("stripe_payment", args, numeric_policy, RunState(run_id="t"))
    assert result.decision == expected


def test_boolean_arg_can_match_boolean_constraint():
    policy = parse_policy_yaml("""
version: 1
default_action: deny
rules:
  - id: verified_ok
    tool: stripe_payment
    action: allow
    constraints:
      vendor_verified: { equals: "true" }
""")
    allowed = evaluate_policy("stripe_payment", {"vendor_verified": True}, policy, RunState(run_id="t"))
    denied = evaluate_policy("stripe_payment", {"vendor_verified": False}, policy, RunState(run_id="t"))
    assert allowed.decision == "allow"
    assert denied.decision == "deny"


def test_membership_constraints():
    policy = parse_policy_yaml("""
version: 1
default_action: deny
rules:
  - id: prod_ok
    tool: deploy
    action: allow
    constraints:
      env: { in: ["staging", "dev"] }
""")
    assert evaluate_policy("deploy", {"env": "dev"}, policy, RunState(run_id="t")).decision == "allow"
    assert evaluate_policy("deploy", {"env": "prod"}, policy, RunState(run_id="t")).decision == "deny"


# --------------------------------------------------------------------------------------
# Live-agent HTTP endpoints
# --------------------------------------------------------------------------------------

def test_providers_endpoint_reports_modes(client, headers):
    resp = client.get("/live-agent/providers", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    ids = {p["id"] for p in payload["providers"]}
    assert {"github", "open_meteo", "hackernews", "stripe", "gemini", "openai"} <= ids
    for p in payload["providers"]:
        assert p["mode"] in ("live", "simulated", "unconfigured", "offline")


def test_scenarios_endpoint_includes_execution_mode(client, headers):
    resp = client.get("/live-agent/scenarios", headers=headers)
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) >= 7
    for s in scenarios:
        assert s["execution_mode"] in ("live", "simulated", "blocked")
        assert s["provider_id"]


def test_execute_allow_scenario_runs_and_persists(client, headers, db_session):
    resp = client.post("/live-agent/execute", json={"scenario": "github_read"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_decision"] == "allow"
    assert body["execution_mode"] == "offline"  # network disabled in this test
    assert body["run_id"].startswith("live-github_read")
    assert body["api_response"]["execution_mode"] == "offline"


def test_execute_blocked_payment_scenario(client, headers):
    resp = client.post("/live-agent/execute", json={"scenario": "stripe_payment_block"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_decision"] == "deny"
    assert body["policy_rule_id"] in ("block_large_payment", "block_excessive_payment")
    assert body["execution_mode"] == "blocked"


def test_execute_hitl_scenario_creates_pending_approval(client, headers, db_session):
    """Regression: compute_call_hash(run_id, tool_name, args) arity bug caused a 500 here."""
    resp = client.post("/live-agent/execute", json={"scenario": "github_delete_hitl"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_decision"] == "require_approval"
    assert body["approval_id"]


def test_execute_pii_email_scenario_redacts_before_gate(client, headers):
    resp = client.post("/live-agent/execute", json={"scenario": "pii_redaction_email"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_decision"] == "require_approval"
    # stored args must not retain the raw SSN
    assert "456-78-9012" not in str(body["api_response"])


def test_execute_unknown_scenario_400(client, headers):
    resp = client.post("/live-agent/execute", json={"scenario": "does_not_exist"}, headers=headers)
    assert resp.status_code == 400


def test_invoke_free_form_llm(client, headers):
    resp = client.post(
        "/live-agent/invoke",
        json={"tool_name": "llm_chat", "tool_args": {"prompt": "hello", "model": "gpt-4o-mini"}},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_decision"] == "allow"
    assert body["execution_mode"] == "simulated"
    assert body["provider_id"] == "openai"


def test_invoke_unknown_tool_400(client, headers):
    resp = client.post("/live-agent/invoke", json={"tool_name": "not_a_tool", "tool_args": {}}, headers=headers)
    assert resp.status_code == 400
    assert "Unknown tool_name" in resp.json()["detail"]


def test_invoke_url_reputation_reports_verdict(client, headers):
    """Checking a known-bad URL must return the verdict, not be blocked itself."""
    resp = client.post(
        "/live-agent/invoke",
        json={"tool_name": "url_reputation", "tool_args": {"url": "https://paypa1-secure-verify.com/x"}},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_response"]["should_block"] is True


def test_invoke_crawl_page_blocked_by_threat_intel_gate(client, headers):
    """The gate protects tools that FETCH a URL: crawling a known-phish domain is denied."""
    resp = client.post(
        "/live-agent/invoke",
        json={"tool_name": "crawl_page", "tool_args": {"url": "https://paypa1-secure-verify.com/x"}},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_decision"] == "deny"
    assert body["policy_rule_id"] == "threat_intel_block"
    assert body["api_response"]["threat_intel"]["should_block"] is True


def test_invoke_crawl_page_benign_url_allowed(client, headers):
    resp = client.post(
        "/live-agent/invoke",
        json={"tool_name": "crawl_page", "tool_args": {"url": "https://docs.python.org/3/"}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["policy_decision"] == "allow"


def test_invoke_stripe_amount_tiers(client, headers):
    blocked = client.post(
        "/live-agent/invoke",
        json={"tool_name": "stripe_payment", "tool_args": {"amount": 1250.0, "recipient": "Offshore"}},
        headers=headers,
    ).json()
    assert blocked["policy_decision"] == "deny"

    review = client.post(
        "/live-agent/invoke",
        json={"tool_name": "stripe_payment", "tool_args": {"amount": 250.0, "recipient": "Vendor"}},
        headers=headers,
    ).json()
    assert review["policy_decision"] == "require_approval"


def test_compare_models_endpoint(client, headers):
    resp = client.post(
        "/live-agent/compare-models",
        json={"prompt": "compare", "model_a": "gemini-2.5-flash", "model_b": "gpt-4o"},
        headers=headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["results"]) == 2
    assert payload["comparison"]["cheapest_model"] == "gemini-2.5-flash"
