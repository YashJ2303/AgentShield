import functools
import inspect
import uuid
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional, Callable, Any
from .context import (
    get_current_run,
    get_current_parent_span_id,
    push_span_id,
    pop_span_id,
)
from .redaction import redact_data
from .otlp_exporter import export_otel_span
from .exceptions import PolicyViolationError, GatewayUnreachableError
from .client import get_active_client




def _extract_token_counts(output: Any, input_payload: Any) -> dict[str, int]:
    """Attempt to extract token usage from model response or estimate conservatively."""
    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if hasattr(output, "usage") and output.usage:
        u = output.usage
        tokens["prompt_tokens"] = getattr(u, "prompt_tokens", 0) or 0
        tokens["completion_tokens"] = getattr(u, "completion_tokens", 0) or 0
        tokens["total_tokens"] = getattr(u, "total_tokens", 0) or (tokens["prompt_tokens"] + tokens["completion_tokens"])
        return tokens

    if isinstance(output, dict) and "usage" in output:
        u = output["usage"]
        if isinstance(u, dict):
            tokens["prompt_tokens"] = u.get("prompt_tokens", 0) or 0
            tokens["completion_tokens"] = u.get("completion_tokens", 0) or 0
            tokens["total_tokens"] = u.get("total_tokens", 0) or (tokens["prompt_tokens"] + tokens["completion_tokens"])
            return tokens

    in_str = str(input_payload)
    out_str = str(output)
    p_tok = max(1, len(in_str) // 4)
    c_tok = max(1, len(out_str) // 4)
    return {
        "prompt_tokens": p_tok,
        "completion_tokens": c_tok,
        "total_tokens": p_tok + c_tok,
    }


def trace_model_call(name: Optional[str] = None):
    """
    Decorator for AI model calls.
    Captures complete prompt/messages input, output, tokens, latency, and redaction counts.
    """
    def decorator(fn: Callable):
        span_name = name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            run_ctx = get_current_run()
            span_id = str(uuid.uuid4())
            parent_id = get_current_parent_span_id()
            started_at = datetime.now(timezone.utc)
            start_mono = time.monotonic()
            seq_num = run_ctx.allocate_sequence_number() if run_ctx else 1

            raw_input = {"args": args, "kwargs": kwargs}
            redacted_input, in_redaction_count = redact_data(raw_input)

            push_span_id(span_id)
            error_msg = None
            output_payload = None
            out_redaction_count = 0

            try:
                result = fn(*args, **kwargs)
                output_payload, out_redaction_count = redact_data(result)
                return result
            except Exception as e:
                error_msg = str(e)
                output_payload = {"error": error_msg}
                raise
            finally:
                pop_span_id()
                end_mono = time.monotonic()
                ended_at = datetime.now(timezone.utc)
                latency_ms = max(1, int((end_mono - start_mono) * 1000))
                token_counts = _extract_token_counts(output_payload, redacted_input)

                span_dict = {
                    "id": span_id,
                    "run_id": run_ctx.run_id if run_ctx else str(uuid.uuid4()),
                    "sequence_number": seq_num,
                    "parent_span_id": parent_id,
                    "span_type": "model",
                    "name": span_name,
                    "input_payload": redacted_input,
                    "output_payload": output_payload,
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                    "latency_ms": latency_ms,
                    "token_counts": token_counts,
                    "error": error_msg,
                    "redaction_count": in_redaction_count + out_redaction_count,
                    "policy_decision": "bypassed",
                }

                if run_ctx:
                    run_ctx.spans.append(span_dict)
                    run_ctx.running_prompt_tokens += token_counts["prompt_tokens"]
                    run_ctx.running_completion_tokens += token_counts["completion_tokens"]
                    run_ctx.running_tokens += token_counts["total_tokens"]

                export_otel_span(
                    name=span_name,
                    span_type="model",
                    run_id=span_dict["run_id"],
                    started_at=started_at,
                    ended_at=ended_at,
                    attributes={
                        "gen_ai.request.model": span_name,
                        "gen_ai.usage.prompt_tokens": token_counts["prompt_tokens"],
                        "gen_ai.usage.completion_tokens": token_counts["completion_tokens"],
                    },
                    error=error_msg,
                )

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            run_ctx = get_current_run()
            span_id = str(uuid.uuid4())
            parent_id = get_current_parent_span_id()
            started_at = datetime.now(timezone.utc)
            start_mono = time.monotonic()
            seq_num = run_ctx.allocate_sequence_number() if run_ctx else 1

            raw_input = {"args": args, "kwargs": kwargs}
            redacted_input, in_redaction_count = redact_data(raw_input)

            push_span_id(span_id)
            error_msg = None
            output_payload = None
            out_redaction_count = 0

            try:
                result = await fn(*args, **kwargs)
                output_payload, out_redaction_count = redact_data(result)
                return result
            except Exception as e:
                error_msg = str(e)
                output_payload = {"error": error_msg}
                raise
            finally:
                pop_span_id()
                end_mono = time.monotonic()
                ended_at = datetime.now(timezone.utc)
                latency_ms = max(1, int((end_mono - start_mono) * 1000))
                token_counts = _extract_token_counts(output_payload, redacted_input)

                span_dict = {
                    "id": span_id,
                    "run_id": run_ctx.run_id if run_ctx else str(uuid.uuid4()),
                    "sequence_number": seq_num,
                    "parent_span_id": parent_id,
                    "span_type": "model",
                    "name": span_name,
                    "input_payload": redacted_input,
                    "output_payload": output_payload,
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                    "latency_ms": latency_ms,
                    "token_counts": token_counts,
                    "error": error_msg,
                    "redaction_count": in_redaction_count + out_redaction_count,
                    "policy_decision": "bypassed",
                }

                if run_ctx:
                    run_ctx.spans.append(span_dict)
                    run_ctx.running_prompt_tokens += token_counts["prompt_tokens"]
                    run_ctx.running_completion_tokens += token_counts["completion_tokens"]
                    run_ctx.running_tokens += token_counts["total_tokens"]

                export_otel_span(
                    name=span_name,
                    span_type="model",
                    run_id=span_dict["run_id"],
                    started_at=started_at,
                    ended_at=ended_at,
                    attributes={
                        "gen_ai.request.model": span_name,
                        "gen_ai.usage.prompt_tokens": token_counts["prompt_tokens"],
                        "gen_ai.usage.completion_tokens": token_counts["completion_tokens"],
                    },
                    error=error_msg,
                )

        return async_wrapper if inspect.iscoroutinefunction(fn) else sync_wrapper

    return decorator


def _bind_tool_arguments(fn: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    """Inspect tool signature and bind positional and keyword arguments to parameter names."""
    try:
        sig = inspect.signature(fn)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except Exception:
        res = dict(kwargs)
        if args:
            res["args"] = args
        return res


def trace_tool_call(name: Optional[str] = None):
    """
    Decorator for agent tools.
    Enforces security policy via POST /gateway/check before execution.
    Fails closed if the gateway is unreachable (configurable).
    Captures tool input arguments, execution result/error, latency, and redactions.
    """
    def decorator(fn: Callable):
        tool_name = name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            run_ctx = get_current_run()
            span_id = str(uuid.uuid4())
            # Tool spans belong directly to the run, not to any enclosing model span
            parent_id = None
            started_at = datetime.now(timezone.utc)
            start_mono = time.monotonic()
            seq_num = run_ctx.allocate_sequence_number() if run_ctx else 1

            tool_args_dict = _bind_tool_arguments(fn, args, kwargs)
            raw_input = dict(tool_args_dict)
            redacted_input, in_redaction_count = redact_data(raw_input)

            if run_ctx:
                run_ctx.running_steps += 1

            client = get_active_client()

            policy_decision = "allow"
            policy_rule_id = None
            policy_version_id = None

            # Execute Gateway Pre-Call Check
            if client and getattr(client.config, "check_policy", True):
                run_id_val = run_ctx.run_id if run_ctx else str(uuid.uuid4())
                cost = run_ctx.running_cost if run_ctx else 0.0
                tokens = run_ctx.running_tokens if run_ctx else 0
                steps = run_ctx.running_steps if run_ctx else 0
                elapsed = run_ctx.elapsed_seconds if run_ctx else 0.0

                try:
                    check_res = client.check_tool(
                        run_id=run_id_val,
                        tool_name=tool_name,
                        tool_args=tool_args_dict,
                        current_cost=cost,
                        current_tokens=tokens,
                        current_steps=steps,
                        elapsed_wall_time=elapsed,
                    )
                    decision = check_res.get("decision", "allow")
                    policy_rule_id = check_res.get("rule_id")
                    policy_version_id = check_res.get("policy_version_id")

                    if decision == "deny":
                        policy_decision = "deny"
                        reason = check_res.get("reason", "Blocked by security policy")
                        end_mono = time.monotonic()
                        ended_at = datetime.now(timezone.utc)
                        latency_ms = max(1, int((end_mono - start_mono) * 1000))

                        span_dict = {
                            "id": span_id,
                            "run_id": run_id_val,
                            "sequence_number": seq_num,
                            "parent_span_id": None,
                            "policy_version_id": policy_version_id,
                            "span_type": "tool",
                            "name": tool_name,
                            "input_payload": redacted_input,
                            "output_payload": {"error": f"Policy violation: {reason}"},
                            "started_at": started_at.isoformat(),
                            "ended_at": ended_at.isoformat(),
                            "latency_ms": latency_ms,
                            "token_counts": {},
                            "error": f"Policy violation: {reason}",
                            "redaction_count": in_redaction_count,
                            "policy_decision": "deny",
                            "policy_rule_id": policy_rule_id,
                        }
                        if run_ctx:
                            run_ctx.spans.append(span_dict)

                        raise PolicyViolationError(
                            f"Tool '{tool_name}' blocked by policy rule '{policy_rule_id}': {reason}",
                            rule_id=policy_rule_id,
                            reason=reason,
                        )

                    elif decision in ("pending", "require_approval"):
                        approval_id = check_res.get("approval_id")
                        timeout_sec = check_res.get("timeout_seconds", 60)

                        poll_res = client.poll_approval(
                            approval_id=approval_id,
                            run_id=run_id_val,
                            tool_name=tool_name,
                            tool_args=tool_args_dict,
                            timeout_seconds=timeout_sec,
                            poll_interval=0.2,
                        )
                        outcome = poll_res.get("decision")
                        if outcome == "approved":
                            policy_decision = "approved"
                            # Proceeds to tool execution
                        else:
                            policy_decision = outcome or "deny"
                            reason = poll_res.get("reason", f"Approval {policy_decision}")
                            end_mono = time.monotonic()
                            ended_at = datetime.now(timezone.utc)
                            latency_ms = max(1, int((end_mono - start_mono) * 1000))

                            span_dict = {
                                "id": span_id,
                                "run_id": run_id_val,
                                "sequence_number": seq_num,
                                "parent_span_id": None,
                                "policy_version_id": policy_version_id,
                                "span_type": "tool",
                                "name": tool_name,
                                "input_payload": redacted_input,
                                "output_payload": {"error": f"Approval {policy_decision}: {reason}"},
                                "started_at": started_at.isoformat(),
                                "ended_at": ended_at.isoformat(),
                                "latency_ms": latency_ms,
                                "token_counts": {},
                                "error": f"Approval {policy_decision}: {reason}",
                                "redaction_count": in_redaction_count,
                                "policy_decision": policy_decision,
                                "policy_rule_id": policy_rule_id,
                            }
                            if run_ctx:
                                run_ctx.spans.append(span_dict)

                            raise PolicyViolationError(
                                f"Tool '{tool_name}' {policy_decision} (rule '{policy_rule_id}'): {reason}",
                                rule_id=policy_rule_id,
                                reason=reason,
                            )

                except GatewayUnreachableError as e:
                    if getattr(client.config, "fail_mode", "fail_closed") == "fail_closed":
                        end_mono = time.monotonic()
                        ended_at = datetime.now(timezone.utc)
                        latency_ms = max(1, int((end_mono - start_mono) * 1000))
                        span_dict = {
                            "id": span_id,
                            "run_id": run_id_val,
                            "sequence_number": seq_num,
                            "parent_span_id": None,
                            "span_type": "tool",
                            "name": tool_name,
                            "input_payload": redacted_input,
                            "output_payload": {"error": str(e)},
                            "started_at": started_at.isoformat(),
                            "ended_at": ended_at.isoformat(),
                            "latency_ms": latency_ms,
                            "token_counts": {},
                            "error": str(e),
                            "redaction_count": in_redaction_count,
                            "policy_decision": "deny",
                            "policy_rule_id": "gateway_unreachable",
                        }
                        if run_ctx:
                            run_ctx.spans.append(span_dict)
                        raise

            injection_flag = False
            injection_details = None

            error_msg = None
            output_payload = None
            out_redaction_count = 0

            try:
                result = fn(*args, **kwargs)
                # Automatic prompt injection screening on tool output before returning to model
                if client and getattr(client.config, "check_policy", True):
                    run_id_val = run_ctx.run_id if run_ctx else str(uuid.uuid4())
                    try:
                        screen_res = client.screen_output(
                            run_id=run_id_val,
                            tool_name=tool_name,
                            tool_output=result,
                            span_id=span_id,
                        )
                        if screen_res.get("injection_flag"):
                            injection_flag = True
                            injection_details = screen_res
                            action_taken = screen_res.get("action_taken", "block")
                            if action_taken == "block":
                                policy_decision = "deny"
                                policy_rule_id = "prompt_injection_detected"
                                refusal_msg = screen_res.get("sanitized_output") or "Security violation: Tool output blocked by AgentShield prompt injection filter."
                                error_msg = refusal_msg
                                output_payload, out_redaction_count = redact_data({"error": refusal_msg})
                                raise PolicyViolationError(refusal_msg, rule_id=policy_rule_id, reason="Prompt injection detected in tool output")
                            elif action_taken == "sanitize":
                                result = screen_res.get("sanitized_output")
                    except GatewayUnreachableError:
                        if getattr(client.config, "fail_mode", "fail_closed") == "fail_closed":
                            policy_decision = "deny"
                            policy_rule_id = "screening_unreachable"
                            error_msg = "Gateway unreachable during prompt injection screening (fail-closed)"
                            output_payload, out_redaction_count = redact_data({"error": error_msg})
                            raise
                output_payload, out_redaction_count = redact_data(result)
                return result
            except Exception as e:
                if not error_msg:
                    error_msg = str(e)
                if not output_payload:
                    output_payload = {"error": error_msg}
                raise
            finally:
                end_mono = time.monotonic()
                ended_at = datetime.now(timezone.utc)
                latency_ms = max(1, int((end_mono - start_mono) * 1000))

                span_dict = {
                    "id": span_id,
                    "run_id": run_ctx.run_id if run_ctx else str(uuid.uuid4()),
                    "sequence_number": seq_num,
                    "parent_span_id": None,
                    "policy_version_id": policy_version_id,
                    "span_type": "tool",
                    "name": tool_name,
                    "input_payload": redacted_input,
                    "output_payload": output_payload,
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                    "latency_ms": latency_ms,
                    "token_counts": {},
                    "error": error_msg,
                    "redaction_count": in_redaction_count + out_redaction_count,
                    "policy_decision": policy_decision,
                    "policy_rule_id": policy_rule_id,
                    "injection_flag": injection_flag,
                    "injection_details": injection_details,
                }

                if run_ctx:
                    run_ctx.spans.append(span_dict)

                export_otel_span(
                    name=tool_name,
                    span_type="tool",
                    run_id=span_dict["run_id"],
                    started_at=started_at,
                    ended_at=ended_at,
                    attributes={"tool.name": tool_name},
                    error=error_msg,
                )

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            run_ctx = get_current_run()
            span_id = str(uuid.uuid4())
            # Tool spans belong directly to the run, not to any enclosing model span
            parent_id = None
            started_at = datetime.now(timezone.utc)
            start_mono = time.monotonic()
            seq_num = run_ctx.allocate_sequence_number() if run_ctx else 1

            tool_args_dict = _bind_tool_arguments(fn, args, kwargs)
            raw_input = dict(tool_args_dict)
            redacted_input, in_redaction_count = redact_data(raw_input)

            if run_ctx:
                run_ctx.running_steps += 1

            client = get_active_client()

            policy_decision = "allow"
            policy_rule_id = None
            policy_version_id = None

            if client and getattr(client.config, "check_policy", True):
                run_id_val = run_ctx.run_id if run_ctx else str(uuid.uuid4())
                cost = run_ctx.running_cost if run_ctx else 0.0
                tokens = run_ctx.running_tokens if run_ctx else 0
                steps = run_ctx.running_steps if run_ctx else 0
                elapsed = run_ctx.elapsed_seconds if run_ctx else 0.0

                try:
                    check_res = client.check_tool(
                        run_id=run_id_val,
                        tool_name=tool_name,
                        tool_args=tool_args_dict,
                        current_cost=cost,
                        current_tokens=tokens,
                        current_steps=steps,
                        elapsed_wall_time=elapsed,
                    )
                    decision = check_res.get("decision", "allow")
                    policy_rule_id = check_res.get("rule_id")
                    policy_version_id = check_res.get("policy_version_id")

                    if decision == "deny":
                        policy_decision = "deny"
                        reason = check_res.get("reason", "Blocked by security policy")
                        end_mono = time.monotonic()
                        ended_at = datetime.now(timezone.utc)
                        latency_ms = max(1, int((end_mono - start_mono) * 1000))

                        span_dict = {
                            "id": span_id,
                            "run_id": run_id_val,
                            "sequence_number": seq_num,
                            "parent_span_id": None,
                            "policy_version_id": policy_version_id,
                            "span_type": "tool",
                            "name": tool_name,
                            "input_payload": redacted_input,
                            "output_payload": {"error": f"Policy violation: {reason}"},
                            "started_at": started_at.isoformat(),
                            "ended_at": ended_at.isoformat(),
                            "latency_ms": latency_ms,
                            "token_counts": {},
                            "error": f"Policy violation: {reason}",
                            "redaction_count": in_redaction_count,
                            "policy_decision": "deny",
                            "policy_rule_id": policy_rule_id,
                        }
                        if run_ctx:
                            run_ctx.spans.append(span_dict)

                        raise PolicyViolationError(
                            f"Tool '{tool_name}' blocked by policy rule '{policy_rule_id}': {reason}",
                            rule_id=policy_rule_id,
                            reason=reason,
                        )

                    elif decision in ("pending", "require_approval"):
                        approval_id = check_res.get("approval_id")
                        timeout_sec = check_res.get("timeout_seconds", 60)

                        poll_res = client.poll_approval(
                            approval_id=approval_id,
                            run_id=run_id_val,
                            tool_name=tool_name,
                            tool_args=tool_args_dict,
                            timeout_seconds=timeout_sec,
                            poll_interval=0.2,
                        )
                        outcome = poll_res.get("decision")
                        if outcome == "approved":
                            policy_decision = "approved"
                            # Proceeds to tool execution
                        else:
                            policy_decision = outcome or "deny"
                            reason = poll_res.get("reason", f"Approval {policy_decision}")
                            end_mono = time.monotonic()
                            ended_at = datetime.now(timezone.utc)
                            latency_ms = max(1, int((end_mono - start_mono) * 1000))

                            span_dict = {
                                "id": span_id,
                                "run_id": run_id_val,
                                "sequence_number": seq_num,
                                "parent_span_id": None,
                                "policy_version_id": policy_version_id,
                                "span_type": "tool",
                                "name": tool_name,
                                "input_payload": redacted_input,
                                "output_payload": {"error": f"Approval {policy_decision}: {reason}"},
                                "started_at": started_at.isoformat(),
                                "ended_at": ended_at.isoformat(),
                                "latency_ms": latency_ms,
                                "token_counts": {},
                                "error": f"Approval {policy_decision}: {reason}",
                                "redaction_count": in_redaction_count,
                                "policy_decision": policy_decision,
                                "policy_rule_id": policy_rule_id,
                            }
                            if run_ctx:
                                run_ctx.spans.append(span_dict)

                            raise PolicyViolationError(
                                f"Tool '{tool_name}' {policy_decision} (rule '{policy_rule_id}'): {reason}",
                                rule_id=policy_rule_id,
                                reason=reason,
                            )

                except GatewayUnreachableError as e:
                    if getattr(client.config, "fail_mode", "fail_closed") == "fail_closed":
                        end_mono = time.monotonic()
                        ended_at = datetime.now(timezone.utc)
                        latency_ms = max(1, int((end_mono - start_mono) * 1000))
                        span_dict = {
                            "id": span_id,
                            "run_id": run_id_val,
                            "sequence_number": seq_num,
                            "parent_span_id": None,
                            "span_type": "tool",
                            "name": tool_name,
                            "input_payload": redacted_input,
                            "output_payload": {"error": str(e)},
                            "started_at": started_at.isoformat(),
                            "ended_at": ended_at.isoformat(),
                            "latency_ms": latency_ms,
                            "token_counts": {},
                            "error": str(e),
                            "redaction_count": in_redaction_count,
                            "policy_decision": "deny",
                            "policy_rule_id": "gateway_unreachable",
                        }
                        if run_ctx:
                            run_ctx.spans.append(span_dict)
                        raise

            injection_flag = False
            injection_details = None

            error_msg = None
            output_payload = None
            out_redaction_count = 0

            try:
                result = await fn(*args, **kwargs)
                # Automatic prompt injection screening on tool output before returning to model
                if client and getattr(client.config, "check_policy", True):
                    run_id_val = run_ctx.run_id if run_ctx else str(uuid.uuid4())
                    try:
                        screen_res = client.screen_output(
                            run_id=run_id_val,
                            tool_name=tool_name,
                            tool_output=result,
                            span_id=span_id,
                        )
                        if screen_res.get("injection_flag"):
                            injection_flag = True
                            injection_details = screen_res
                            action_taken = screen_res.get("action_taken", "block")
                            if action_taken == "block":
                                policy_decision = "deny"
                                policy_rule_id = "prompt_injection_detected"
                                refusal_msg = screen_res.get("sanitized_output") or "Security violation: Tool output blocked by AgentShield prompt injection filter."
                                error_msg = refusal_msg
                                output_payload, out_redaction_count = redact_data({"error": refusal_msg})
                                raise PolicyViolationError(refusal_msg, rule_id=policy_rule_id, reason="Prompt injection detected in tool output")
                            elif action_taken == "sanitize":
                                result = screen_res.get("sanitized_output")
                    except GatewayUnreachableError:
                        if getattr(client.config, "fail_mode", "fail_closed") == "fail_closed":
                            policy_decision = "deny"
                            policy_rule_id = "screening_unreachable"
                            error_msg = "Gateway unreachable during prompt injection screening (fail-closed)"
                            output_payload, out_redaction_count = redact_data({"error": error_msg})
                            raise
                output_payload, out_redaction_count = redact_data(result)
                return result
            except Exception as e:
                if not error_msg:
                    error_msg = str(e)
                if not output_payload:
                    output_payload = {"error": error_msg}
                raise
            finally:
                end_mono = time.monotonic()
                ended_at = datetime.now(timezone.utc)
                latency_ms = max(1, int((end_mono - start_mono) * 1000))

                span_dict = {
                    "id": span_id,
                    "run_id": run_ctx.run_id if run_ctx else str(uuid.uuid4()),
                    "sequence_number": seq_num,
                    "parent_span_id": None,
                    "policy_version_id": policy_version_id,
                    "span_type": "tool",
                    "name": tool_name,
                    "input_payload": redacted_input,
                    "output_payload": output_payload,
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                    "latency_ms": latency_ms,
                    "token_counts": {},
                    "error": error_msg,
                    "redaction_count": in_redaction_count + out_redaction_count,
                    "policy_decision": policy_decision,
                    "policy_rule_id": policy_rule_id,
                    "injection_flag": injection_flag,
                    "injection_details": injection_details,
                }

                if run_ctx:
                    run_ctx.spans.append(span_dict)

                export_otel_span(
                    name=tool_name,
                    span_type="tool",
                    run_id=span_dict["run_id"],
                    started_at=started_at,
                    ended_at=ended_at,
                    attributes={"tool.name": tool_name},
                    error=error_msg,
                )

        return async_wrapper if inspect.iscoroutinefunction(fn) else sync_wrapper

    return decorator
