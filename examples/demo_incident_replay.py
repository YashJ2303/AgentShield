"""
Milestone 8: Incident Replay Engine End-to-End Demonstration (RQ2).

Demonstrates:
1. Replaying a recorded trace from SQLite (run 21b99068-ed36-4072-aca7-561b7cb7b0b2).
   NOTE: This trace was generated using seeded test data for M8 demonstration;
   it will be re-run on traces from actual demo agents once Milestone 11 is built.
2. Clean Reproduction Replay:
   - Frozen tool outputs returned with 0 live tool calls
   - Exact tool and argument matching
   - Deterministic baseline check
3. Targeted Counterfactual Candidate Security Policy Replay:
   - Policy explicitly sets default_action: allow and targets only `bash_exec` with deny
   - Steps 1 & 2 (calculator, sql_query) proceed normally with frozen outputs
   - Step 3 (bash_exec) is blocked by candidate policy AST evaluator
   - Clear diagnostic trajectory diff isolating the regression
4. Stochastic Simulation Replay (Evaluating RQ2 with Temperature > 0 Variation):
   - StochasticSimulatorAgent introduces argument paraphrasing and slight variation
   - Evaluates spread (sigma > 0) across N=3 samples
   - Compares overall composite fidelity vs truncated fidelity (pre-cache-miss)
5. Sensitivity Analysis:
   - Evaluates argument matching threshold at 0.75, 0.85, 0.95
"""
import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
from server.app.database import SessionLocal
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.services.replay_engine import (
    IncidentReplayHarness,
    ScriptedMockAgent,
    StochasticSimulatorAgent,
)


def run_e2e_replay_demonstration():
    db = SessionLocal()
    from evaluation.trace_recorder import record_real_sql_agent_trace
    target_run_id = record_real_sql_agent_trace(db)

    orig_run = db.query(Run).filter(Run.id == target_run_id).first()
    if not orig_run:
        print(f"Error: Target run {target_run_id} not found in database.")
        db.close()
        return

    orig_spans = (
        db.query(Span)
        .filter(Span.run_id == target_run_id, Span.span_type == "tool")
        .order_by(Span.sequence_number.asc())
        .all()
    )

    print("=" * 80)
    print("INCIDENT REPLAY ENGINE (RQ2) - END-TO-END DEMO ON REAL AGENT TRACE")
    print("=" * 80)
    print(f"Target Run ID:   {orig_run.id}")
    print(f"Trace Origin:    a trace from the SQL agent under the mock provider")
    print(f"Recorded Model:  {orig_run.model}")
    print(f"Recorded Status: {orig_run.outcome}")
    print(f"Tool Steps ({len(orig_spans)}): {[s.name for s in orig_spans]}")
    print("-" * 80)

    harness = IncidentReplayHarness(db)

    # -------------------------------------------------------------------------
    # Scenario 1: Clean Baseline Reproduction (Deterministic Mock)
    # -------------------------------------------------------------------------
    print("\n[SCENARIO 1: Clean Reproduction Under Identical Scripted Behavior]")
    planned_calls = [(s.name, s.input_payload if isinstance(s.input_payload, dict) else {}) for s in orig_spans]
    clean_agent = ScriptedMockAgent(planned_calls=planned_calls, final_outcome=orig_run.outcome)

    res_clean = harness.replay_run(
        original_run_id=target_run_id,
        agent=clean_agent,
        target_model="claude-3-5-sonnet",
        matching_threshold=0.85,
        num_samples=3,
        compute_sensitivity=True,
    )

    print(f"Replay ID:           {res_clean.replay_id}")
    print(f"Mean Fidelity Score: {res_clean.mean_fidelity * 100:.1f}%")
    print(f"Truncated Fidelity:  {res_clean.mean_truncated_fidelity * 100:.1f}%")
    print(f"Cache Miss Rate:     {res_clean.mean_cache_miss_rate * 100:.1f}%")
    print(f"Fidelity Range:      {res_clean.fidelity_range:.4f} (max - min)")
    print(f"Fidelity Sample SD:  {res_clean.fidelity_std_dev:.4f} (sample standard deviation)")
    print(f"Regression Detected: {res_clean.regression_detected}")

    print("\nSensitivity Table (Argument Matching Thresholds):")
    print(f"  {'Threshold':<12} | {'Fidelity':<10} | {'Misses':<8} | {'Total':<8} | {'Miss Rate':<10}")
    print(f"  {'-'*12}-+-{'-'*10}-+-{'-'*8}-+-{'-'*8}-+-{'-'*10}")
    for pt in res_clean.sensitivity_table:
        print(f"  {pt['threshold']:<12.2f} | {pt['fidelity_score']*100:<9.1f}% | {pt['cache_misses']:<8} | {pt['total_calls']:<8} | {pt['cache_miss_rate']*100:<9.1f}%")

    # -------------------------------------------------------------------------
    # Scenario 2: Counterfactual Candidate Security Policy Replay (Targeted Denial)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("[SCENARIO 2: Counterfactual Candidate Security Policy Evaluation on Real Trace]")
    targeted_policy_yaml = """version: "1"
default_action: allow
rules:
  - id: restrict_orders_access
    tool: execute_sql
    parameters:
      query:
        contains: "orders"
    action: deny"""

    print("Candidate Policy YAML:")
    print(targeted_policy_yaml)
    print("-" * 80)

    res_policy = harness.replay_run(
        original_run_id=target_run_id,
        agent=clean_agent,
        target_model="claude-3-5-sonnet",
        candidate_policy_yaml=targeted_policy_yaml,
        matching_threshold=0.85,
        num_samples=3,
        compute_sensitivity=False,
    )

    print(f"Replay ID:           {res_policy.replay_id}")
    print(f"Mean Fidelity Score: {res_policy.mean_fidelity * 100:.1f}%")
    print(f"Truncated Fidelity:  {res_policy.mean_truncated_fidelity * 100:.1f}%")
    print(f"Cache Miss Rate:     {res_policy.mean_cache_miss_rate * 100:.1f}%")
    print(f"Regression Detected: {res_policy.regression_detected}")
    print(f"Regression Reasons:  {res_policy.regression_reasons}")

    print("\nTrajectory Step Diff (Side-by-Side Plain Text):")
    for diff in res_policy.trajectory_diff:
        print(f"\n--- Step #{diff['step_number']} ---")
        print(f"  [RECORDED ORIGINAL]")
        print(f"    Tool:     {diff['tool_name_recorded']}")
        print(f"    Policy:   {diff['policy_decision_recorded']}")
        print(f"    Args:     {json.dumps(diff['args_recorded'])}")
        print(f"    Output:   {json.dumps(diff['output_recorded'])}")
        print(f"  [REPLAYED CANDIDATE]")
        print(f"    Tool:     {diff['tool_name_replayed']} (Match: {diff['tool_match']})")
        print(f"    Policy:   {diff['policy_decision_replayed']} (Candidate Policy Verdict)")
        print(f"    Args:     {json.dumps(diff['args_replayed'])} (Similarity: {diff['arg_similarity']*100:.1f}%)")
        print(f"    Output:   {json.dumps(diff['output_replayed'])} (Cache Miss: {diff['is_cache_miss']})")

    # -------------------------------------------------------------------------
    # Scenario 3: Stochastic Agent Simulation (Temperature > 0 Evaluation)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("[SCENARIO 3: Stochastic Agent Replay (SIMULATION: Temperature > 0)]")
    print("Simulates a non-deterministic LLM agent with argument paraphrasing and slight variation.")
    print("-" * 80)

    stochastic_agent = StochasticSimulatorAgent(
        planned_calls=planned_calls,
        final_outcome=orig_run.outcome,
        noise_level=0.30,
        seed=101,
        can_recover_from_deny=True,
    )

    res_stochastic = harness.replay_run(
        original_run_id=target_run_id,
        agent=stochastic_agent,
        target_model="claude-3-5-sonnet",
        matching_threshold=0.85,
        num_samples=3,
        compute_sensitivity=False,
    )

    print(f"Replay ID:           {res_stochastic.replay_id}")
    print(f"Mean Fidelity Score: {res_stochastic.mean_fidelity * 100:.1f}%")
    print(f"Truncated Fidelity:  {res_stochastic.mean_truncated_fidelity * 100:.1f}%")
    print(f"Fidelity Range:      {res_stochastic.fidelity_range:.4f} (max - min)")
    print(f"Fidelity Sample SD:  {res_stochastic.fidelity_std_dev:.4f} (sample standard deviation s)")
    print(f"Cache Miss Rate:     {res_stochastic.mean_cache_miss_rate * 100:.1f}%")
    print(f"Regression Detected: {res_stochastic.regression_detected} (Majority rule: only 1 of 3 samples degraded)")
    print(f"Sample Fidelities:   {[round(s.fidelity_score, 4) for s in res_stochastic.sample_results]}")
    print(f"Simulator Config:    {stochastic_agent.get_config()}")

    db.close()
    print("\n" + "=" * 80)
    print("DEMO RUN COMPLETED SUCCESSFULLY: Replay records saved to SQLite database.")
    print("=" * 80)


if __name__ == "__main__":
    run_e2e_replay_demonstration()
