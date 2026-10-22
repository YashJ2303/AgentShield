import os
import sys
import time
import json
import uuid
import threading
from datetime import datetime, timezone
import httpx

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sdk.agentshield import init, run as agentshield_run, trace_tool_call
from server.app.config import settings

SERVER_URL = "http://127.0.0.1:8000"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or settings.ADMIN_TOKEN or "agentshield-admin-supersecret-token-2026"
API_KEY = "agentshield-dev-key-12345"

print("=" * 80)
print("AGENTSHIELD MILESTONE 5: HUMAN-IN-THE-LOOP APPROVAL DEMO")
print("=" * 80)

# Step 1: Upload a policy requiring human approval for wire transfers
policy_yaml = """
version: 1
default_action: allow
rules:
  - id: require_approval_wire_transfer
    tool: wire_transfer
    action: require_approval
    timeout_seconds: 12
"""

print("\n[Step 1] Uploading security policy with 'require_approval' rule...")
with httpx.Client(base_url=SERVER_URL) as client:
    p_resp = client.post(
        "/policies",
        headers={"X-Admin-Token": ADMIN_TOKEN},
        json={
            "yaml_content": policy_yaml,
            "change_note": "Production financial operations require dual human sign-off"
        }
    )
    if p_resp.status_code == 201:
        print(f"Policy Version {p_resp.json()['version_number']} active! Rule ID: require_approval_wire_transfer")
    else:
        print(f"Policy upload response: {p_resp.status_code} - {p_resp.text}")

# Step 2: Initialize SDK
sdk_client = init(
    server_url=SERVER_URL,
    api_key=API_KEY,
    admin_token=ADMIN_TOKEN,
    fail_mode="fail_closed",
)

# Step 3: Define instrumented tool
@trace_tool_call(name="wire_transfer")
def wire_transfer(recipient: str, amount: float, authorization_code: str):
    print(f"\n[TOOL EXECUTION RESUMED] --> Dispatching wire transfer:")
    print(f"   Recipient: {recipient}")
    print(f"   Amount: ${amount:.2f}")
    print(f"   Auth Code: {authorization_code}")
    return {
        "status": "COMPLETED",
        "tx_hash": f"0x{uuid.uuid4().hex}",
        "settled_at": datetime.now(timezone.utc).isoformat(),
        "amount": amount
    }

# Step 4: Human reviewer simulator thread
def simulate_human_reviewer():
    time.sleep(1.8)
    print("\n[HUMAN OPERATOR / DASHBOARD SIMULATOR]")
    print("--> Querying GET /approvals?status=pending...")
    with httpx.Client(base_url=SERVER_URL) as client:
        res = client.get("/approvals?status=pending")
        items = res.json()
        if not items:
            print("--> No pending approvals found!")
            return
        
        pending_item = items[0]
        app_id = pending_item["id"]
        print(f"--> Found pending approval: {app_id}")
        print(f"    Tool: {pending_item['tool_name']}")
        print(f"    Run ID: {pending_item['run_id']}")
        print(f"    Tool Arguments: {json.dumps(pending_item['tool_args'])}")
        print(f"    Call Hash: {pending_item['call_hash']}")
        print(f"    Remaining Window: {pending_item['remaining_seconds']}s")

        print("--> Recording approval decision via POST /approvals/{id}/decision (with X-Admin-Token)...")
        dec_resp = client.post(
            f"/approvals/{app_id}/decision",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={
                "decision": "approve",
                "reason": "Authorized by Treasury Desk: Compliance KYC check passed.",
                "decided_by": "treasury_director"
            }
        )
        print(f"--> Decision Response [{dec_resp.status_code}]: {json.dumps(dec_resp.json(), indent=2)}")

# Step 5: Execute Agent Run with approval interception
reviewer_thread = threading.Thread(target=simulate_human_reviewer, daemon=True)
reviewer_thread.start()

run_id = str(uuid.uuid4())
print(f"\n[Step 2] Launching AI Agent Execution Run: {run_id}")
print("Agent attempts privileged tool call: wire_transfer(recipient='corp_supplier_llc', amount=250000.0)...")

start_mono = time.monotonic()
with agentshield_run(run_id=run_id, task_id="treasury-disbursement", model="gpt-4o") as ctx:
    print("[AGENT] Pausing on tool call boundary... Waiting for Human Approval...")
    tool_output = wire_transfer(
        recipient="corp_supplier_llc",
        amount=250000.0,
        authorization_code="sk-live-secret-treasury-passkey-12345678"
    )
    print(f"\n[AGENT] Tool call completed! Result: {json.dumps(tool_output, indent=2)}")

reviewer_thread.join(timeout=5.0)
elapsed_total = time.monotonic() - start_mono
print(f"\n[Step 3] Run Finished in {elapsed_total:.2f}s")

# Step 6: Query server trace to inspect final span state
print("\n[Step 4] Querying Server Trace from GET /runs/{run_id} to verify recorded telemetry...")
time.sleep(0.5)
with httpx.Client(base_url=SERVER_URL) as client:
    run_resp = client.get(f"/runs/{run_id}")
    if run_resp.status_code == 200:
        run_data = run_resp.json()
        print(f"\nRun Outcome: {run_data.get('outcome')}")
        print(f"Step Count: {run_data.get('step_count')}")
        spans = run_data.get("spans", [])
        print(f"Spans Recorded: {len(spans)}")
        for sp in spans:
            print("\n---------------- Recorded Span Telemetry ----------------")
            print(f"Span ID:         {sp.get('id')}")
            print(f"Sequence Number: {sp.get('sequence_number')}")
            print(f"Span Name:       {sp.get('name')} ({sp.get('span_type')})")
            print(f"Policy Decision: {sp.get('policy_decision')}")
            print(f"Policy Rule ID:  {sp.get('policy_rule_id')}")
            print(f"Redaction Count: {sp.get('redaction_count')}")
            print(f"Latency:         {sp.get('latency_ms')}ms")
            print(f"Input Payload:   {json.dumps(sp.get('input_payload'))}")
            print(f"Output Payload:  {json.dumps(sp.get('output_payload'))}")
            print("---------------------------------------------------------")
    else:
        print(f"Failed to query run: {run_resp.status_code} {run_resp.text}")

print("\n" + "=" * 80)
print("END OF DEMONSTRATION")
print("=" * 80)
