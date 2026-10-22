"""
AgentShield LangChain Wrapper for Milestone 11 & 12.
NOTE: LangChain is NOT imported directly by this module; this is a lightweight
wrapper (AgentShieldLangChainWrapper) that implements the standard duck-typing
interface (.invoke({'input': ...})) expected by LangChain/LangGraph pipelines
without taking on a heavyweight dependency. In all documentation and evaluation reports,
this component is designated as a wrapper rather than framework-level independence.
"""
from typing import Optional, Any, Callable
from evaluation.agents.base import BaseDemoAgent


class AgentShieldLangChainWrapper:
    """
    Lightweight wrapper adapting an AgentShield demo agent to the standard
    LangChain/LangGraph runnable interface (.invoke(dict) -> dict).
    """
    def __init__(self, agent: BaseDemoAgent, tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]]):
        self.agent = agent
        self.tool_executor = tool_executor

    def invoke(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        prompt = input_dict.get("input") or input_dict.get("prompt") or str(input_dict)
        return self.agent.run(prompt=prompt, tool_executor=self.tool_executor)

    def __call__(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        return self.invoke(input_dict)


# Backward-compatible alias
AgentShieldLangChainAdapter = AgentShieldLangChainWrapper
