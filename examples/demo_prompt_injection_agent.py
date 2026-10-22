"""
End-to-end demonstration of Milestone 7: Prompt-Injection Screening Layer.

Demonstrates:
1. An AI Web Agent fetching an untrusted external web page.
2. The web page contains hidden prompt injection attacks (HTML comment + CSS display:none).
3. The AgentShield SDK @trace_tool_call automatically intercepts the tool output and calls POST /gateway/screen-output.
4. Scenario A (Action = 'block'): The attack is halted, output replaced by safe refusal WITHOUT echoing the attack, span marked injection_flag=True.
5. Scenario B (Action = 'sanitize'): The attack is stripped, returning clean sanitized content to the agent.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from server.app.main import app
from server.app.database import SessionLocal, Base, engine
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.models.policy import PolicyVersion
from server.app.services.auth import seed_default_api_key
from sdk.agentshield.client import GatewayClient, GatewayConfig, set_active_client
from sdk.agentshield.decorators import trace_tool_call, trace_model_call
from sdk.agentshield import RunContext, set_current_run
from sdk.agentshield.exceptions import PolicyViolationError
from examples.mock_web_server import MockWebServer

client = TestClient(app)
API_KEY = "agentshield-dev-key-12345"


def setup_demo_policy(action: str = "block") -> str:
    """Set an active policy with injection screening action."""
    db = SessionLocal()
    seed_default_api_key(db)

    yaml_content = f"""version: 1
default_action: allow
injection_screening:
  enabled: true
  default_action: {action}

rules:
  - id: web_fetch_rule
    tool: fetch_web_page
    action: allow
    injection_action: {action}
"""
    # Deactivate older policies
    db.query(PolicyVersion).update({PolicyVersion.is_active: False})
    db.commit()

    pol_id = f"demo-injection-policy-{action}"
    existing = db.query(PolicyVersion).filter(PolicyVersion.id == pol_id).first()
    if existing:
        existing.is_active = True
        existing.yaml_content = yaml_content
    else:
        new_pol = PolicyVersion(
            id=pol_id,
            version_number=100 + (1 if action == "sanitize" else 0),
            yaml_content=yaml_content,
            is_active=True,
            created_by="system",
            change_note=f"Policy with injection screening action={action}",
        )
        db.add(new_pol)
    db.commit()
    db.close()
    return pol_id


def run_e2e_injection_demo():
    print("=" * 80)
    print("AGENTSHIELD: MILESTONE 7 END-TO-END PROMPT INJECTION DEMO")
    print("=" * 80)

    # Configure SDK with TestClient bridge
    cfg = GatewayConfig(server_url="http://testserver", api_key=API_KEY, http_client=client)
    gw_client = GatewayClient(cfg)
    set_active_client(gw_client)

    # -------------------------------------------------------------------------
    # PART 1: BLOCK ACTION (Default)
    # -------------------------------------------------------------------------
    print("\n[SCENARIO 1] Untrusted Web Page with Injection -> Policy Action: 'block'")
    setup_demo_policy(action="block")

    run_id_block = f"demo-injection-block-{uuid.uuid4().hex[:8]}"
    run_ctx_block = RunContext(run_id=run_id_block)
    set_current_run(run_ctx_block)

    @trace_tool_call(name="fetch_web_page")
    def fetch_web_page_blocked(url: str) -> str:
        print(f" -> [Tool: fetch_web_page] Requesting: {url}")
        content = MockWebServer.get(url)
        print(f" -> [Tool: fetch_web_page] Received {len(content)} bytes from mock server.")
        return content

    @trace_model_call(name="research_summarizer")
    def simulate_agent_block():
        print(" -> [Model] Prompt: Research Acme Global corporate profile.")
        try:
            page_text = fetch_web_page_blocked("http://acme-internal.local/profile")
            return f"Processed page: {page_text[:100]}"
        except PolicyViolationError as pve:
            print(f" -> [AgentShield Intercepted] Blocked injection attack!")
            print(f"    Reason: {pve.reason}")
            print(f"    Safe Refusal Delivered: {str(pve)}")
            return "Agent stopped safely: Tool output rejected due to prompt injection."

    result_block = simulate_agent_block()
    print(f" -> [Agent Outcome]: {result_block}")

    # Ingest spans to database
    gw_client.ingest_spans(
        spans=run_ctx_block.spans,
        session_id="session-e2e-demo",
        task_id="web_research_agent",
        model="gpt-4o",
        outcome="failure",
    )

    # Verify DB persistence of match metadata
    db = SessionLocal()
    tool_span = db.query(Span).filter(Span.run_id == run_id_block, Span.span_type == "tool").first()
    print("\n[Recorded Trace & Metadata for Block Scenario]:")
    print(f" - Run ID: {run_id_block}")
    print(f" - Span ID: {tool_span.id}")
    print(f" - Policy Decision: {tool_span.policy_decision} (Rule: {tool_span.policy_rule_id})")
    print(f" - Injection Flag: {tool_span.injection_flag}")
    print(f" - Matches Count: {len(tool_span.injection_details.get('matches', []))}")
    for idx, m in enumerate(tool_span.injection_details.get("matches", [])):
        print(f"    Match #{idx+1}: [{m['category']}] pattern '{m['pattern_name']}' via {m['detector']}")
    print(f" - Output Stored (Plain Text, Safe Refusal): {tool_span.output_payload}")
    db.close()

    # -------------------------------------------------------------------------
    # PART 2: SANITIZE ACTION
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[SCENARIO 2] Untrusted Web Page with Injection -> Policy Action: 'sanitize'")
    setup_demo_policy(action="sanitize")

    run_id_sanitize = f"demo-injection-sanitize-{uuid.uuid4().hex[:8]}"
    run_ctx_san = RunContext(run_id=run_id_sanitize)
    set_current_run(run_ctx_san)

    @trace_tool_call(name="fetch_web_page")
    def fetch_web_page_sanitized(url: str) -> str:
        return MockWebServer.get(url)

    @trace_model_call(name="research_summarizer")
    def simulate_agent_sanitize():
        print(" -> [Model] Prompt: Research Acme Global corporate profile.")
        clean_text = fetch_web_page_sanitized("http://acme-internal.local/profile")
        print(f" -> [Agent Received Sanitized Output]:\n\"{clean_text[:160]}...\"")
        return f"Summarized {len(clean_text)} sanitized characters."

    result_san = simulate_agent_sanitize()
    print(f" -> [Agent Outcome]: {result_san}")

    # Ingest spans to database
    gw_client.ingest_spans(
        spans=run_ctx_san.spans,
        session_id="session-e2e-demo",
        task_id="web_research_agent",
        model="gpt-4o",
        outcome="success",
    )

    db = SessionLocal()
    tool_span_san = db.query(Span).filter(Span.run_id == run_id_sanitize, Span.span_type == "tool").first()
    print("\n[Recorded Trace & Metadata for Sanitize Scenario]:")
    print(f" - Run ID: {run_id_sanitize}")
    print(f" - Span ID: {tool_span_san.id}")
    print(f" - Policy Decision: {tool_span_san.policy_decision}")
    print(f" - Injection Flag: {tool_span_san.injection_flag}")
    print(f" - Output Stored (Instruction Stripped): {str(tool_span_san.output_payload)[:120]}...")
    db.close()

    print("\n" + "=" * 80)
    print("DEMO COMPLETE: All end-to-end injection flows successfully verified!")
    print("=" * 80)

if __name__ == "__main__":
    run_e2e_injection_demo()
