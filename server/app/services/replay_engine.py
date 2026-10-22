"""
Milestone 8: Incident Replay Engine (RQ2).

Provides:
- Standard AgentInterface for deterministic agent execution
- ScriptedMockAgent with controllable behavior shifts
- Pure Replay Harness with frozen tool output cache
- Fuzzy argument matching with configurable threshold (0.75, 0.85, 0.95, default 0.85)
- Cache-miss handling with synthetic responses (guaranteed zero live tool execution)
- Candidate policy evaluation reusing pure evaluate_policy()
- Multi-sample replay (N=3) with spread reporting and regression consistency flags
- Trajectory diff generation for side-by-side comparison
"""
import json
import uuid
import statistics
from abc import ABC, abstractmethod
from typing import Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from server.app.models.run import Run
from server.app.models.span import Span
from server.app.models.replay import Replay
from server.app.schemas.replay import BatchReplayResponse, BatchReplayItemSummary
from server.app.services.fidelity import (
    calculate_tool_sequence_similarity,
    calculate_fidelity_score,
    levenshtein_distance,
)
from server.app.services.policy_engine import (
    parse_policy_yaml,
    evaluate_policy,
    RunState,
)


# =========================================================================
# 1. Standard Agent Interface
# =========================================================================

class AgentInterface(ABC):
    """
    Standard interface that demo agents implement to enable deterministic incident replay.
    Allows the replay harness to execute the agent decision loop with substituted models,
    altered system prompts, or candidate policies while intercepting tool invocations.
    """
    @abstractmethod
    def run(
        self,
        prompt: str,
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute agent decision loop.
        tool_executor(tool_name, tool_args) is supplied by the replay harness to return frozen outputs.
        Returns final outcome dict, e.g. {"outcome": "success" | "failure", "result": ...}.
        """
        pass


class ScriptedMockAgent(AgentInterface):
    """
    Deterministic mock agent for testing replay fidelity and regression detection.
    Can be configured with planned tool calls, deliberate behavior shifts, or error simulations.
    """
    def __init__(
        self,
        planned_calls: Optional[list[tuple[str, dict[str, Any]]]] = None,
        final_outcome: str = "success",
        behavior_shift: Optional[str] = None,  # None | "altered_args" | "forbidden_tool" | "loop"
    ):
        self.planned_calls = planned_calls or []
        self.final_outcome = final_outcome
        self.behavior_shift = behavior_shift

    def run(
        self,
        prompt: str,
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        executed_steps = []
        for tool_name, tool_args in self.planned_calls:
            args_to_use = dict(tool_args)

            # Apply controllable behavior shift if requested
            if self.behavior_shift == "altered_args":
                args_to_use["query_filter"] = "modified_unmatched_param"
            elif self.behavior_shift == "forbidden_tool":
                tool_name = "unauthorized_admin_drop"
            elif self.behavior_shift == "loop":
                # Execute same tool multiple times
                for _ in range(3):
                    res = tool_executor(tool_name, args_to_use)
                    executed_steps.append((tool_name, args_to_use, res))
                break

            res = tool_executor(tool_name, args_to_use)
            executed_steps.append((tool_name, args_to_use, res))

            # If tool was blocked or error encountered, stop early
            if res.get("policy_decision") == "deny" or res.get("error"):
                return {"outcome": "failure", "steps": executed_steps, "error": res.get("error")}

        return {"outcome": self.final_outcome, "steps": executed_steps}


class StochasticSimulatorAgent(AgentInterface):
    """
    Stochastic agent simulator modeling non-deterministic LLM behavior (temperature > 0).

    Explicit Configurable Simulation Parameters (swept in M12):
    - paraphrase_rate (float in [0.0, 1.0], default 0.20): Probability that an argument string
      undergoes semantic paraphrasing / format drift.
    - tool_swap_rate (float in [0.0, 1.0], default 0.10): Probability that adjacent tool calls
      are reordered.
    - recovery_rate (float in [0.0, 1.0], default 0.60): Probability that the agent catches a policy deny
      or tool error, logs a notice, and attempts to proceed.
    - can_recover_from_deny (bool, default False): Whether recovery logic is enabled.
    - noise_level (float, default 0.20): Global fallback variance scale.
    - seed (int, default 42): PRNG seed for reproducible simulation.

    NOTE: All results and logs from this agent are labeled 'SIMULATION'.
    """
    def __init__(
        self,
        planned_calls: Optional[list[tuple[str, dict[str, Any]]]] = None,
        final_outcome: str = "success",
        noise_level: float = 0.20,
        paraphrase_rate: Optional[float] = None,
        tool_swap_rate: Optional[float] = None,
        recovery_rate: float = 0.60,
        seed: int = 42,
        can_recover_from_deny: bool = False,
    ):
        self.planned_calls = planned_calls or []
        self.final_outcome = final_outcome
        self.noise_level = noise_level
        self.paraphrase_rate = paraphrase_rate if paraphrase_rate is not None else noise_level
        self.tool_swap_rate = tool_swap_rate if tool_swap_rate is not None else (noise_level * 0.5)
        self.recovery_rate = recovery_rate
        self.seed = seed
        self.can_recover_from_deny = can_recover_from_deny
        self._iteration = 0

    def get_config(self) -> dict[str, Any]:
        return {
            "mode": "SIMULATION",
            "paraphrase_rate": self.paraphrase_rate,
            "tool_swap_rate": self.tool_swap_rate,
            "recovery_rate": self.recovery_rate,
            "can_recover_from_deny": self.can_recover_from_deny,
            "noise_level": self.noise_level,
            "seed": self.seed,
        }

    def run(
        self,
        prompt: str,
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        import random
        rng = random.Random(self.seed + self._iteration * 31)
        self._iteration += 1

        executed_steps = []
        current_outcome = self.final_outcome

        calls = list(self.planned_calls)
        # Occasional tool order swap if multiple calls exist and noise triggers
        if len(calls) >= 2 and rng.random() < self.tool_swap_rate:
            idx1, idx2 = 0, 1
            calls[idx1], calls[idx2] = calls[idx2], calls[idx1]

        for tool_name, tool_args in calls:
            args_to_use = dict(tool_args)
            # Apply simulated argument paraphrasing noise
            if rng.random() < self.paraphrase_rate:
                for k, v in list(args_to_use.items()):
                    if isinstance(v, str):
                        args_to_use[k] = f"{v} (verified)"
                    elif isinstance(v, (int, float)):
                        args_to_use[k] = float(v)

            res = tool_executor(tool_name, args_to_use)
            executed_steps.append((tool_name, args_to_use, res))

            if res.get("policy_decision") == "deny" or res.get("error"):
                if self.can_recover_from_deny and rng.random() < self.recovery_rate:
                    # Simulated agent recovers by logging notice and proceeding
                    continue
                else:
                    current_outcome = "failure"
                    break

        return {
            "outcome": current_outcome,
            "steps": executed_steps,
            "simulation": True,
            "mode": "SIMULATION",
            "simulator_config": self.get_config(),
        }


# =========================================================================
# 2. Argument Similarity & Matching
# =========================================================================

def calculate_arg_similarity(args_a: Any, args_b: Any) -> float:
    """
    Calculate similarity between two argument payloads in [0.0, 1.0].
    Uses normalized Levenshtein distance on canonical JSON serialized strings.
    """
    if args_a == args_b:
        return 1.0
    if args_a is None or args_b is None:
        return 0.0

    try:
        str_a = json.dumps(args_a, sort_keys=True, ensure_ascii=False)
        str_b = json.dumps(args_b, sort_keys=True, ensure_ascii=False)
    except Exception:
        str_a = str(args_a)
        str_b = str(args_b)

    if not str_a and not str_b:
        return 1.0
    max_len = max(len(str_a), len(str_b))
    if max_len == 0:
        return 1.0

    dist = levenshtein_distance(str_a, str_b)
    return round(max(0.0, min(1.0, 1.0 - (dist / max_len))), 4)


# =========================================================================
# 3. Trajectory Step Diff Models
# =========================================================================

@dataclass
class TrajectoryStepDiff:
    step_number: int
    tool_name_recorded: Optional[str]
    tool_name_replayed: Optional[str]
    tool_match: bool
    args_recorded: Any
    args_replayed: Any
    arg_similarity: float
    output_recorded: Any
    output_replayed: Any
    policy_decision_recorded: Optional[str]
    policy_decision_replayed: Optional[str]
    is_cache_miss: bool


@dataclass
class ReplaySampleResult:
    sample_index: int
    fidelity_score: float
    fidelity_truncated: float
    s_tool: float
    s_args: float
    s_outcome: float
    cache_miss_rate: float
    total_calls: int
    cache_misses: int
    replayed_outcome: str
    replayed_tools: list[str]


@dataclass
class ReplayExecutionResult:
    replay_id: str
    original_run_id: str
    target_model: Optional[str]
    target_prompt_version: Optional[str]
    candidate_policy_version_id: Optional[str]
    matching_threshold: float
    num_samples: int
    mean_fidelity: float
    mean_truncated_fidelity: float
    fidelity_spread: float  # Legacy alias for range
    fidelity_range: float   # Sample Range: max - min
    fidelity_std_dev: float # Sample Standard Deviation (s)
    mean_cache_miss_rate: float
    regression_detected: bool
    regression_reasons: list[str]
    sample_results: list[ReplaySampleResult]
    trajectory_diff: list[dict[str, Any]]
    sensitivity_table: Optional[list[dict[str, Any]]] = None


# =========================================================================
# 4. Incident Replay Harness
# =========================================================================

class IncidentReplayHarness:
    """
    Executes incident replays using frozen tool outputs recorded from an original run.
    Guarantees that no live tool ever executes (cache misses return synthetic error responses).
    Supports candidate policy evaluation, fuzzy argument matching, multi-sample spread,
    and regression detection.
    """

    def __init__(self, db: Session):
        self.db = db

    def replay_run(
        self,
        original_run_id: str,
        agent: AgentInterface,
        target_model: Optional[str] = None,
        target_prompt: Optional[str] = None,
        candidate_policy_yaml: Optional[str] = None,
        candidate_policy_version_id: Optional[str] = None,
        matching_threshold: float = 0.85,
        num_samples: int = 3,
        compute_sensitivity: bool = False,
    ) -> ReplayExecutionResult:
        """
        Executes replay of an original run over num_samples repetitions.
        """
        # 1. Fetch original run and tool spans
        orig_run: Optional[Run] = self.db.query(Run).filter(Run.id == original_run_id).first()
        if not orig_run:
            raise ValueError(f"Original run '{original_run_id}' not found")

        spans: list[Span] = (
            self.db.query(Span)
            .filter(Span.run_id == original_run_id, Span.span_type == "tool")
            .order_by(Span.sequence_number.asc(), Span.started_at.asc())
            .all()
        )

        recorded_tools = [s.name for s in spans]
        recorded_steps = [
            {
                "sequence_number": s.sequence_number or (idx + 1),
                "name": s.name,
                "input_payload": s.input_payload,
                "output_payload": s.output_payload,
                "policy_decision": s.policy_decision or "allow",
                "policy_rule_id": s.policy_rule_id,
            }
            for idx, s in enumerate(spans)
        ]

        # 2. Parse candidate policy if supplied
        candidate_policy_config = None
        if candidate_policy_yaml and candidate_policy_yaml.strip():
            candidate_policy_config = parse_policy_yaml(candidate_policy_yaml)

        # 3. Execute N samples
        sample_results: list[ReplaySampleResult] = []
        sample_diffs: list[list[TrajectoryStepDiff]] = []

        for sample_idx in range(1, num_samples + 1):
            replayed_calls: list[dict[str, Any]] = []
            cache_misses = 0

            # Step-aware cursor to track matching recorded steps sequentially in-order
            used_recorded_indices = set()
            cursor_idx = 0

            def _tool_interceptor(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
                nonlocal cache_misses, cursor_idx
                step_idx = len(replayed_calls) + 1

                # 1. Candidate Policy Check (evaluates exact pure evaluate_policy function)
                policy_decision = "allow"
                policy_rule_id = None
                if candidate_policy_config:
                    run_state = RunState(
                        run_id=original_run_id,
                        current_cost=0.0,
                        current_tokens=0,
                        current_steps=step_idx,
                        elapsed_wall_time_seconds=0.0,
                    )
                    pol_res = evaluate_policy(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        policy=candidate_policy_config,
                        run_state=run_state,
                    )
                    policy_decision = pol_res.decision
                    policy_rule_id = pol_res.rule_id
                    if policy_decision == "deny":
                        # Match against recorded steps to find corresponding recorded index for diff
                        match_idx = None
                        arg_sim = 0.0
                        for r_idx in range(cursor_idx, len(recorded_steps)):
                            rec = recorded_steps[r_idx]
                            if rec["name"] == tool_name:
                                sim = calculate_arg_similarity(tool_args, rec["input_payload"])
                                if sim > arg_sim:
                                    arg_sim = sim
                                    match_idx = r_idx
                        # Blocked under candidate policy!
                        call_record = {
                            "step_number": step_idx,
                            "name": tool_name,
                            "args": tool_args,
                            "output": {"error": f"Policy violation: Blocked by candidate policy rule '{policy_rule_id}'"},
                            "policy_decision": "deny",
                            "policy_rule_id": policy_rule_id,
                            "matched_recorded_index": match_idx,
                            "is_cache_miss": False,
                            "arg_similarity": arg_sim,
                        }
                        replayed_calls.append(call_record)
                        return {"policy_decision": "deny", "error": call_record["output"]["error"]}

                # 2. Fuzzy Match against recorded tool spans (strictly in-order forward search priority)
                best_match_idx = None
                best_similarity = -1.0

                # Search forward from cursor position first
                for r_idx in range(cursor_idx, len(recorded_steps)):
                    rec = recorded_steps[r_idx]
                    if rec["name"] == tool_name and r_idx not in used_recorded_indices:
                        sim = calculate_arg_similarity(tool_args, rec["input_payload"])
                        if sim > best_similarity:
                            best_similarity = sim
                            best_match_idx = r_idx
                        if sim >= 0.999:
                            break

                # Fallback: if no forward match found, inspect earlier unused recorded steps
                if best_match_idx is None:
                    for r_idx in range(0, cursor_idx):
                        rec = recorded_steps[r_idx]
                        if rec["name"] == tool_name and r_idx not in used_recorded_indices:
                            sim = calculate_arg_similarity(tool_args, rec["input_payload"])
                            if sim > best_similarity:
                                best_similarity = sim
                                best_match_idx = r_idx
                            if sim >= 0.999:
                                break

                # Check against matching threshold
                if best_match_idx is not None and best_similarity >= matching_threshold:
                    used_recorded_indices.add(best_match_idx)
                    cursor_idx = max(cursor_idx, best_match_idx + 1)
                    matched_output = recorded_steps[best_match_idx]["output_payload"]
                    call_record = {
                        "step_number": step_idx,
                        "name": tool_name,
                        "args": tool_args,
                        "output": matched_output,
                        "policy_decision": policy_decision,
                        "policy_rule_id": policy_rule_id,
                        "matched_recorded_index": best_match_idx,
                        "is_cache_miss": False,
                        "arg_similarity": best_similarity,
                    }
                    replayed_calls.append(call_record)
                    return matched_output if isinstance(matched_output, dict) else {"result": matched_output}
                else:
                    # CACHE MISS: Return synthetic recorded response, NEVER call a live tool!
                    cache_misses += 1
                    synthetic_miss_resp = {
                        "replay_cache_miss": True,
                        "error": f"Replay cache miss: No recorded output for tool '{tool_name}' with matching arguments",
                        "similarity": max(0.0, best_similarity),
                    }
                    call_record = {
                        "step_number": step_idx,
                        "name": tool_name,
                        "args": tool_args,
                        "output": synthetic_miss_resp,
                        "policy_decision": policy_decision,
                        "policy_rule_id": policy_rule_id,
                        "matched_recorded_index": None,
                        "is_cache_miss": True,
                        "arg_similarity": max(0.0, best_similarity),
                    }
                    replayed_calls.append(call_record)
                    return synthetic_miss_resp

            # Run agent decision loop
            prompt_to_use = target_prompt or "Execute replayed task"
            agent_out = agent.run(prompt=prompt_to_use, tool_executor=_tool_interceptor, model=target_model)
            replayed_outcome = agent_out.get("outcome", "success")

            # Compute sample fidelity
            # Canonical Rule: Exclude candidate-policy denied calls from allowed executed sequence
            allowed_calls = [c for c in replayed_calls if c.get("policy_decision") != "deny"]
            replayed_tool_names = [c["name"] for c in allowed_calls]
            s_tool = calculate_tool_sequence_similarity(recorded_tools, replayed_tool_names)

            # S_args: Canonical Plan Definition: mean argument similarity over matched allowed tool steps only
            matched_arg_sims = [
                c["arg_similarity"]
                for c in allowed_calls
                if (not c["is_cache_miss"] and c["matched_recorded_index"] is not None)
            ]
            s_args = (
                statistics.mean(matched_arg_sims)
                if matched_arg_sims
                else (1.0 if not recorded_tools and not replayed_tool_names else 0.0)
            )
            s_outcome = 1.0 if replayed_outcome == orig_run.outcome else 0.0

            sample_fidelity = calculate_fidelity_score(s_tool, s_args, s_outcome)
            sample_miss_rate = round(cache_misses / len(replayed_calls), 4) if replayed_calls else 0.0

            # Truncated Fidelity: evaluated on steps up to the first cache miss
            first_miss_idx = next((idx for idx, c in enumerate(replayed_calls) if c["is_cache_miss"]), None)
            if first_miss_idx is None:
                sample_fidelity_trunc = sample_fidelity
            elif first_miss_idx == 0:
                sample_fidelity_trunc = 0.0
            else:
                prefix_rec_tools = recorded_tools[:first_miss_idx]
                prefix_rep_tools = [c["name"] for c in replayed_calls[:first_miss_idx]]
                s_tool_trunc = calculate_tool_sequence_similarity(prefix_rec_tools, prefix_rep_tools)
                matched_trunc_sims = [
                    c["arg_similarity"]
                    for c in replayed_calls[:first_miss_idx]
                    if (not c["is_cache_miss"] and c["matched_recorded_index"] is not None)
                ]
                s_args_trunc = statistics.mean(matched_trunc_sims) if matched_trunc_sims else 0.0
                s_outcome_trunc = 1.0
                sample_fidelity_trunc = calculate_fidelity_score(s_tool_trunc, s_args_trunc, s_outcome_trunc)

            sample_res = ReplaySampleResult(
                sample_index=sample_idx,
                fidelity_score=sample_fidelity,
                fidelity_truncated=round(sample_fidelity_trunc, 4),
                s_tool=round(s_tool, 4),
                s_args=round(s_args, 4),
                s_outcome=s_outcome,
                cache_miss_rate=sample_miss_rate,
                total_calls=len(replayed_calls),
                cache_misses=cache_misses,
                replayed_outcome=replayed_outcome,
                replayed_tools=replayed_tool_names,
            )
            sample_results.append(sample_res)

            # Build step-by-step diff for this sample
            step_diffs: list[TrajectoryStepDiff] = []
            max_steps = max(len(recorded_steps), len(replayed_calls))
            for i in range(max_steps):
                rec_step = recorded_steps[i] if i < len(recorded_steps) else None
                rep_step = replayed_calls[i] if i < len(replayed_calls) else None

                t_rec = rec_step["name"] if rec_step else None
                t_rep = rep_step["name"] if rep_step else None
                t_match = (t_rec == t_rep) and (t_rec is not None)

                arg_sim = (
                    calculate_arg_similarity(rec_step["input_payload"], rep_step["args"])
                    if (rec_step and rep_step)
                    else 0.0
                )

                diff = TrajectoryStepDiff(
                    step_number=i + 1,
                    tool_name_recorded=t_rec,
                    tool_name_replayed=t_rep,
                    tool_match=t_match,
                    args_recorded=rec_step["input_payload"] if rec_step else None,
                    args_replayed=rep_step["args"] if rep_step else None,
                    arg_similarity=arg_sim,
                    output_recorded=rec_step["output_payload"] if rec_step else None,
                    output_replayed=rep_step["output"] if rep_step else None,
                    policy_decision_recorded=rec_step["policy_decision"] if rec_step else None,
                    policy_decision_replayed=rep_step["policy_decision"] if rep_step else None,
                    is_cache_miss=rep_step["is_cache_miss"] if rep_step else False,
                )
                step_diffs.append(diff)
            sample_diffs.append(step_diffs)

        # 4. Aggregate metrics across samples
        fidelities = [s.fidelity_score for s in sample_results]
        trunc_fidelities = [s.fidelity_truncated for s in sample_results]
        miss_rates = [s.cache_miss_rate for s in sample_results]
        mean_fid = round(statistics.mean(fidelities), 4)
        mean_trunc_fid = round(statistics.mean(trunc_fidelities), 4)
        spread_range = round(max(fidelities) - min(fidelities), 4)
        sample_std_dev = round(statistics.stdev(fidelities), 4) if len(fidelities) > 1 else 0.0
        mean_miss_rate = round(statistics.mean(miss_rates), 4)

        # 5. Regression Detection Consistency (Majority Rule)
        # Consistent with RQ2 definition: Flag regression ONLY when a majority of samples
        # individually breach the threshold (>= max(1, num_samples // 2 + 1)), preventing
        # healthy stochastic agents from being falsely flagged due to a single outlier.
        majority_threshold = max(1, num_samples // 2 + 1)
        low_fidelity_samples = sum(1 for s in sample_results if s.fidelity_score < 0.80)
        policy_blocks_count = sum(
            1 for s in sample_results
            if any(c.policy_decision_replayed == "deny" for c in sample_diffs[s.sample_index - 1])
        )
        failures_count = sum(1 for s in sample_results if s.replayed_outcome != orig_run.outcome)

        regression_reasons = []
        if low_fidelity_samples >= majority_threshold:
            regression_reasons.append(
                f"Low composite fidelity (< 0.80) across majority of samples ({low_fidelity_samples}/{num_samples})"
            )
        if policy_blocks_count >= majority_threshold:
            regression_reasons.append(
                f"Candidate policy blocked tool execution across majority of samples ({policy_blocks_count}/{num_samples})"
            )
        if failures_count >= majority_threshold:
            regression_reasons.append(
                f"Outcome divergence across majority of samples ({failures_count}/{num_samples})"
            )

        regression_detected = len(regression_reasons) > 0

        # Primary trajectory diff from sample 1 (JSON-serializable)
        primary_diff = [
            {
                "step_number": d.step_number,
                "tool_name_recorded": d.tool_name_recorded,
                "tool_name_replayed": d.tool_name_replayed,
                "tool_match": d.tool_match,
                "args_recorded": d.args_recorded,
                "args_replayed": d.args_replayed,
                "arg_similarity": d.arg_similarity,
                "output_recorded": d.output_recorded,
                "output_replayed": d.output_replayed,
                "policy_decision_recorded": d.policy_decision_recorded,
                "policy_decision_replayed": d.policy_decision_replayed,
                "is_cache_miss": d.is_cache_miss,
            }
            for d in sample_diffs[0]
        ]

        # Optional threshold sensitivity analysis (0.75, 0.85, 0.95)
        sensitivity_table = None
        if compute_sensitivity:
            sensitivity_table = self.evaluate_threshold_sensitivity(
                original_run_id=original_run_id,
                agent=agent,
                target_model=target_model,
                target_prompt=target_prompt,
                thresholds=[0.75, 0.85, 0.95],
            )

        replay_id = f"replay-{uuid.uuid4().hex[:12]}"

        # Persist Replay model record
        replay_record = Replay(
            id=replay_id,
            original_run_id=original_run_id,
            target_model=target_model or orig_run.model,
            target_prompt_version=target_prompt or orig_run.prompt_version,
            candidate_policy_version_id=candidate_policy_version_id,
            outcome=sample_results[0].replayed_outcome,
            fidelity_score=mean_fid,
            fidelity_truncated=mean_trunc_fid,
            cache_miss_rate=mean_miss_rate,
            trajectory_diff={"steps": primary_diff, "regression_reasons": regression_reasons},
            sample_results=[
                {
                    "sample_index": s.sample_index,
                    "fidelity_score": s.fidelity_score,
                    "fidelity_truncated": s.fidelity_truncated,
                    "s_tool": s.s_tool,
                    "s_args": s.s_args,
                    "s_outcome": s.s_outcome,
                    "cache_miss_rate": s.cache_miss_rate,
                    "replayed_outcome": s.replayed_outcome,
                    "replayed_tools": s.replayed_tools,
                }
                for s in sample_results
            ],
        )
        self.db.add(replay_record)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

        return ReplayExecutionResult(
            replay_id=replay_id,
            original_run_id=original_run_id,
            target_model=target_model or orig_run.model,
            target_prompt_version=target_prompt or orig_run.prompt_version,
            candidate_policy_version_id=candidate_policy_version_id,
            matching_threshold=matching_threshold,
            num_samples=num_samples,
            mean_fidelity=mean_fid,
            mean_truncated_fidelity=mean_trunc_fid,
            fidelity_spread=spread_range,
            fidelity_range=spread_range,
            fidelity_std_dev=sample_std_dev,
            mean_cache_miss_rate=mean_miss_rate,
            regression_detected=regression_detected,
            regression_reasons=regression_reasons,
            sample_results=sample_results,
            trajectory_diff=primary_diff,
            sensitivity_table=sensitivity_table,
        )

    def evaluate_threshold_sensitivity(
        self,
        original_run_id: str,
        agent: AgentInterface,
        target_model: Optional[str] = None,
        target_prompt: Optional[str] = None,
        thresholds: Optional[list[float]] = None,
    ) -> list[dict[str, Any]]:
        """
        Runs sensitivity analysis across specified thresholds (0.75, 0.85, 0.95),
        reporting cache-miss rate and composite fidelity at each threshold.
        """
        eval_thresholds = thresholds or [0.75, 0.85, 0.95]
        results = []
        for thresh in eval_thresholds:
            res = self.replay_run(
                original_run_id=original_run_id,
                agent=agent,
                target_model=target_model,
                target_prompt=target_prompt,
                matching_threshold=thresh,
                num_samples=1,
                compute_sensitivity=False,
            )
            results.append(
                {
                    "threshold": thresh,
                    "fidelity_score": res.mean_fidelity,
                    "cache_miss_rate": res.mean_cache_miss_rate,
                    "cache_misses": res.sample_results[0].cache_misses,
                    "total_calls": res.sample_results[0].total_calls,
                }
            )
        return results

    def replay_batch(
        self,
        run_ids: list[str],
        agent: Optional[AgentInterface] = None,
        target_model: Optional[str] = None,
        target_prompt: Optional[str] = None,
        candidate_policy_yaml: Optional[str] = None,
        matching_threshold: float = 0.85,
        num_samples: int = 3,
        compute_sensitivity: bool = False,
    ) -> BatchReplayResponse:
        """
        Executes batch replay across a list of run UUIDs.
        Aggregates fidelity scores, truncated fidelity, cache miss rates, and regression detection counts.
        Generates markdown and JSON report summaries.
        Missing run IDs are recorded gracefully without failing the entire batch.
        """
        items: list[BatchReplayItemSummary] = []
        missing_run_ids: list[str] = []

        for rid in run_ids:
            orig_run = self.db.query(Run).filter(Run.id == rid).first()
            if not orig_run:
                missing_run_ids.append(rid)
                items.append(
                    BatchReplayItemSummary(
                        run_id=rid,
                        status="not_found",
                        error=f"Run '{rid}' not found in database",
                    )
                )
                continue

            try:
                # If no custom agent provided, construct default ScriptedMockAgent from recorded tool spans
                if agent is None:
                    tool_spans = (
                        self.db.query(Span)
                        .filter(Span.run_id == rid, Span.span_type == "tool")
                        .order_by(Span.sequence_number.asc(), Span.started_at.asc())
                        .all()
                    )
                    planned = [(s.name, s.input_payload if isinstance(s.input_payload, dict) else {}) for s in tool_spans]
                    run_agent = ScriptedMockAgent(planned_calls=planned, final_outcome=orig_run.outcome)
                else:
                    run_agent = agent

                res = self.replay_run(
                    original_run_id=rid,
                    agent=run_agent,
                    target_model=target_model,
                    target_prompt=target_prompt,
                    candidate_policy_yaml=candidate_policy_yaml,
                    matching_threshold=matching_threshold,
                    num_samples=num_samples,
                    compute_sensitivity=compute_sensitivity,
                )
                items.append(
                    BatchReplayItemSummary(
                        run_id=rid,
                        replay_id=res.replay_id,
                        status="replayed",
                        model=res.target_model,
                        fidelity_score=res.mean_fidelity,
                        fidelity_truncated=res.mean_truncated_fidelity,
                        cache_miss_rate=res.mean_cache_miss_rate,
                        regression_detected=res.regression_detected,
                        regression_reasons=res.regression_reasons,
                    )
                )
            except Exception as e:
                items.append(
                    BatchReplayItemSummary(
                        run_id=rid,
                        status="error",
                        error=str(e),
                    )
                )

        successful = [it for it in items if it.status == "replayed"]
        total_req = len(run_ids)
        succ_count = len(successful)
        failed_count = total_req - succ_count

        mean_fid = round(statistics.mean([it.fidelity_score for it in successful]), 4) if successful else 0.0
        mean_trunc = round(statistics.mean([it.fidelity_truncated for it in successful]), 4) if successful else 0.0
        mean_miss = round(statistics.mean([it.cache_miss_rate for it in successful]), 4) if successful else 0.0
        reg_count = sum(1 for it in successful if it.regression_detected)
        reg_rate = round(reg_count / succ_count, 4) if succ_count else 0.0

        # Build Markdown report
        md_lines = [
            "# AgentShield Batch Incident Replay Report",
            "",
            f"**Generated At**: {datetime.now(timezone.utc).isoformat()}",
            f"- **Total Runs Requested**: {total_req}",
            f"- **Successfully Replayed**: {succ_count}",
            f"- **Failed / Missing**: {failed_count}",
            f"- **Mean Composite Fidelity**: {mean_fid * 100:.1f}%",
            f"- **Mean Truncated Fidelity (Pre-Cache-Miss)**: {mean_trunc * 100:.1f}%",
            f"- **Mean Cache-Miss Rate**: {mean_miss * 100:.1f}%",
            f"- **Regressions Flagged**: {reg_count} ({reg_rate * 100:.1f}%)",
            "",
            "## Replayed Runs Detail Table",
            "",
            "| Run ID | Status | Model | Overall Fidelity | Truncated Fidelity | Cache Miss Rate | Regression? | Reasons |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for it in items:
            if it.status == "replayed":
                reg_str = "**YES**" if it.regression_detected else "No"
                fid_str = f"{it.fidelity_score * 100:.1f}%" if it.fidelity_score is not None else "-"
                trunc_str = f"{it.fidelity_truncated * 100:.1f}%" if it.fidelity_truncated is not None else "-"
                miss_str = f"{it.cache_miss_rate * 100:.1f}%" if it.cache_miss_rate is not None else "-"
                reasons_str = "; ".join(it.regression_reasons) if it.regression_reasons else "-"
                md_lines.append(f"| `{it.run_id[:16]}...` | `{it.status}` | `{it.model or 'default'}` | {fid_str} | {trunc_str} | {miss_str} | {reg_str} | {reasons_str} |")
            else:
                md_lines.append(f"| `{it.run_id[:16]}...` | `{it.status}` | - | - | - | - | - | {it.error or 'N/A'} |")

        markdown_report = "\n".join(md_lines)

        json_report = {
            "summary": {
                "total_requested": total_req,
                "successful_replays": succ_count,
                "failed_replays": failed_count,
                "mean_fidelity": mean_fid,
                "mean_truncated_fidelity": mean_trunc,
                "mean_cache_miss_rate": mean_miss,
                "regressions_detected": reg_count,
                "regression_rate": reg_rate,
            },
            "total_requested": total_req,
            "successful_replays": succ_count,
            "failed_replays": failed_count,
            "mean_fidelity": mean_fid,
            "mean_truncated_fidelity": mean_trunc,
            "mean_cache_miss_rate": mean_miss,
            "regressions_detected": reg_count,
            "regression_rate": reg_rate,
            "runs": [it.model_dump() for it in items],
            "items": [it.model_dump() for it in items],
            "missing_run_ids": missing_run_ids,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        return BatchReplayResponse(
            total_requested=total_req,
            successful_replays=succ_count,
            failed_replays=failed_count,
            mean_fidelity=mean_fid,
            mean_truncated_fidelity=mean_trunc,
            mean_cache_miss_rate=mean_miss,
            regressions_detected=reg_count,
            regression_rate=reg_rate,
            items=items,
            missing_run_ids=missing_run_ids,
            markdown_report=markdown_report,
            json_report=json_report,
        )
