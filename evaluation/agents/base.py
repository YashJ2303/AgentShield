"""
Base Agent Interface and Execution Harness for Milestone 11 Demo Agents.
Implements the Replay Agent Interface compatible with IncidentReplayHarness.
"""
from abc import ABC, abstractmethod
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from server.app.services.replay_engine import AgentInterface


@dataclass
class AgentStepLog:
    step_number: int
    tool_name: str
    tool_args: dict[str, Any]
    output: Any
    policy_decision: str = "allow"  # 'allow' | 'deny'
    error: Optional[str] = None


@dataclass
class AgentRunResult:
    agent_name: str
    task_id: str
    outcome: str  # 'success' | 'failure' | 'blocked'
    final_answer: str
    steps: list[AgentStepLog] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseDemoAgent(AgentInterface, ABC):
    """
    Abstract base demo agent implementing the IncidentReplayHarness AgentInterface.
    Can run against live tools or replayed frozen tool executors.
    """
    name: str = "base_agent"
    system_prompt: str = "You are a helpful assistant."

    def __init__(self, llm_provider: Optional[Any] = None):
        self.llm_provider = llm_provider

    @abstractmethod
    def run(
        self,
        prompt: str,
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute agent loop.
        tool_executor(tool_name, tool_args) -> {"output": ..., "policy_decision": "allow"|"deny", "error": ...}
        Returns:
            {"outcome": "success"|"failure"|"blocked", "final_answer": ..., "steps": list[AgentStepLog]}
        """
        pass
