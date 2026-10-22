"""
Stochastic Simulation Agent for Milestone 11 (RQ2).
Evaluates agent replay and regression detection under temperature > 0 variation.

CRITICAL METHODOLOGICAL NOTE:
All outputs from this agent are labeled 'SIMULATION'. Its results measure its configured
parameters (paraphrase rate, tool swap rate, recovery rate). It allows controlled sweeps
of non-deterministic variance prior to live LLM runs.
"""
import random
from typing import Optional, Callable, Any
from evaluation.agents.base import BaseDemoAgent, AgentStepLog
from evaluation.llm_provider import BaseLLMProvider, MockLLMProvider, ChatMessage


class StochasticDemoAgent(BaseDemoAgent):
    """
    Stochastic Non-Deterministic Agent Simulator.
    Introduces controllable argument paraphrasing and tool variations to simulate temperature > 0.
    All outputs and reports explicitly label execution as [SIMULATION].
    """
    name: str = "stochastic_agent"
    mode: str = "SIMULATION"

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        paraphrase_rate: float = 0.25,
        tool_swap_rate: float = 0.05,
        recovery_rate: float = 0.50,
        noise_level: float = 0.20,
        seed: int = 42,
    ):
        super().__init__(llm_provider or MockLLMProvider())
        self.paraphrase_rate = paraphrase_rate
        self.tool_swap_rate = tool_swap_rate
        self.recovery_rate = recovery_rate
        self.noise_level = noise_level
        self.seed = seed
        self._rng = random.Random(seed)

    def get_config(self) -> dict[str, Any]:
        return {
            "mode": "SIMULATION",
            "paraphrase_rate": self.paraphrase_rate,
            "tool_swap_rate": self.tool_swap_rate,
            "recovery_rate": self.recovery_rate,
            "noise_level": self.noise_level,
            "seed": self.seed,
        }

    def _paraphrase_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Apply slight non-semantic paraphrasing (synonyms, whitespace, reordered filters)."""
        modified = dict(args)
        for k, v in list(modified.items()):
            if isinstance(v, str):
                if self._rng.random() < self.paraphrase_rate:
                    synonyms = {
                        "active": "status = 'active'",
                        "report.txt": "./report.txt",
                        "status": "current_status",
                        "admin": "administrator",
                    }
                    if v in synonyms and self._rng.random() < 0.5:
                        modified[k] = synonyms[v]
                    elif " " in v and self._rng.random() < 0.5:
                        # Extra spacing or case shift
                        modified[k] = "  ".join(v.split())
        return modified

    def run(
        self,
        prompt: str,
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        step_logs: list[AgentStepLog] = []

        # Generate base intent from provider
        messages = [ChatMessage(role="user", content=prompt)]
        base_resp = self.llm_provider.generate(messages)

        planned_calls = base_resp.tool_calls
        if not planned_calls:
            # Fallback planned tool call based on prompt
            planned_calls = [
                # Generic analytics call
                type("ToolCall", (), {"name": "execute_sql", "arguments": {"query": "SELECT count(*) FROM users WHERE status = 'active';"}})()
            ]

        for i, tc in enumerate(planned_calls):
            tool_name = tc.name
            args = dict(tc.arguments) if isinstance(tc.arguments, dict) else {}

            # 1. Stochastic tool swap simulation
            if self._rng.random() < self.tool_swap_rate:
                swaps = {"execute_sql": "run_sql_query", "fetch_url": "http_get", "poll_status": "check_job_status"}
                tool_name = swaps.get(tool_name, tool_name)

            # 2. Stochastic argument paraphrasing simulation
            args = self._paraphrase_args(args)

            tool_res = tool_executor(tool_name, args)
            step_log = AgentStepLog(
                step_number=i + 1,
                tool_name=tool_name,
                tool_args=args,
                output=tool_res.get("output"),
                policy_decision=tool_res.get("policy_decision", "allow"),
                error=tool_res.get("error"),
            )
            step_logs.append(step_log)

            if tool_res.get("policy_decision") == "deny":
                # Check recovery rate
                if self._rng.random() < self.recovery_rate:
                    # Attempt safe recovery step
                    recovery_res = tool_executor("fallback_echo", {"msg": "Alternative action taken"})
                    step_logs.append(AgentStepLog(
                        step_number=i + 2,
                        tool_name="fallback_echo",
                        tool_args={"msg": "Alternative action taken"},
                        output=recovery_res.get("output"),
                        policy_decision=recovery_res.get("policy_decision", "allow"),
                    ))
                    return {
                        "outcome": "success",
                        "final_answer": "[SIMULATION] Recovered gracefully from policy block via alternative fallback.",
                        "steps": step_logs,
                        "metadata": {"simulation": True, "config": self.get_config()},
                    }
                else:
                    return {
                        "outcome": "blocked",
                        "final_answer": f"[SIMULATION] Blocked by policy on step {i+1}: {tool_res.get('error') or 'denied'}",
                        "steps": step_logs,
                        "metadata": {"simulation": True, "config": self.get_config()},
                    }

        return {
            "outcome": "success",
            "final_answer": f"[SIMULATION] Task completed under stochastic temperature simulation.",
            "steps": step_logs,
            "metadata": {"simulation": True, "config": self.get_config()},
        }
