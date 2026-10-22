from contextvars import ContextVar
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RunContext:
    run_id: str
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    tags: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    spans: list[dict[str, Any]] = field(default_factory=list)
    running_cost: float = 0.0
    running_tokens: int = 0
    running_prompt_tokens: int = 0
    running_completion_tokens: int = 0
    running_steps: int = 0
    _seq_counter: int = 1

    def allocate_sequence_number(self) -> int:
        seq = self._seq_counter
        self._seq_counter += 1
        return seq

    @property
    def elapsed_seconds(self) -> float:
        now = datetime.now(timezone.utc)
        return (now - self.started_at).total_seconds()


_current_run: ContextVar[Optional[RunContext]] = ContextVar("agentshield_current_run", default=None)
_span_stack: ContextVar[list[str]] = ContextVar("agentshield_span_stack", default=[])


def get_current_run() -> Optional[RunContext]:
    return _current_run.get()


def set_current_run(ctx: Optional[RunContext]):
    return _current_run.set(ctx)


def get_current_parent_span_id() -> Optional[str]:
    stack = _span_stack.get()
    return stack[-1] if stack else None


def push_span_id(span_id: str):
    stack = list(_span_stack.get())
    stack.append(span_id)
    _span_stack.set(stack)


def pop_span_id():
    stack = list(_span_stack.get())
    if stack:
        stack.pop()
        _span_stack.set(stack)
