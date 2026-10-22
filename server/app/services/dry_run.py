from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.schemas.policy import PolicyConfig
from server.app.schemas.dry_run import DryRunResponse, SpanDiffItem
from server.app.services.policy_engine import evaluate_policy, RunState


def execute_dry_run(
    db: Session,
    candidate_policy: PolicyConfig,
    run_ids: Optional[list[str]] = None,
    limit_runs: int = 50,
) -> DryRunResponse:
    """
    Simulates evaluating candidate security policy against historical run spans.
    Reconstructs running execution state (steps, tokens, costs, tool counts)
    at each step to provide accurate budget, rate limit, and security check diffs.
    """
    # 1. Fetch target runs
    query = db.query(Run)
    if run_ids:
        query = query.filter(Run.id.in_(run_ids))
    else:
        query = query.order_by(desc(Run.started_at)).limit(limit_runs)

    runs = query.all()

    total_runs = len(runs)
    total_spans = 0
    would_allow = 0
    would_deny = 0
    would_require_approval = 0
    changed_count = 0
    diffs: list[SpanDiffItem] = []

    # 2. Iterate each run and simulate chronological tool calls
    for run in runs:
        spans = (
            db.query(Span)
            .filter(Span.run_id == run.id, Span.span_type == "tool")
            .order_by(Span.sequence_number.asc(), Span.started_at.asc())
            .all()
        )

        running_cost = 0.0
        running_tokens = 0
        running_steps = 0
        tool_counts: dict[str, int] = {}
        run_start = run.started_at

        for span in spans:
            total_spans += 1
            running_steps += 1

            # Approximate elapsed wall-clock seconds from run start
            elapsed_sec = 0.0
            if span.started_at and run_start:
                try:
                    elapsed_sec = max(0.0, (span.started_at - run_start).total_seconds())
                except Exception:
                    elapsed_sec = 0.0

            # Running state at the moment of this tool call
            state = RunState(
                run_id=run.id,
                current_cost=running_cost,
                current_tokens=running_tokens,
                current_steps=running_steps,
                elapsed_wall_time_seconds=elapsed_sec,
                tool_call_counts=dict(tool_counts),
            )

            # Extract arguments dictionary
            args_payload = span.input_payload
            if isinstance(args_payload, dict):
                tool_args = args_payload
            else:
                tool_args = {}

            # Pure-function evaluation with candidate policy
            eval_result = evaluate_policy(
                tool_name=span.name,
                tool_args=tool_args,
                policy=candidate_policy,
                run_state=state,
            )

            # Update running counts for subsequent steps in this run
            tool_counts[span.name] = tool_counts.get(span.name, 0) + 1
            if span.token_counts and isinstance(span.token_counts, dict):
                running_tokens += span.token_counts.get("total_tokens", 0)

            # Record stats
            if eval_result.decision == "allow":
                would_allow += 1
            elif eval_result.decision == "require_approval":
                would_require_approval += 1
            else:
                would_deny += 1

            # Check if decision or rule changed compared to recorded history
            orig_decision = span.policy_decision or "allow"
            has_changed = (orig_decision != eval_result.decision)

            if has_changed:
                changed_count += 1

            diffs.append(
                SpanDiffItem(
                    span_id=span.id,
                    run_id=run.id,
                    tool_name=span.name,
                    tool_args=tool_args,
                    original_decision=span.policy_decision,
                    original_rule_id=span.policy_rule_id,
                    candidate_decision=eval_result.decision,
                    candidate_rule_id=eval_result.rule_id,
                    candidate_reason=eval_result.reason,
                    has_changed=has_changed,
                )
            )

    return DryRunResponse(
        total_runs_evaluated=total_runs,
        total_spans_evaluated=total_spans,
        would_allow=would_allow,
        would_deny=would_deny,
        would_require_approval=would_require_approval,
        changed_count=changed_count,
        diffs=diffs,
    )
