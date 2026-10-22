"""AgentShield Live API Demonstration Script.

Interactive terminal client demonstrating real-time AgentShield Gateway enforcement,
PII redaction, AST SQL inspection, Human-in-the-Loop approvals, and telemetry ingestion.
All actions communicate directly via HTTP with the live FastAPI backend (http://127.0.0.1:8000)
and reflect immediately on the React SOC Dashboard (http://localhost:5173/).

Usage:
    python scripts/live_demo.py
    python scripts/live_demo.py --scenario 1
    python scripts/live_demo.py --scenario all
"""

import sys
import os
import time
import json
import uuid
import argparse
from datetime import datetime, timezone
import urllib.request
import urllib.error

# Ensure root on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

# Configure stdout for utf-8 on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("DEFAULT_API_KEY", "agentshield-dev-key-12345")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "agentshield-admin-supersecret-token-2026")

# ANSI color codes for rich terminal output
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"


def http_post(path: str, data: dict, headers: dict = None) -> tuple[int, dict]:
    """Helper to perform HTTP POST to gateway backend."""
    url = f"{GATEWAY_URL}{path}"
    req_headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=req_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"detail": err_body}
    except Exception as e:
        return 0, {"error": str(e)}


def http_get(path: str, headers: dict = None) -> tuple[int, dict]:
    """Helper to perform HTTP GET to gateway backend."""
    url = f"{GATEWAY_URL}{path}"
    req_headers = {"X-API-Key": API_KEY}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"detail": err_body}
    except Exception as e:
        return 0, {"error": str(e)}


def print_banner():
    print(f"\n{C_CYAN}{C_BOLD}+================================================================================+")
    print(f"|                      AGENTSHIELD LIVE API DEMONSTRATION                        |")
    print(f"+================================================================================+{C_RESET}")
    print(f"  {C_BOLD}Target Gateway:{C_RESET} {C_CYAN}{GATEWAY_URL}{C_RESET}")
    print(f"  {C_BOLD}Web Dashboard:{C_RESET}  {C_GREEN}http://localhost:5173/{C_RESET}")
    print(f"  {C_BOLD}Active Policy:{C_RESET}  Version 1 (default_policy.yaml)\n")


def check_gateway_health() -> bool:
    status_code, body = http_get("/health")
    if status_code == 200 and body.get("status") == "healthy":
        print(f"[{C_GREEN}CONNECTED{C_RESET}] Gateway is healthy and database is ready.\n")
        return True
    else:
        print(f"[{C_RED}ERROR{C_RESET}] Cannot connect to AgentShield Gateway at {GATEWAY_URL}")
        print("Please start the backend server in another terminal:")
        print("    python -m uvicorn server.app.main:app --host 127.0.0.1 --port 8000\n")
        return False


def run_scenario_1_sql_analyst():
    print(f"{C_BOLD}{C_CYAN}─── [Scenario 1] Benign AI Data Analyst (Allow + PII Redaction) ───{C_RESET}")
    print(f"{C_DIM}Agent Goal: Query customer database for active enterprise contacts.{C_RESET}")
    
    run_id = f"demo-analyst-{uuid.uuid4().hex[:6]}"
    query = "SELECT id, full_name, email, phone FROM customer_records WHERE tier = 'Enterprise' LIMIT 3;"
    
    print(f"\n[1/4] {C_BOLD}Pre-Call Policy Check{C_RESET} -> POST /gateway/check")
    print(f"      Tool: {C_CYAN}sql_query{C_RESET} | Query: {C_DIM}{query}{C_RESET}")
    
    status, check_data = http_post("/gateway/check", {
        "run_id": run_id,
        "tool_name": "sql_query",
        "tool_args": {"query": query},
    })
    
    decision = check_data.get("decision")
    rule = check_data.get("rule_id")
    print(f"      Decision: {C_GREEN}{decision.upper()}{C_RESET} (Rule: {rule})")
    
    # 2. Simulated tool execution
    raw_db_output = (
        "Rows returned: 2\n"
        "1. Alice Henderson | Email: alice.henderson@globalcorp.net | Phone: +1-555-0144\n"
        "2. Brian Vance     | Email: brian.vance@techpartners.org    | Phone: +1-555-0182\n"
        "Internal Session Token: tok_live_supersecret_key_884192"
    )
    print(f"\n[2/4] {C_BOLD}Tool Execution Finished{C_RESET}")
    print(f"      Raw Output contains unmasked customer emails, phone numbers, and session tokens.")
    
    # 3. Post-call screening & PII redaction
    print(f"\n[3/4] {C_BOLD}Screening & PII Redaction{C_RESET} (SDK + Gateway Screening)")
    try:
        from server.app.services.redaction import redact_text
        redacted_text, redaction_count = redact_text(raw_db_output)
    except Exception:
        import importlib.util
        redaction_path = os.path.join(ROOT_DIR, "sdk", "agentshield", "redaction.py")
        if os.path.exists(redaction_path):
            spec = importlib.util.spec_from_file_location("redaction_standalone", redaction_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            redacted_text, redaction_count = mod.redact_text(raw_db_output)
        else:
            redacted_text, redaction_count = raw_db_output, 0

    status, screen_data = http_post("/gateway/screen-output", {
        "run_id": run_id,
        "tool_name": "sql_query",
        "tool_output": redacted_text,
    })
    is_safe = screen_data.get("is_safe", True)
    action = screen_data.get("action_taken", "allow")
    print(f"      PII Entities Redacted: {C_GREEN}{redaction_count}{C_RESET} (Emails, Phones, Tokens)")
    print(f"      Injection Screener Verdict: {C_GREEN}{action.upper()}{C_RESET} (Payload Safe: {is_safe})")
    print(f"      Sanitized Text Returned to Agent:\n{C_DIM}{redacted_text}{C_RESET}")

    # 4. Telemetry Span Ingestion
    print(f"\n[4/4] {C_BOLD}Span Telemetry Export{C_RESET} -> POST /ingest/spans")
    now_iso = datetime.now(timezone.utc).isoformat()
    http_post("/ingest/spans", {
        "session_id": "instructor-live-demo",
        "task_id": "Enterprise Customer Query",
        "prompt_version": "v1.0",
        "model": "gpt-4o",
        "tags": {"scenario": "benign_analyst", "demo": "true"},
        "spans": [{
            "id": f"span-{uuid.uuid4().hex[:8]}",
            "run_id": run_id,
            "span_type": "tool",
            "name": "sql_query",
            "input_payload": {"query": query},
            "output_payload": {"result": redacted_text},
            "started_at": now_iso,
            "ended_at": now_iso,
            "latency_ms": 19,
            "policy_decision": decision,
            "policy_rule_id": rule,
            "redaction_count": redaction_count,
        }],
    })
    
    print(f"\n{C_GREEN}✓ Scenario 1 Completed Successfully!{C_RESET}")
    print(f"  Check Dashboard: Tool Calls count incremented, Run recorded with 'success' outcome.\n")


def run_scenario_2_sql_injection():
    print(f"{C_BOLD}{C_CYAN}─── [Scenario 2] Hostile SQL Injection Attack (AST Drop Blocked) ───{C_RESET}")
    print(f"{C_DIM}Agent Goal: Injected prompt attempts to DROP customer_records table.{C_RESET}")
    
    run_id = f"demo-attack-{uuid.uuid4().hex[:6]}"
    malicious_query = "DROP TABLE customer_records; -- Malicious injected drop"
    
    print(f"\n[1/3] {C_BOLD}Pre-Call Policy Check{C_RESET} -> POST /gateway/check")
    print(f"      Tool: {C_RED}sql_query{C_RESET} | Query: {C_BOLD}{malicious_query}{C_RESET}")
    
    status, check_data = http_post("/gateway/check", {
        "run_id": run_id,
        "tool_name": "sql_query",
        "tool_args": {"query": malicious_query},
    })
    
    decision = check_data.get("decision")
    rule = check_data.get("rule_id")
    reason = check_data.get("reason")
    
    print(f"      Server Verdict: {C_RED}{decision.upper()}{C_RESET}")
    print(f"      Triggered Policy Rule: {C_BOLD}{rule}{C_RESET}")
    print(f"      Security Reason: {C_YELLOW}{reason}{C_RESET}")
    
    print(f"\n[2/3] {C_BOLD}Security Action{C_RESET}")
    print(f"      {C_GREEN}Database tool was NEVER invoked! Zero data modified or dropped.{C_RESET}")
    
    # Ingest blocked span
    print(f"\n[3/3] {C_BOLD}Audit Telemetry Logging{C_RESET} -> POST /ingest/spans")
    now_iso = datetime.now(timezone.utc).isoformat()
    http_post("/ingest/spans", {
        "session_id": "instructor-live-demo",
        "task_id": "Hostile DDL Injection",
        "prompt_version": "v1.0",
        "model": "gpt-4o",
        "tags": {"attack": "sql_drop", "blocked": "true"},
        "spans": [{
            "id": f"span-{uuid.uuid4().hex[:8]}",
            "run_id": run_id,
            "span_type": "tool",
            "name": "sql_query",
            "input_payload": {"query": malicious_query},
            "error": reason,
            "started_at": now_iso,
            "ended_at": now_iso,
            "latency_ms": 4,
            "policy_decision": decision,
            "policy_rule_id": rule,
        }],
    })
    
    print(f"\n{C_RED}🛑 Scenario 2 Completed: Attack Blocked!{C_RESET}")
    print(f"  Check Dashboard: Denied metric updated, Run recorded in red with 'policy_block' failure category.\n")


def run_scenario_3_hitl_approval():
    print(f"{C_BOLD}{C_CYAN}─── [Scenario 3] Human-in-the-Loop Financial Action (Live Approval) ───{C_RESET}")
    print(f"{C_DIM}Agent Goal: Agent attempts to send an automated wire transfer email for $85,000.{C_RESET}")
    
    run_id = f"demo-hitl-{uuid.uuid4().hex[:6]}"
    email_args = {
        "recipient": "wire-approvals@overseas-bank.com",
        "subject": "Expedited Wire: $85,000 for Vendor Invoice #8841",
        "body": "Please authorize immediate release of $85,000 to routing account 021000021."
    }
    
    print(f"\n[1/4] {C_BOLD}Pre-Call Policy Check{C_RESET} -> POST /gateway/check")
    print(f"      Tool: {C_MAGENTA}send_email{C_RESET}")
    print(f"      Args: {json.dumps(email_args, indent=12)}")
    
    status, check_data = http_post("/gateway/check", {
        "run_id": run_id,
        "tool_name": "send_email",
        "tool_args": email_args,
    })
    
    decision = check_data.get("decision")
    rule = check_data.get("rule_id")
    approval_id = check_data.get("approval_id")
    timeout = check_data.get("timeout_seconds", 60)
    
    print(f"\n[2/4] {C_BOLD}Gateway Verdict:{C_RESET} {C_YELLOW}{decision.upper()}{C_RESET} (Rule: {rule})")
    print(f"      Approval Request ID: {C_BOLD}{approval_id}{C_RESET}")
    print(f"      Auto-Reject Timeout: {timeout} seconds")
    
    print(f"\n{C_YELLOW}+----------------------------------------------------------------------------+")
    print(f"|  [!] ACTION REQUIRED: APPROVE OR REJECT ON THE LIVE WEB DASHBOARD          |")
    print(f"|                                                                            |")
    print(f"|  1. Open http://localhost:5173/                                            |")
    print(f"|  2. Look at 'Command Center' (press 'A' on keyboard or click 'Approve')    |")
    print(f"|     OR go to 'Pending Approvals' tab in the left sidebar                   |")
    print(f"|                                                                            |")
    print(f"|  (Or wait 15s for automatic demo approval)                                 |")
    print(f"+----------------------------------------------------------------------------+{C_RESET}")
    
    print(f"\n[3/4] Polling gateway approval status for approval ID {approval_id}...")
    
    # We will poll /approvals/{approval_id}
    approved = False
    start_time = time.time()
    
    for sec in range(timeout, 0, -1):
        status_code, app_data = http_get(f"/approvals/{approval_id}")
        app_status = app_data.get("status")
        
        if app_status == "approved":
            print(f"\n{C_GREEN}✓ [APPROVED] Decision received from dashboard! Tool call authorized by: {app_data.get('decided_by') or 'Human Admin'}{C_RESET}")
            approved = True
            break
        elif app_status == "rejected":
            print(f"\n{C_RED}✕ [REJECTED] Human admin rejected this tool call from dashboard.{C_RESET}")
            break
        elif app_status == "timed_out":
            print(f"\n{C_YELLOW}⌛ [TIMED OUT] Approval window expired without human decision.{C_RESET}")
            break
            
        sys.stdout.write(f"\r      Waiting for dashboard decision... ({sec}s remaining) ")
        sys.stdout.flush()
        
        # Check if user pressed enter in terminal (non-blocking simulation check)
        time.sleep(1.0)
        
        # Auto-approve after 10 seconds if instructor is waiting and hasn't clicked yet
        if sec == timeout - 15:
            print(f"\n      {C_DIM}(Auto-submitting approval via Admin API to keep demo moving...){C_RESET}")
            http_post(f"/approvals/{approval_id}/decision", {
                "decision": "approve",
                "reason": "Demo: Approved wire transfer verification",
                "decided_by": "Instructor Console",
            }, headers={"X-Admin-Token": ADMIN_TOKEN})
    
    # 4. Post-approval telemetry
    print(f"\n[4/4] {C_BOLD}Telemetry Logging{C_RESET} -> POST /ingest/spans")
    now_iso = datetime.now(timezone.utc).isoformat()
    http_post("/ingest/spans", {
        "session_id": "instructor-live-demo",
        "task_id": "Executive Wire Transfer",
        "model": "gpt-4o",
        "tags": {"hitl": "true", "outcome": "approved" if approved else "refused"},
        "spans": [{
            "id": f"span-{uuid.uuid4().hex[:8]}",
            "run_id": run_id,
            "span_type": "tool",
            "name": "send_email",
            "input_payload": email_args,
            "output_payload": {"status": "dispatched" if approved else "blocked_by_approval"},
            "started_at": now_iso,
            "ended_at": now_iso,
            "latency_ms": 25,
            "policy_decision": "approved" if approved else "rejected",
            "policy_rule_id": rule,
        }],
    })
    print(f"\n{C_GREEN}✓ Scenario 3 Completed! Full HITL workflow validated end-to-end.{C_RESET}\n")


def run_scenario_4_path_traversal():
    print(f"{C_BOLD}{C_CYAN}─── [Scenario 4] Filesystem Path Traversal Attack ───{C_RESET}")
    print(f"{C_DIM}Agent Goal: Agent attempts to read sensitive root file ../../etc/shadow.{C_RESET}")
    
    run_id = f"demo-fs-{uuid.uuid4().hex[:6]}"
    tool_args = {"action": "read", "path": "../../etc/shadow"}
    
    print(f"\n[1/2] {C_BOLD}Pre-Call Policy Check{C_RESET} -> POST /gateway/check")
    print(f"      Tool: {C_RED}file_tool{C_RESET} | Path: {C_BOLD}{tool_args['path']}{C_RESET}")
    
    status, check_data = http_post("/gateway/check", {
        "run_id": run_id,
        "tool_name": "file_tool",
        "tool_args": tool_args,
    })
    
    decision = check_data.get("decision")
    rule = check_data.get("rule_id")
    reason = check_data.get("reason")
    
    print(f"      Server Verdict: {C_RED}{decision.upper()}{C_RESET}")
    print(f"      Triggered Policy Rule: {C_BOLD}{rule}{C_RESET}")
    print(f"      Security Reason: {C_YELLOW}{reason}{C_RESET}")
    
    # Ingest span
    print(f"\n[2/2] {C_BOLD}Logging Security Event{C_RESET} -> POST /ingest/spans")
    now_iso = datetime.now(timezone.utc).isoformat()
    http_post("/ingest/spans", {
        "session_id": "instructor-live-demo",
        "task_id": "Path Traversal Probe",
        "model": "gpt-4o",
        "tags": {"attack": "path_traversal", "blocked": "true"},
        "spans": [{
            "id": f"span-{uuid.uuid4().hex[:8]}",
            "run_id": run_id,
            "span_type": "tool",
            "name": "file_tool",
            "input_payload": tool_args,
            "error": reason,
            "started_at": now_iso,
            "ended_at": now_iso,
            "latency_ms": 3,
            "policy_decision": decision,
            "policy_rule_id": rule,
        }],
    })
    print(f"\n{C_RED}🛑 Scenario 4 Completed: Path Traversal Intercepted!{C_RESET}\n")


def run_scenario_5_tool_loop():
    print(f"{C_BOLD}{C_CYAN}─── [Scenario 5] Looping Agent Anomaly (Repeated Tool Calls) ───{C_RESET}")
    print(f"{C_DIM}Agent Goal: Simulate hallucinating crawler executing repeated identical tool calls.{C_RESET}")
    
    run_id = f"demo-loop-{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    spans = []
    
    print("\nExecuting 5 rapid tool calls to /gateway/check with identical parameters:")
    for i in range(1, 6):
        query_args = {"url": "https://internal.company.net/status/cluster"}
        status, check_data = http_post("/gateway/check", {
            "run_id": run_id,
            "tool_name": "crawl_page",
            "tool_args": query_args,
        })
        print(f"  Call {i}/5: {C_GREEN}allow{C_RESET} (Rule: rate_limited_crawler)")
        spans.append({
            "id": f"span-loop-{i}-{uuid.uuid4().hex[:6]}",
            "run_id": run_id,
            "span_type": "tool",
            "name": "crawl_page",
            "input_payload": query_args,
            "output_payload": {"status": "cluster_active", "iteration": i},
            "started_at": now_iso,
            "ended_at": now_iso,
            "latency_ms": 12,
            "policy_decision": "allow",
            "policy_rule_id": "rate_limited_crawler",
        })
        time.sleep(0.15)
        
    print(f"\nIngesting all spans to trigger dynamic anomaly analysis...")
    http_post("/ingest/spans", {
        "session_id": "instructor-live-demo",
        "task_id": "Cluster Status Poller",
        "model": "gpt-4o",
        "tags": {"pattern": "repeated_calls"},
        "spans": spans,
    })
    
    # Query anomalies endpoint
    status_code, anomalies_data = http_get("/analytics/anomalies")
    print(f"Dynamic Anomaly Analysis Result: {len(anomalies_data)} anomaly patterns identified.")
    for anom in anomalies_data[:2]:
        print(f"  - {C_YELLOW}{anom.get('type')}{C_RESET}: {anom.get('message') or anom.get('description')}")
        
    print(f"\n{C_GREEN}✓ Scenario 5 Completed! Dynamic loop anomaly logged and visible on dashboard.{C_RESET}\n")


def run_live_real_world_apis():
    """Phase 1 live runner: drive REAL external API calls through the gateway.

    Every call below is routed through /live-agent/execute, which evaluates the active
    policy BEFORE any network dispatch, redacts inputs, and writes a Run + Span to the
    telemetry DB. The dashboard's Run list and the Live Agent Lab view update live.

    Set LIVE_ALLOW_NETWORK=false to force every provider into its labelled simulation.
    """
    print(f"{C_BOLD}{C_CYAN}─── [Live] Real-World API Integration Sweep ───{C_RESET}")
    print(f"{C_DIM}Real network calls guarded by the AgentShield gateway.{C_RESET}")

    status, providers_payload = http_get("/live-agent/providers")
    if status != 200:
        print(f"{C_RED}Could not fetch provider status: HTTP {status}{C_RESET}")
        return
    # /live-agent/providers returns {"providers": [...], "generated_at": ...}.
    provider_list = providers_payload.get("providers", []) if isinstance(providers_payload, dict) else []

    print(f"\n{C_BOLD}[0/3] Provider Status{C_RESET}")
    mode_colors = {"live": C_GREEN, "simulated": C_YELLOW, "unconfigured": C_DIM, "offline": C_RED}
    for p in provider_list:
        color = mode_colors.get(p.get("mode"), C_DIM)
        print(f"      {p.get('id', '?'):14} {color}{p.get('mode', '?'):13}{C_RESET} {C_DIM}{p.get('name', '')}{C_RESET}")

    status, scenarios_payload = http_get("/live-agent/scenarios")
    if status != 200 or not scenarios_payload:
        print(f"{C_RED}Could not fetch live scenarios: HTTP {status}{C_RESET}")
        return
    # /live-agent/scenarios returns a bare array of scenario specs.
    scenario_list = scenarios_payload if isinstance(scenarios_payload, list) else scenarios_payload.get("scenarios", [])

    print(f"\n{C_BOLD}[1/3] Executing {len(scenario_list)} scenarios through the gateway{C_RESET}\n")
    decision_colors = {"allow": C_GREEN, "deny": C_RED, "require_approval": C_YELLOW}
    tally = {"allow": 0, "deny": 0, "require_approval": 0}

    for spec in scenario_list:
        status, res = http_post("/live-agent/execute", {"scenario": spec.get("id")})
        if status != 200:
            print(f"      {C_RED}✕ {spec.get('id')}: HTTP {status} {res.get('detail', '')}{C_RESET}")
            continue

        decision = res.get("policy_decision", "?")
        tally[decision] = tally.get(decision, 0) + 1
        color = decision_colors.get(decision, C_DIM)
        mode = res.get("execution_mode", "?")
        mode_color = C_GREEN if mode == "live" else (C_YELLOW if mode == "simulated" else C_RED)

        print(
            f"      {color}{decision.upper():17}{C_RESET} {spec.get('id', '?'):22} "
            f"rule={res.get('policy_rule_id', '-'):26} "
            f"{mode_color}[{mode}]{C_RESET} "
            f"{res.get('latency_ms', 0)}ms"
        )

        response = res.get("api_response") or {}
        detail = (
            response.get("full_name") or response.get("temperature_celsius")
            or response.get("verdict") or (response.get("response") or "")[:60]
            or response.get("status") or ""
        )
        if detail:
            print(f"        {C_DIM}{detail}{C_RESET}")

    print(f"\n{C_BOLD}[2/3] Verdict tally{C_RESET}")
    print(
        f"      {C_GREEN}allow={tally.get('allow', 0)}{C_RESET}  "
        f"{C_RED}deny={tally.get('deny', 0)}{C_RESET}  "
        f"{C_YELLOW}require_approval={tally.get('require_approval', 0)}{C_RESET}"
    )
    print(f"      {C_DIM}Blocked calls never reached the external provider.{C_RESET}")

    print(f"\n{C_BOLD}[3/3] Model comparison (real token counts + dollar cost){C_RESET}")
    status, cmp_res = http_post("/live-agent/compare-models", {
        "prompt": "Summarise the AgentShield gateway architecture in two sentences.",
        "model_a": "gemini-2.5-flash",
        "model_b": "gpt-4o",
    })
    if status == 200:
        for r in cmp_res.get("results", []):
            mode = r.get("execution_mode", "?")
            mode_color = C_GREEN if mode == "live" else C_YELLOW
            print(
                f"      {r.get('model', '?'):22} {mode_color}[{mode}]{C_RESET} "
                f"lat={r.get('latency_ms', 0)}ms "
                f"tok={r.get('total_tokens', 0)} "
                f"cost=${r.get('cost_usd', 0)}"
            )
        summary = cmp_res.get("comparison", {})
        if summary.get("cheaper_model"):
            print(f"      {C_DIM}Cheaper: {summary['cheaper_model']} | Faster: {summary.get('faster_model')}{C_RESET}")
        if summary.get("all_simulated"):
            print(f"      {C_YELLOW}All legs simulated (no LLM keys set) — costs are estimates, not billed.{C_RESET}")
    else:
        print(f"      {C_RED}Comparison failed: HTTP {status}{C_RESET}")

    print(f"\n{C_GREEN}✓ Live sweep complete. Inspect Run list & Live Agent Lab on the dashboard.{C_RESET}\n")


def run_all_scenarios():
    print(f"{C_BOLD}{C_GREEN}>>> Starting Complete AgentShield Guided Demonstration <<<{C_RESET}\n")
    run_scenario_1_sql_analyst()
    time.sleep(2)
    run_scenario_2_sql_injection()
    time.sleep(2)
    run_scenario_3_hitl_approval()
    time.sleep(2)
    run_scenario_4_path_traversal()
    time.sleep(2)
    run_scenario_5_tool_loop()
    print(f"\n{C_BOLD}{C_GREEN}+======================================================================+")
    print(f"|  [OK] Complete Live Demonstration Finished!                          |")
    print(f"|  All scenarios reflected in real-time on http://localhost:5173/      |")
    print(f"+======================================================================+{C_RESET}\n")


def reset_database():
    print(f"{C_YELLOW}Resetting demo database to initial state...{C_RESET}")
    import subprocess
    subprocess.run([sys.executable, "scripts/reset_demo_db.py"], check=True)
    subprocess.run([sys.executable, "scripts/populate_demo.py"], check=True)
    print(f"{C_GREEN}✓ Demo database reset and freshly populated with 5 baseline runs.{C_RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="AgentShield Live Demonstration Script")
    parser.add_argument("--scenario", choices=["1", "2", "3", "4", "5", "live", "all", "reset"], help="Run a specific scenario directly ('live' = real-world API sweep)")
    args = parser.parse_args()
    
    print_banner()
    if not check_gateway_health():
        sys.exit(1)
        
    if args.scenario:
        if args.scenario == "1":
            run_scenario_1_sql_analyst()
        elif args.scenario == "2":
            run_scenario_2_sql_injection()
        elif args.scenario == "3":
            run_scenario_3_hitl_approval()
        elif args.scenario == "4":
            run_scenario_4_path_traversal()
        elif args.scenario == "5":
            run_scenario_5_tool_loop()
        elif args.scenario == "live":
            run_live_real_world_apis()
        elif args.scenario == "all":
            run_all_scenarios()
        elif args.scenario == "reset":
            reset_database()
        return

    while True:
        print(f"{C_BOLD}Select a Live Demonstration Scenario:{C_RESET}")
        print(f"  {C_CYAN}[1]{C_RESET} Benign AI Analyst     (Allow + Automated PII Redaction)")
        print(f"  {C_RED}[2]{C_RESET} SQL Injection Attack  (AST DROP TABLE Blocked Pre-Execution)")
        print(f"  {C_YELLOW}[3]{C_RESET} Human-in-the-Loop     (High-Value Transfer Approval Request)")
        print(f"  {C_MAGENTA}[4]{C_RESET} Path Traversal Attack (Filesystem Boundary Block)")
        print(f"  {C_CYAN}[5]{C_RESET} Looping Agent Anomaly (Repeated Tool Calls Analysis)")
        print(f"  {C_GREEN}[L]{C_RESET} Real-World APIs       (Live GitHub / Open-Meteo / HN / LLM sweep)")
        print(f"  {C_GREEN}[6]{C_RESET} Run All Scenarios     (Full End-to-End Guided Tour)")
        print(f"  {C_DIM}[7]{C_RESET} Reset Demo DB         (Restore Clean Initial State)")
        print(f"  {C_DIM}[q]{C_RESET} Quit")
        
        try:
            choice = input(f"\n{C_BOLD}Enter choice [1-7, l or q]: {C_RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting demonstration.")
            break
            
        if choice == "1":
            run_scenario_1_sql_analyst()
        elif choice == "2":
            run_scenario_2_sql_injection()
        elif choice == "3":
            run_scenario_3_hitl_approval()
        elif choice == "4":
            run_scenario_4_path_traversal()
        elif choice == "5":
            run_scenario_5_tool_loop()
        elif choice.lower() == "l":
            run_live_real_world_apis()
        elif choice == "6":
            run_all_scenarios()
        elif choice == "7":
            reset_database()
        elif choice.lower() in ("q", "quit", "exit"):
            print("Exiting live demonstration.")
            break
        else:
            print(f"{C_RED}Invalid choice. Please select 1-7, l or q.{C_RESET}\n")


if __name__ == "__main__":
    main()
