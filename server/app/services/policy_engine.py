import re
import yaml
from typing import Optional, Any
from dataclasses import dataclass, field
from server.app.schemas.policy import PolicyConfig, PolicyRule
from server.app.services.security_checks import check_sql_safety, check_path_safety, check_domain_safety


@dataclass
class RunState:
    run_id: str
    current_cost: float = 0.0
    current_tokens: int = 0
    current_steps: int = 0
    elapsed_wall_time_seconds: float = 0.0
    tool_call_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class PolicyDecisionResult:
    decision: str  # allow | deny | require_approval
    rule_id: Optional[str] = None
    reason: Optional[str] = None
    timeout_seconds: Optional[int] = None


def parse_policy_yaml(yaml_str: str) -> PolicyConfig:
    """
    Parses and strictly validates YAML policy configuration.
    Raises ValueError on syntax errors, duplicate rule IDs, or invalid schemas.
    Never falls back to allow-all.
    """
    if not yaml_str or not yaml_str.strip():
        raise ValueError("Policy YAML cannot be empty")

    try:
        data = yaml.safe_load(yaml_str)
    except Exception as e:
        raise ValueError(f"Invalid YAML syntax: {str(e)}")

    if not isinstance(data, dict):
        raise ValueError("Policy YAML root must be a mapping/dictionary")

    # Validate schema via Pydantic
    try:
        policy = PolicyConfig.model_validate(data)
    except Exception as e:
        raise ValueError(f"Policy schema validation failed: {str(e)}")

    # Check for duplicate rule IDs
    rule_ids = set()
    for rule in policy.rules:
        if rule.id in rule_ids:
            raise ValueError(f"Duplicate rule ID found in policy: '{rule.id}'")
        rule_ids.add(rule.id)

    # Check for unreachable rules after an unconstrained wildcard rule
    wildcard_seen = False
    for rule in policy.rules:
        if wildcard_seen:
            raise ValueError(f"Unreachable rule '{rule.id}' positioned after unconditional wildcard rule")
        if rule.tool == "*" and not rule.constraints and not rule.sql_check and not rule.path_allowlist and not rule.domain_allowlist:
            wildcard_seen = True

    return policy


def _get_named_arg(tool_args: dict[str, Any], arg_name: str) -> Optional[str]:
    """Retrieve named argument from tool args without guessing or falling back to other keys."""
    if arg_name in tool_args and tool_args[arg_name] is not None:
        return str(tool_args[arg_name])
    if "kwargs" in tool_args and isinstance(tool_args["kwargs"], dict):
        if arg_name in tool_args["kwargs"] and tool_args["kwargs"][arg_name] is not None:
            return str(tool_args["kwargs"][arg_name])
    return None


# Constraint operators that compare the argument as a number rather than a string.
NUMERIC_CONSTRAINT_OPS = ("gt", "gte", "lt", "lte")


def coerce_numeric(value: Any) -> Optional[float]:
    """Best-effort conversion of a tool argument to a float, or None if it is not numeric.

    Booleans are rejected: in Python `True == 1`, so a flag like `dry_run: true` must never
    satisfy `amount: {gt: 500}`. Currency symbols and thousands separators are tolerated so
    a policy written as `amount: {gte: 100}` still matches a "$1,250" argument.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("_", "")
        text = re.sub(r"^[\$€£¥]", "", text).strip()
        try:
            return float(text)
        except ValueError:
            return None
    return None


def evaluate_policy(
    tool_name: str,
    tool_args: dict[str, Any],
    policy: PolicyConfig,
    run_state: Optional[RunState] = None,
) -> PolicyDecisionResult:
    """
    Pure function evaluating policy rules against a tool call and run state.
    Returns PolicyDecisionResult with verdict ('allow', 'deny', 'require_approval'),
    matching rule_id, reason, and timeout.
    """
    # 1. Evaluate Budget and Step Limits
    if run_state and policy.limits:
        limits = policy.limits
        if limits.max_cost_per_run is not None and run_state.current_cost > limits.max_cost_per_run:
            return PolicyDecisionResult(
                decision="deny",
                rule_id="limit:max_cost_per_run",
                reason=f"Cost limit exceeded: ${run_state.current_cost:.4f} > ${limits.max_cost_per_run:.4f}",
            )
        if limits.max_tokens_per_run is not None and run_state.current_tokens > limits.max_tokens_per_run:
            return PolicyDecisionResult(
                decision="deny",
                rule_id="limit:max_tokens_per_run",
                reason=f"Token limit exceeded: {run_state.current_tokens} > {limits.max_tokens_per_run}",
            )
        if limits.max_steps_per_run is not None and run_state.current_steps >= limits.max_steps_per_run:
            return PolicyDecisionResult(
                decision="deny",
                rule_id="limit:max_steps_per_run",
                reason=f"Step limit reached: {run_state.current_steps} >= {limits.max_steps_per_run}",
            )
        if limits.max_wall_time_seconds is not None and run_state.elapsed_wall_time_seconds > limits.max_wall_time_seconds:
            return PolicyDecisionResult(
                decision="deny",
                rule_id="limit:max_wall_time_seconds",
                reason=f"Wall-clock time limit exceeded: {run_state.elapsed_wall_time_seconds:.1f}s > {limits.max_wall_time_seconds:.1f}s",
            )

    # 2. Iterate and evaluate policy rules in order
    for rule in policy.rules:
        # Match tool name or wildcard
        if rule.tool != "*" and rule.tool != tool_name:
            continue

        # A. Rate limit check
        if rule.rate_limit and run_state:
            prior_calls = run_state.tool_call_counts.get(tool_name, 0)
            if (prior_calls + 1) > rule.rate_limit.max_calls_per_run:
                return PolicyDecisionResult(
                    decision="deny",
                    rule_id=rule.id,
                    reason=f"Rate limit exceeded for tool '{tool_name}': {prior_calls + 1} > {rule.rate_limit.max_calls_per_run}",
                )

        # B. SQL Safety Check
        if rule.sql_check:
            target_arg = rule.sql_check.arg or "query"
            sql_query = _get_named_arg(tool_args, target_arg)
            if sql_query is None:
                return PolicyDecisionResult(
                    decision="deny",
                    rule_id=rule.id,
                    reason=f"SQL safety check bound to argument '{target_arg}', but argument was missing from tool call",
                )
            is_safe, sql_err = check_sql_safety(
                query=sql_query,
                allowed_operations=rule.sql_check.allowed_operations,
                blocked_operations=rule.sql_check.blocked_operations,
                require_where_clause_on=rule.sql_check.require_where_clause_on,
            )
            if not is_safe:
                return PolicyDecisionResult(
                    decision="deny",
                    rule_id=rule.id,
                    reason=f"SQL safety check failed: {sql_err}",
                )

        # C. Path Allowlist / Denylist Check
        if rule.path_allowlist or rule.path_denylist:
            target_arg = rule.path_arg or "path"
            path_val = _get_named_arg(tool_args, target_arg)
            if path_val is None:
                return PolicyDecisionResult(
                    decision="deny",
                    rule_id=rule.id,
                    reason=f"Path confinement check bound to argument '{target_arg}', but argument was missing from tool call",
                )
            is_safe, path_err = check_path_safety(
                target_path=path_val,
                allowlist=rule.path_allowlist,
                denylist=rule.path_denylist,
            )
            if not is_safe:
                return PolicyDecisionResult(
                    decision="deny",
                    rule_id=rule.id,
                    reason=f"Path confinement check failed: {path_err}",
                )

        # D. Domain Allowlist Check
        if rule.domain_allowlist:
            target_arg = rule.domain_arg or "url"
            domain_val = _get_named_arg(tool_args, target_arg)
            if domain_val is None:
                return PolicyDecisionResult(
                    decision="deny",
                    rule_id=rule.id,
                    reason=f"Domain allowlist check bound to argument '{target_arg}', but argument was missing from tool call",
                )
            is_safe, domain_err = check_domain_safety(
                url_or_domain=domain_val,
                allowlist=rule.domain_allowlist,
            )
            if not is_safe:
                return PolicyDecisionResult(
                    decision="deny",
                    rule_id=rule.id,
                    reason=f"Domain allowlist check failed: {domain_err}",
                )

        # E. Argument Constraints (supports regex, contains, equals, numeric comparisons
        #    and membership tests under constraints or parameters)
        rule_constraints = rule.constraints or getattr(rule, "parameters", None)
        if rule_constraints:
            constraint_failed = False
            for param_name, constraint_spec in rule_constraints.items():
                raw_arg = tool_args.get(param_name)
                arg_val = str(raw_arg if raw_arg is not None else "")
                if isinstance(raw_arg, bool):
                    # YAML parses `equals: true` to a bool while str(True) is "True"; normalise
                    # so boolean arguments can satisfy boolean constraints at all.
                    arg_val = "true" if raw_arg else "false"
                if isinstance(constraint_spec, dict):
                    if "regex" in constraint_spec:
                        pattern = constraint_spec["regex"]
                        if not re.search(pattern, arg_val):
                            constraint_failed = True
                            break
                    if "contains" in constraint_spec:
                        substr = constraint_spec["contains"]
                        if substr.lower() not in arg_val.lower():
                            constraint_failed = True
                            break
                    if "equals" in constraint_spec:
                        if str(constraint_spec["equals"]) != arg_val:
                            constraint_failed = True
                            break

                    # Numeric comparisons are fail-closed: a missing or non-numeric argument
                    # never satisfies the rule, so evaluation falls through to later rules
                    # (or the deny default) instead of accidentally matching.
                    numeric_ops = [op for op in NUMERIC_CONSTRAINT_OPS if op in constraint_spec]
                    if numeric_ops:
                        actual = coerce_numeric(raw_arg)
                        if actual is None:
                            constraint_failed = True
                            break
                        for op in numeric_ops:
                            bound = coerce_numeric(constraint_spec[op])
                            if bound is None:
                                raise ValueError(
                                    f"Rule '{rule.id}': constraint '{op}' for argument "
                                    f"'{param_name}' must be numeric, got {constraint_spec[op]!r}"
                                )
                            passed = (
                                actual > bound if op == "gt"
                                else actual >= bound if op == "gte"
                                else actual < bound if op == "lt"
                                else actual <= bound
                            )
                            if not passed:
                                constraint_failed = True
                                break
                        if constraint_failed:
                            break

                    if "in" in constraint_spec:
                        options = constraint_spec["in"]
                        if not isinstance(options, (list, tuple)) or str(raw_arg) not in {str(o) for o in options}:
                            constraint_failed = True
                            break
                    if "not_in" in constraint_spec:
                        options = constraint_spec["not_in"]
                        if isinstance(options, (list, tuple)) and str(raw_arg) in {str(o) for o in options}:
                            constraint_failed = True
                            break
                elif isinstance(constraint_spec, str):
                    if constraint_spec.lower() not in arg_val.lower():
                        constraint_failed = True
                        break
            if constraint_failed:
                # Rule does not match because constraint failed -> evaluate next rule
                continue

        # Rule matched and passed all safety checks!
        return PolicyDecisionResult(
            decision=rule.action,
            rule_id=rule.id,
            reason=f"Matched policy rule '{rule.id}'",
            timeout_seconds=rule.timeout_seconds,
        )

    # 3. Default action when no rules match
    return PolicyDecisionResult(
        decision=policy.default_action,
        rule_id="default_policy",
        reason=f"No matching rule; applied default action '{policy.default_action}'",
    )
