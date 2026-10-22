import time
import uuid
from datetime import datetime, timezone, timedelta
import pytest

from server.app.models.approval import Approval
from server.app.models.policy import PolicyVersion
from server.app.models.run import Run
from server.app.config import settings
from server.app.services.approval_manager import compute_call_hash
from sdk.agentshield.client import GatewayClient, GatewayConfig, set_active_client
from sdk.agentshield.decorators import trace_tool_call, PolicyViolationError
from sdk.agentshield import run as agentshield_run


POLICY_REQUIRE_APPROVAL_YAML = """
version: 1
default_action: allow
rules:
  - id: rule_wire_transfer
    tool: wire_transfer
    action: require_approval
    timeout_seconds: 2
  - id: rule_send_payment
    tool: send_payment
    action: require_approval
    timeout_seconds: 5
  - id: rule_sensitive_dispatch
    tool: sensitive_dispatch
    action: require_approval
    timeout_seconds: 5
"""


def _setup_approval_policy(client):
    resp = client.post(
        "/policies",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"yaml_content": POLICY_REQUIRE_APPROVAL_YAML, "change_note": "Require approval test policy"},
    )
    assert resp.status_code == 201


import threading

def test_approve_allows_call_to_proceed(client, db_session):
    """Test that human approval allows the agent tool call to proceed and records 'approved' on span."""
    _setup_approval_policy(client)
    sdk_client = GatewayClient(
        GatewayConfig(
            server_url="http://testserver",
            api_key="test-agent-key-secret-123",
            admin_token=settings.ADMIN_TOKEN,
            http_client=client,
        )
    )
    set_active_client(sdk_client)

    executed = []

    @trace_tool_call(name="wire_transfer")
    def wire_transfer(account: str, amount: float):
        executed.append((account, amount))
        return {"status": "transferred", "amount": amount}

    run_id = str(uuid.uuid4())

    def async_approver():
        # Sleep briefly to let the agent initiate the tool call and create pending approval
        time.sleep(0.3)
        res = client.get("/approvals?status=pending")
        items = res.json()
        assert len(items) > 0
        app_id = items[0]["id"]
        dec_res = client.post(
            f"/approvals/{app_id}/decision",
            headers={"X-Admin-Token": settings.ADMIN_TOKEN},
            json={"decision": "approve", "reason": "Verified executive authorization", "decided_by": "alice_admin"},
        )
        assert dec_res.status_code == 200

    th = threading.Thread(target=async_approver, daemon=True)
    th.start()

    with agentshield_run(run_id=run_id) as ctx:
        result = wire_transfer("AC-999", 500.0)
        assert result["status"] == "transferred"
        assert executed == [("AC-999", 500.0)]

        # Verify span in context
        assert len(ctx.spans) == 1
        span = ctx.spans[0]
        assert span["policy_decision"] == "approved"
        assert span["policy_rule_id"] == "rule_wire_transfer"
        assert span["name"] == "wire_transfer"

    th.join(timeout=2.0)


def test_reject_denies_call(client, db_session):
    """Test that rejecting an approval denies the call and records 'rejected' on the span."""
    _setup_approval_policy(client)
    sdk_client = GatewayClient(
        GatewayConfig(
            server_url="http://testserver",
            api_key="test-agent-key-secret-123",
            admin_token=settings.ADMIN_TOKEN,
            http_client=client,
        )
    )
    set_active_client(sdk_client)

    @trace_tool_call(name="wire_transfer")
    def wire_transfer(account: str, amount: float):
        return {"status": "transferred"}

    run_id = str(uuid.uuid4())

    def async_rejecter():
        time.sleep(0.3)
        res = client.get("/approvals?status=pending")
        items = res.json()
        assert len(items) > 0
        app_id = items[0]["id"]
        dec_res = client.post(
            f"/approvals/{app_id}/decision",
            headers={"X-Admin-Token": settings.ADMIN_TOKEN},
            json={"decision": "reject", "reason": "Suspicious account destination", "decided_by": "secops"},
        )
        assert dec_res.status_code == 200

    th = threading.Thread(target=async_rejecter, daemon=True)
    th.start()

    with agentshield_run(run_id=run_id) as ctx:
        with pytest.raises(PolicyViolationError) as exc_info:
            wire_transfer("AC-SUSPECT", 9999.0)

        assert "rejected" in str(exc_info.value).lower()

        # Verify span records rejection
        assert len(ctx.spans) == 1
        assert ctx.spans[0]["policy_decision"] == "rejected"
        assert ctx.spans[0]["policy_rule_id"] == "rule_wire_transfer"

    th.join(timeout=2.0)


def test_timeout_denies_call_and_expires_at_read_time(client, db_session):
    """Test that expired approvals auto-deny and trigger read-time transition to timed_out."""
    _setup_approval_policy(client)
    run_id = str(uuid.uuid4())

    # Create approval with 1-second timeout
    resp = client.post(
        "/gateway/check",
        headers={"X-API-Key": "test-agent-key-secret-123"},
        json={
            "run_id": run_id,
            "tool_name": "wire_transfer",
            "tool_args": {"account": "AC-1", "amount": 10.0},
        },
    )
    assert resp.status_code == 200
    approval_id = resp.json()["approval_id"]

    # Manually backdate the requested_at timestamp by 10 seconds to simulate timeout expiry
    approval = db_session.query(Approval).filter(Approval.id == approval_id).first()
    approval.requested_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db_session.commit()

    # Query GET /approvals/{id} -> must trigger read-time expiry
    get_resp = client.get(f"/approvals/{approval_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "timed_out"
    assert get_resp.json()["remaining_seconds"] == 0.0

    # Verify database record updated atomically
    db_session.refresh(approval)
    assert approval.status == "timed_out"


def test_late_approval_after_timeout_is_refused(client, db_session):
    """Test that an approval decision arriving after timeout has fired is rejected (409 Conflict)."""
    _setup_approval_policy(client)
    run_id = str(uuid.uuid4())

    resp = client.post(
        "/gateway/check",
        headers={"X-API-Key": "test-agent-key-secret-123"},
        json={
            "run_id": run_id,
            "tool_name": "wire_transfer",
            "tool_args": {"account": "AC-2", "amount": 20.0},
        },
    )
    approval_id = resp.json()["approval_id"]

    # Force expiration by backdating requested_at
    approval = db_session.query(Approval).filter(Approval.id == approval_id).first()
    approval.requested_at = datetime.now(timezone.utc) - timedelta(seconds=15)
    db_session.commit()

    # Late decision attempt
    late_resp = client.post(
        f"/approvals/{approval_id}/decision",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"decision": "approve", "reason": "Late arrival"},
    )
    assert late_resp.status_code == 409
    assert "timed out" in late_resp.json()["detail"].lower()

    # Status must remain timed_out
    db_session.refresh(approval)
    assert approval.status == "timed_out"


def test_double_decision_on_same_approval_is_refused(client, db_session):
    """Test that deciding an already-decided approval returns 409 Conflict."""
    _setup_approval_policy(client)
    run_id = str(uuid.uuid4())

    resp = client.post(
        "/gateway/check",
        headers={"X-API-Key": "test-agent-key-secret-123"},
        json={
            "run_id": run_id,
            "tool_name": "send_payment",
            "tool_args": {"dest": "bob", "amount": 100},
        },
    )
    approval_id = resp.json()["approval_id"]

    # First decision
    d1 = client.post(
        f"/approvals/{approval_id}/decision",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"decision": "approve", "reason": "First decision"},
    )
    assert d1.status_code == 200

    # Second decision (conflicting or duplicate)
    d2 = client.post(
        f"/approvals/{approval_id}/decision",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"decision": "reject", "reason": "Second decision attempt"},
    )
    assert d2.status_code == 409
    assert "already decided" in d2.json()["detail"].lower()


def test_wrong_or_missing_admin_token_is_refused(client, db_session):
    """Test that decision endpoint requires valid X-Admin-Token header."""
    _setup_approval_policy(client)
    run_id = str(uuid.uuid4())

    resp = client.post(
        "/gateway/check",
        headers={"X-API-Key": "test-agent-key-secret-123"},
        json={
            "run_id": run_id,
            "tool_name": "send_payment",
            "tool_args": {"dest": "carol", "amount": 50},
        },
    )
    approval_id = resp.json()["approval_id"]

    # 1. Missing header
    res_missing = client.post(
        f"/approvals/{approval_id}/decision",
        json={"decision": "approve"},
    )
    assert res_missing.status_code == 403

    # 2. Wrong header
    res_wrong = client.post(
        f"/approvals/{approval_id}/decision",
        headers={"X-Admin-Token": "completely-wrong-token"},
        json={"decision": "approve"},
    )
    assert res_wrong.status_code == 403


def test_approval_cannot_be_reused_for_different_args_or_run(client, db_session):
    """
    Test that an approval cannot authorize a different call, different arguments,
    or a different run, and cannot be consumed more than once (single-use).
    """
    _setup_approval_policy(client)
    run_id_a = str(uuid.uuid4())
    run_id_b = str(uuid.uuid4())

    resp = client.post(
        "/gateway/check",
        headers={"X-API-Key": "test-agent-key-secret-123"},
        json={
            "run_id": run_id_a,
            "tool_name": "send_payment",
            "tool_args": {"dest": "alice@company.com", "amount": 100},
        },
    )
    approval_id = resp.json()["approval_id"]

    # Approve original call
    client.post(
        f"/approvals/{approval_id}/decision",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"decision": "approve"},
    )

    # 1. Tamper attempt: different arguments (higher amount)
    tamper_args = client.post(
        f"/approvals/{approval_id}/consume",
        json={
            "run_id": run_id_a,
            "tool_name": "send_payment",
            "tool_args": {"dest": "alice@company.com", "amount": 999999},
        },
    )
    assert tamper_args.status_code == 400
    assert "mismatch" in tamper_args.json()["detail"].lower()

    # 2. Tamper attempt: different run ID
    tamper_run = client.post(
        f"/approvals/{approval_id}/consume",
        json={
            "run_id": run_id_b,
            "tool_name": "send_payment",
            "tool_args": {"dest": "alice@company.com", "amount": 100},
        },
    )
    assert tamper_run.status_code == 400
    assert "mismatch" in tamper_run.json()["detail"].lower()

    # 3. Legitimate consumption: matches exact (run_id_a, send_payment, original args)
    valid_consume = client.post(
        f"/approvals/{approval_id}/consume",
        json={
            "run_id": run_id_a,
            "tool_name": "send_payment",
            "tool_args": {"dest": "alice@company.com", "amount": 100},
        },
    )
    assert valid_consume.status_code == 200
    assert valid_consume.json()["valid"] is True

    # 4. Replay attempt: trying to consume the same approval a second time
    replay_consume = client.post(
        f"/approvals/{approval_id}/consume",
        json={
            "run_id": run_id_a,
            "tool_name": "send_payment",
            "tool_args": {"dest": "alice@company.com", "amount": 100},
        },
    )
    assert replay_consume.status_code == 409
    assert "already been consumed" in replay_consume.json()["detail"].lower()


def test_secrets_in_tool_args_are_redacted_in_stored_approval(client, db_session):
    """Test that secrets in tool_args are redacted before being stored in the approvals table."""
    _setup_approval_policy(client)
    run_id = str(uuid.uuid4())

    raw_tool_args = {
        "api_key": "sk-live-1234567890abcdef12345678",
        "card_number": "4111111111111111",
        "email": "user@example.com",
        "action": "execute_privileged_sync",
    }

    resp = client.post(
        "/gateway/check",
        headers={"X-API-Key": "test-agent-key-secret-123"},
        json={
            "run_id": run_id,
            "tool_name": "sensitive_dispatch",
            "tool_args": raw_tool_args,
        },
    )
    assert resp.status_code == 200
    approval_id = resp.json()["approval_id"]

    # Inspect the database record directly
    stored_app = db_session.query(Approval).filter(Approval.id == approval_id).first()
    assert stored_app is not None

    stored_args = stored_app.tool_args
    assert "sk-live-1234567890abcdef12345678" not in str(stored_args)
    assert "4111111111111111" not in str(stored_args)
    assert "[REDACTED:API_KEY]" in str(stored_args)
    assert "[REDACTED:CREDIT_CARD]" in str(stored_args)

    # But call_hash is deterministically computed and preserved
    expected_hash = compute_call_hash(run_id, "sensitive_dispatch", raw_tool_args)
    assert stored_app.call_hash == expected_hash


def test_sdk_denies_when_server_is_down_mid_poll():
    """Test that the SDK fail-closed policy denies when the server is unreachable mid-poll."""
    class CrashingHttpClient:
        def __init__(self):
            self.call_count = 0

        def get(self, url, headers=None):
            self.call_count += 1
            # Raise connection error to simulate server going down mid-poll
            raise ConnectionResetError("Connection abruptly terminated by host")

        def post(self, url, headers=None, json=None):
            raise ConnectionResetError("Server down")

    crashing_sdk_client = GatewayClient(
        GatewayConfig(
            server_url="http://testserver",
            api_key="test-key",
            fail_mode="fail_closed",
            http_client=CrashingHttpClient(),
        )
    )

    poll_result = crashing_sdk_client.poll_approval(
        approval_id="test-approval-id",
        run_id="test-run-id",
        tool_name="test_tool",
        tool_args={},
        timeout_seconds=2,
        poll_interval=0.1,
    )
    assert poll_result["decision"] == "deny"
    assert "unreachable" in poll_result["reason"].lower()


def test_number_canonicalization_stable_int_and_float():
    """Confirm number canonicalization is stable between 250000 and 250000.0 in call hashes."""
    run_id = str(uuid.uuid4())
    tool = "wire_transfer"

    hash_int = compute_call_hash(run_id, tool, {"amount": 250000, "meta": {"code": 100}})
    hash_float = compute_call_hash(run_id, tool, {"amount": 250000.0, "meta": {"code": 100.0}})
    assert hash_int == hash_float

    # Non-integer float is preserved
    hash_decimal = compute_call_hash(run_id, tool, {"amount": 250000.50})
    assert hash_decimal != hash_int


def test_raw_pre_redaction_hashing_distinguishes_different_secrets():
    """
    Confirm the call hash covers raw arguments at check time, not redacted ones.
    Two calls differing only in a secret field (e.g. auth code) MUST yield different hashes.
    """
    run_id = str(uuid.uuid4())
    tool = "authorize_transfer"

    args_a = {"account": "AC-100", "auth_code": "sk-secret-code-AAA-111"}
    args_b = {"account": "AC-100", "auth_code": "sk-secret-code-BBB-222"}

    hash_a = compute_call_hash(run_id, tool, args_a)
    hash_b = compute_call_hash(run_id, tool, args_b)

    assert hash_a != hash_b, "Hashes must differ even if secret values would be redacted in storage"


def test_timezone_mismatch_expiry(db_session):
    """Confirm expiry safely handles both naive and aware datetimes without TypeError."""
    from server.app.services.approval_manager import expire_if_timed_out

    # Naive requested_at (typical SQLite return)
    naive_past = datetime.utcnow() - timedelta(seconds=120)
    app = Approval(
        id=str(uuid.uuid4()),
        run_id="run-tz-test",
        tool_name="test_tool",
        tool_args={},
        call_hash="dummy-hash",
        status="pending",
        timeout_seconds=60,
        requested_at=naive_past,  # offset-naive
    )
    db_session.add(app)
    db_session.commit()

    # Compare against timezone-aware UTC now
    aware_now = datetime.now(timezone.utc)
    expired = expire_if_timed_out(db_session, app, now=aware_now)
    assert expired is True
    assert app.status == "timed_out"


def test_parallel_threaded_double_decision_refusal(client, db_session):
    """
    Test parallel concurrent decision submissions against the same approval.
    Guarantees atomic UPDATE ... WHERE status = 'pending'; exactly one thread
    succeeds (200 OK) and the competing thread receives 409 Conflict.
    """
    import concurrent.futures

    # Seed pending approval
    approval_id = f"concur-app-{uuid.uuid4()}"
    app = Approval(
        id=approval_id,
        run_id="run-concur-test",
        tool_name="wire_transfer",
        tool_args={"amount": 5000},
        call_hash="dummy-hash",
        status="pending",
        timeout_seconds=60,
        requested_at=datetime.now(timezone.utc),
    )
    db_session.add(app)
    db_session.commit()

    headers = {"X-Admin-Token": settings.ADMIN_TOKEN}

    def decide_worker(decision: str):
        return client.post(
            f"/approvals/{approval_id}/decision",
            headers=headers,
            json={"decision": decision, "reason": f"Decided as {decision}"},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(decide_worker, "approve")
        f2 = executor.submit(decide_worker, "reject")
        responses = [f1.result(), f2.result()]

    status_codes = [r.status_code for r in responses]
    assert 200 in status_codes, f"Expected one 200 OK, got: {status_codes}"
    assert 409 in status_codes, f"Expected one 409 Conflict, got: {status_codes}"

