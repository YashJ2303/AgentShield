class AgentShieldError(Exception):
    """Base exception for all AgentShield errors."""
    pass


class PolicyViolationError(AgentShieldError):
    """Raised when a tool execution is blocked by the security gateway policy."""
    def __init__(self, message: str, rule_id: str = None, reason: str = None):
        super().__init__(message)
        self.rule_id = rule_id
        self.reason = reason


class GatewayUnreachableError(AgentShieldError):
    """Raised when the AgentShield gateway server cannot be contacted in fail-closed mode."""
    pass
