from enum import Enum


class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    TIMED_OUT = "timed_out"


class SpanType(str, Enum):
    MODEL = "model"
    TOOL = "tool"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    BYPASSED = "bypassed"


class FailureCategory(str, Enum):
    TOOL_ERROR = "tool_error"
    POLICY_BLOCK = "policy_block"
    TIMEOUT = "timeout"
    LOOP = "loop"
    MALFORMED_OUTPUT = "malformed_output"
    BUDGET_EXCEEDED = "budget_exceeded"
    OTHER = "other"
