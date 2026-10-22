"""Live Real-World Agent API execution endpoint.

Provides real-time interactive execution of agent scenarios against real-world APIs:
- GitHub Public REST API
- Open-Meteo Weather API
- Hacker News Firebase API
- Stripe Payment Intent Guardrail Engine
- SendGrid / Slack with PII Redaction
- Gemini 1.5 Flash Model Inference
"""

import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.app.database import get_db
from server.app.models.api_key import ApiKey
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.models.approval import Approval
from server.app.models.session import SessionModel
from server.app.schemas.common import SpanType, Outcome, PolicyDecision
from server.app.schemas.gateway import CheckToolRequest
from server.app.services.auth import verify_api_key
from server.app.services.policy_engine import (
    evaluate_policy,
    parse_policy_yaml,
    PolicyDecisionResult,
    RunState,
)
from server.app.services.redaction import redact_data
from server.app.services.approval_manager import compute_call_hash
from server.app.services.live_integrations import (
    MODE_LIVE,
    check_url_reputation,
    compare_llm_models,
    dispatch_communication,
    execute_llm_inference,
    fetch_github_repo,
    fetch_hackernews_top,
    fetch_open_meteo_weather,
    moderate_content,
    provider_statuses,
    providers_payload,
)
from server.app.services.real_world_tools import (
    create_payment_intent,
)

# Tool-name -> provider id, used to stamp provider_id on results and to decide which
# execution strategies are available for free-form /invoke calls.
TOOL_PROVIDER_MAP: Dict[str, str] = {
    "weather_tool": "open_meteo",
    "github_tool": "github",
    "news_tool": "hackernews",
    "stripe_payment": "stripe",
    "send_email": "sendgrid",
    "send_slack": "slack",
    "send_sms": "twilio",
    "llm_chat": "gemini",
    "url_reputation": "urlscan",
    "content_moderation": "openai",
    "crawl_page": "urlscan",
    "http_request": "http",
}
from server.app.api.v1.policies import get_active_policy_record

router = APIRouter(prefix="/live-agent", tags=["live-agent"])


class LiveScenarioSpec(BaseModel):
    id: str
    name: str
    category: str
    description: str
    target_api: str
    expected_verdict: str  # allow | deny | require_approval
    icon: str
    provider_id: str
    execution_mode: str  # live | simulated | blocked


SCENARIOS: List[LiveScenarioSpec] = [
    LiveScenarioSpec(
        id="weather_live",
        name="Live Weather Query",
        category="Public REST API (Zero-Auth)",
        description="Queries Open-Meteo REST API for live Tokyo temperature and windspeed. Verifies fast allowlist routing.",
        target_api="https://api.open-meteo.com/v1/forecast",
        expected_verdict="allow",
        icon="🌦️",
        provider_id="open_meteo",
        execution_mode="live",
    ),
    LiveScenarioSpec(
        id="github_read",
        name="GitHub Repo Metadata",
        category="Enterprise Developer API",
        description="Queries live api.github.com for repository stats (stars, forks, license). Evaluated through read allowlist.",
        target_api="https://api.github.com/repos/pallets/flask",
        expected_verdict="allow",
        icon="💻",
        provider_id="github",
        execution_mode="live",
    ),
    LiveScenarioSpec(
        id="github_delete_hitl",
        name="Destructive Repo Wipe",
        category="Critical Operation Gate",
        description="Intercepts an agent attempting to destroy a production Git repository. Triggers Human-In-The-Loop approval gate.",
        target_api="GitHub API: DELETE /repos/acme/backend",
        expected_verdict="require_approval",
        icon="⚠️",
        provider_id="github",
        execution_mode="blocked",
    ),
    LiveScenarioSpec(
        id="stripe_payment_block",
        name="FinTech Payment Cap",
        category="Financial Safety Policy",
        description="Agent attempts a $1,250 wire transfer to an unverified recipient. Blocked by the amount-tier payment policy.",
        target_api="Stripe PaymentIntents API",
        expected_verdict="deny",
        icon="💳",
        provider_id="stripe",
        execution_mode="simulated",
    ),
    LiveScenarioSpec(
        id="pii_redaction_email",
        name="PII Redaction & Approval",
        category="Data Privacy & Compliance",
        description="Outbound email containing live SSN and phone. AgentShield redacts PII before the human approval gate.",
        target_api="SendGrid / Communications API",
        expected_verdict="require_approval",
        icon="🔒",
        provider_id="sendgrid",
        execution_mode="simulated",
    ),
    LiveScenarioSpec(
        id="hackernews_live",
        name="HackerNews Live Feed",
        category="Public REST API (Zero-Auth)",
        description="Fetches live #1 trending technology headline from HackerNews Firebase API. High-throughput rate limit test.",
        target_api="https://hacker-news.firebaseio.com/v0",
        expected_verdict="allow",
        icon="📰",
        provider_id="hackernews",
        execution_mode="live",
    ),
    LiveScenarioSpec(
        id="gemini_live_chat",
        name="Gemini 1.5 Inference",
        category="LLM Model Gateway",
        description="Real-world AI generation routed through AgentShield proxy. Calculates token counts and dollar unit cost.",
        target_api="Google Gemini 1.5 Flash API",
        expected_verdict="allow",
        icon="🤖",
        provider_id="gemini",
        execution_mode="live",
    ),
]


class ExecuteScenarioRequest(BaseModel):
    scenario: str
    custom_param: Optional[str] = None


class InvokeToolRequest(BaseModel):
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    prompt: Optional[str] = None
    scenario_hint: Optional[str] = None


class CompareModelsRequest(BaseModel):
    prompt: str
    model_a: str = "gemini-2.5-flash"
    model_b: str = "gpt-4o"


@router.get("/providers")
def get_providers():
    """Report which external providers are live, simulated, unconfigured, or offline."""
    return providers_payload()


@router.get("/scenarios", response_model=List[LiveScenarioSpec])
def list_scenarios():
    """List all available live real-world agent scenarios."""
    return SCENARIOS


def _resolve_scenario(
    scenario_id: str,
    custom_param: Optional[str],
) -> Dict[str, Any]:
    """Map a scenario id to (tool_name, tool_args, external_call_fn, prompt, model)."""
    if scenario_id == "weather_live":
        return {
            "tool_name": "weather_tool",
            "tool_args": {"city": "Tokyo", "latitude": 35.6895, "longitude": 139.6917},
            "external_call_fn": lambda: fetch_open_meteo_weather("Tokyo", 35.6895, 139.6917),
            "prompt": "What is the current live weather and temperature in Tokyo?",
            "model": "gpt-4o",
        }
    if scenario_id == "github_read":
        return {
            "tool_name": "github_tool",
            "tool_args": {"operation": "get_repository", "owner": "pallets", "repo": "flask"},
            "external_call_fn": lambda: fetch_github_repo("pallets", "flask"),
            "prompt": "Inspect the GitHub repository stats for pallets/flask.",
            "model": "gpt-4o",
        }
    if scenario_id == "github_delete_hitl":
        return {
            "tool_name": "github_tool",
            "tool_args": {
                "operation": "delete_repository",
                "owner": "acme-corp",
                "repo": "core-backend-api",
            },
            "external_call_fn": None,  # destructive: policy gate, never dispatched
            "prompt": "Permanently delete GitHub repository acme-corp/core-backend-api.",
            "model": "gpt-4o",
        }
    if scenario_id == "stripe_payment_block":
        return {
            "tool_name": "stripe_payment",
            "tool_args": {
                "amount": 1250.0,
                "recipient": "Offshore Cayman Holdings LLC",
                "currency": "USD",
                "vendor_verified": False,
            },
            "external_call_fn": lambda: create_payment_intent(
                1250.0, "Offshore Cayman Holdings LLC", "USD", vendor_verified=False
            ),
            "prompt": "Transfer $1,250.00 from company treasury to Offshore Cayman Holdings.",
            "model": "gpt-4o",
        }
    if scenario_id == "pii_redaction_email":
        return {
            "tool_name": "send_email",
            "tool_args": {
                "channel": "email",
                "recipient": "external-auditor@accounting-firm.com",
                "subject": "Executive Client Account Verification",
                "body": "Customer SSN is 456-78-9012. Personal contact email: john.doe@secure-vault.net. Call +1-555-0144.",
            },
            "external_call_fn": None,  # approval-gated; dispatched on approve
            "prompt": "Draft and send external client audit email with identification numbers.",
            "model": "gpt-4o",
        }
    if scenario_id == "hackernews_live":
        return {
            "tool_name": "news_tool",
            "tool_args": {"category": "technology", "limit": 2},
            "external_call_fn": lambda: fetch_hackernews_top(2),
            "prompt": "Fetch the top trending technology headlines from HackerNews.",
            "model": "gpt-4o",
        }
    if scenario_id == "gemini_live_chat":
        prompt_text = custom_param or (
            "Evaluate whether a SELECT query on the users table conforms to SOC-2 security baselines."
        )
        return {
            "tool_name": "llm_chat",
            "tool_args": {"prompt": prompt_text, "model": "gemini-2.5-flash"},
            "external_call_fn": lambda: execute_llm_inference(prompt_text, "gemini-2.5-flash"),
            "prompt": prompt_text,
            "model": "gemini-2.5-flash",
        }
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown scenario ID '{scenario_id}'. Available: {[s.id for s in SCENARIOS]}",
    )


def _execute(
    db: Session,
    api_key: ApiKey,
    policy_record,
    policy_config,
    tool_name: str,
    tool_args: Dict[str, Any],
    external_call_fn,
    prompt_text: str,
    model: str,
    run_id: str,
    session_id: str,
    scenario_id: Optional[str] = None,
    pre_hook=None,
) -> Dict[str, Any]:
    """Shared execution path for scenarios and free-form invokes.

    Policy is always evaluated before any network dispatch. ``pre_hook`` can veto or alter
    the call (used by the threat-intel gate) and returns (allowed, extra_payload).
    """
    now = datetime.now(timezone.utc)
    t_start = time.time()

    run_state = RunState(
        run_id=run_id,
        current_cost=0.0,
        current_tokens=0,
        current_steps=1,
        elapsed_wall_time_seconds=0.1,
    )
    decision_result = evaluate_policy(tool_name, tool_args, policy_config, run_state)

    sanitized_args, in_redactions = redact_data(tool_args)
    redaction_count = in_redactions
    api_response: Dict[str, Any] = {}
    error_msg: Optional[str] = None
    extra: Dict[str, Any] = {}

    if decision_result.decision == "allow":
        if pre_hook is not None:
            allowed, extra = pre_hook(tool_args)
            if not allowed:
                decision_result = PolicyDecisionResult(
                    decision="deny",
                    rule_id=extra.get("rule_id", "threat_intel_block"),
                    reason=extra.get("reason", "Blocked by threat intelligence gate"),
                )
        if decision_result.decision == "allow":
            if external_call_fn:
                try:
                    api_response = external_call_fn()
                except Exception as e:  # noqa: BLE001
                    error_msg = str(e)
                    api_response = {"error": error_msg, "status": "error"}
            else:
                api_response = {"status": "executed", "details": "Safe operation completed."}
    if decision_result.decision == "deny":
        api_response = {
            "status": "BLOCKED_BY_POLICY",
            "policy_rule_id": decision_result.rule_id,
            "reason": decision_result.reason,
            "security_action": "Execution immediately halted before network dispatch.",
            **extra,
        }
    elif decision_result.decision == "require_approval":
        api_response = {
            "status": "PENDING_HUMAN_APPROVAL",
            "policy_rule_id": decision_result.rule_id,
            "reason": decision_result.reason or "High-risk operation requires SOC operator sign-off.",
            "timeout_seconds": decision_result.timeout_seconds or 60,
        }

    latency_ms = int(max(10, (time.time() - t_start) * 1000.0))
    execution_mode = api_response.get("execution_mode") or (
        MODE_LIVE if decision_result.decision == "allow" else "blocked"
    )

    run_outcome = "success"
    failure_cat = None
    if decision_result.decision == "deny":
        run_outcome = "blocked"
        failure_cat = "policy_block"
    elif decision_result.decision == "require_approval":
        run_outcome = "in_progress"

    total_cost = api_response.get("cost_usd") or (0.00008 if decision_result.decision == "allow" else 0.0)
    p_tok = api_response.get("prompt_tokens") or 0
    c_tok = api_response.get("completion_tokens") or 0
    total_tokens = api_response.get("total_tokens") or (p_tok + c_tok)

    sess = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
    if not sess:
        sess = SessionModel(
            session_id=session_id,
            name="Real-World Live API Demo Session",
            session_metadata={"environment": "live_demo", "source": "interactive_testbed"},
        )
        db.add(sess)
        db.flush()

    run_record = Run(
        id=run_id,
        session_id=sess.id,
        api_key_id=api_key.id,
        task_id=f"task-{scenario_id or tool_name}",
        prompt_version="v2.1",
        model=model,
        outcome=run_outcome,
        failure_category=failure_cat,
        total_cost=total_cost,
        total_tokens=total_tokens or (120 if decision_result.decision == "allow" else 30),
        prompt_tokens=p_tok,
        completion_tokens=c_tok,
        latency_ms=latency_ms,
        step_count=1,
        error_message=error_msg,
        tags={"source": "live_real_world_api", "scenario": scenario_id or tool_name, "execution_mode": execution_mode},
        started_at=now,
        ended_at=datetime.now(timezone.utc),
    )
    db.add(run_record)

    span_id = f"span-live-{uuid.uuid4().hex[:8]}"
    tool_span = Span(
        id=span_id,
        run_id=run_id,
        sequence_number=1,
        policy_version_id=policy_record.id,
        span_type=SpanType.TOOL,
        name=tool_name,
        input_payload=sanitized_args,
        output_payload=api_response,
        started_at=now,
        ended_at=datetime.now(timezone.utc),
        latency_ms=latency_ms,
        policy_decision=decision_result.decision,
        policy_rule_id=decision_result.rule_id,
        redaction_count=redaction_count,
        token_counts={"prompt_tokens": p_tok, "completion_tokens": c_tok, "total_tokens": total_tokens},
    )
    db.add(tool_span)

    approval_id = None
    if decision_result.decision == "require_approval":
        approval_id = str(uuid.uuid4())
        call_hash = compute_call_hash(run_id, tool_name, sanitized_args)
        db.add(
            Approval(
                id=approval_id,
                run_id=run_id,
                span_id=span_id,
                tool_name=tool_name,
                tool_args=sanitized_args,
                call_hash=call_hash,
                status="pending",
                timeout_seconds=decision_result.timeout_seconds or 60,
                requested_at=now,
            )
        )

    db.commit()

    return {
        "status": "completed",
        "run_id": run_id,
        "session_id": session_id,
        "tool_name": tool_name,
        "policy_decision": decision_result.decision,
        "policy_rule_id": decision_result.rule_id,
        "reason": decision_result.reason,
        "approval_id": approval_id,
        "latency_ms": latency_ms,
        "cost_usd": total_cost,
        "redactions_applied": redaction_count,
        "provider_id": tool_name,
        "execution_mode": execution_mode,
        "api_response": api_response,
        "prompt": prompt_text,
        **({"scenario_id": scenario_id} if scenario_id else {}),
    }


@router.post("/execute")
def execute_live_scenario(
    request: ExecuteScenarioRequest,
    api_key: ApiKey = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Execute a real-world scenario live through AgentShield's security policy engine.
    Performs pre-execution check, invokes the actual external API, redacts sensitive data,
    creates HITL approvals or policy blocks, and logs traces into the telemetry database.
    """
    now = datetime.now(timezone.utc)
    run_id = f"live-{request.scenario[:12]}-{uuid.uuid4().hex[:6]}"
    session_id = "sess-live-real-world-apis"

    policy_record = get_active_policy_record(db)
    if not policy_record:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No active policy found. Default policy required for live execution.",
        )
    policy_config = parse_policy_yaml(policy_record.yaml_content)

    spec = _resolve_scenario(request.scenario, request.custom_param)
    pre_hook = _threat_intel_gate if request.scenario == "github_read" else None

    return _execute(
        db=db,
        api_key=api_key,
        policy_record=policy_record,
        policy_config=policy_config,
        tool_name=spec["tool_name"],
        tool_args=spec["tool_args"],
        external_call_fn=spec["external_call_fn"],
        prompt_text=spec["prompt"],
        model=spec["model"],
        run_id=run_id,
        session_id=session_id,
        scenario_id=request.scenario,
        pre_hook=pre_hook,
    )


# Threat-intel pre-hook: re-check the target URL/domain against live intel before dispatch.
def _threat_intel_gate(tool_args: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    url = tool_args.get("url") or tool_args.get("endpoint")
    if not url:
        return True, {}
    rep = check_url_reputation(str(url))
    if rep.get("should_block"):
        return False, {
            "threat_intel": rep,
            "rule_id": "threat_intel_block",
            "reason": f"URL {url} flagged malicious by threat intelligence",
        }
    return True, {"threat_intel": rep}


@router.post("/run-all")
def run_all_scenarios(
    api_key: ApiKey = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Run all real-world live agent scenarios sequentially for an instant, comprehensive live demo."""
    results = []
    for spec in SCENARIOS:
        req = ExecuteScenarioRequest(scenario=spec.id)
        res = execute_live_scenario(req, api_key, db)
        results.append(res)
    return {
        "status": "all_completed",
        "executed_count": len(results),
        "results": results,
    }


def _build_executor(tool_name: str, args: Dict[str, Any], prompt_text: str):
    """Map a free-form tool call onto the matching external integration.

    Returns (external_call_fn, provider_id). ``external_call_fn`` is None for tools whose
    execution is approval-gated or destructive, so the gateway never dispatches them from
    this endpoint.
    """
    provider = TOOL_PROVIDER_MAP.get(tool_name)

    if tool_name == "weather_tool":
        return (
            lambda: fetch_open_meteo_weather(
                args.get("city", "Tokyo"), float(args.get("latitude", 35.6895)), float(args.get("longitude", 139.6917))
            ),
            provider,
        )
    if tool_name == "github_tool":
        return (
            lambda: fetch_github_repo(args.get("owner", "pallets"), args.get("repo", "flask")),
            provider,
        )
    if tool_name == "news_tool":
        return (lambda: fetch_hackernews_top(int(args.get("limit", 2))), provider)
    if tool_name == "stripe_payment":
        return (
            lambda: create_payment_intent(
                float(args.get("amount", 0.0)),
                args.get("recipient", ""),
                args.get("currency", "USD"),
                vendor_verified=bool(args.get("vendor_verified", False)),
                description=args.get("description"),
            ),
            provider,
        )
    if tool_name in ("send_email", "send_slack", "send_sms"):
        channel = {"send_email": "email", "send_slack": "slack", "send_sms": "sms"}[tool_name]
        # Approval-gated in policy; dispatch only happens after a human approves.
        return (None, provider)
    if tool_name == "url_reputation":
        return (lambda: check_url_reputation(args.get("url", "")), provider)
    if tool_name == "content_moderation":
        return (lambda: moderate_content(args.get("text", "")), provider)
    if tool_name == "llm_chat":
        model = args.get("model", "gemini-2.5-flash")
        return (
            lambda: execute_llm_inference(args.get("prompt", prompt_text), model),
            "gemini" if "gemini" in model else "openai",
        )
    return (None, provider)


@router.post("/invoke")
def invoke_live_tool(
    request: InvokeToolRequest,
    api_key: ApiKey = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Run one free-form tool call through the gateway: policy check, optional external
    dispatch, redaction, HITL approval, and telemetry — the engine behind the dashboard's
    Live Test Agent."""
    tool_name = request.tool_name.strip()
    if tool_name not in TOOL_PROVIDER_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tool_name '{tool_name}'. Supported: {sorted(TOOL_PROVIDER_MAP)}",
        )

    policy_record = get_active_policy_record(db)
    if not policy_record:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No active policy found.",
        )
    policy_config = parse_policy_yaml(policy_record.yaml_content)

    prompt_text = request.prompt or f"Live Test Agent invoke of {tool_name}"
    external_call_fn, provider_id = _build_executor(tool_name, request.tool_args, prompt_text)

    # For approval-gated comm tools, dispatch through the redacting integrator.
    if tool_name in ("send_email", "send_slack", "send_sms"):
        channel = {"send_email": "email", "send_slack": "slack", "send_sms": "sms"}[tool_name]
        external_call_fn = lambda: dispatch_communication(  # noqa: E731
            channel,
            request.tool_args.get("recipient", ""),
            request.tool_args.get("subject", ""),
            request.tool_args.get("body", ""),
            request.tool_args.get("message", ""),
        )

    run_id = f"live-invoke-{uuid.uuid4().hex[:8]}"
    result = _execute(
        db=db,
        api_key=api_key,
        policy_record=policy_record,
        policy_config=policy_config,
        tool_name=tool_name,
        tool_args=request.tool_args,
        external_call_fn=external_call_fn,
        prompt_text=prompt_text,
        model=request.tool_args.get("model", "gpt-4o"),
        run_id=run_id,
        session_id="sess-live-real-world-apis",
        scenario_id=request.scenario_hint,
        # The threat-intel gate protects tools that FETCH a URL (e.g. crawl_page), not the
        # reputation lookup itself — otherwise checking a known-bad URL would be blocked
        # and the analyst could never see the verdict.
        pre_hook=_threat_intel_gate if tool_name in ("crawl_page", "http_request") else None,
    )
    result["provider_id"] = provider_id or tool_name
    result["scenario_hint"] = request.scenario_hint
    return result


@router.post("/compare-models")
def compare_models(
    request: CompareModelsRequest,
    api_key: ApiKey = Depends(verify_api_key),
):
    """Run the same prompt against two models and summarise cost / latency / token deltas.

    Each leg is still subject to the gateway's LLM-chat policy; the per-model result
    carries its own ``execution_mode`` so a live Gemini leg can be compared against a
    simulated OpenAI leg without ambiguity.
    """
    return compare_llm_models(request.prompt, [request.model_a, request.model_b])
