from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any


class PolicyLimits(BaseModel):
    max_cost_per_run: Optional[float] = Field(None, ge=0.0)
    max_tokens_per_run: Optional[int] = Field(None, ge=0)
    max_steps_per_run: Optional[int] = Field(None, ge=0)
    max_wall_time_seconds: Optional[float] = Field(None, ge=0.0)


class SQLCheckConfig(BaseModel):
    arg: Optional[str] = Field("query", description="Name of the tool argument containing the SQL statement")
    allowed_operations: list[str] = Field(
        default_factory=lambda: ["SELECT"],
        description="List of permitted SQL statement types (defaults to SELECT-only unless specified)",
    )
    blocked_operations: list[str] = Field(
        default_factory=lambda: [
            "DROP", "TRUNCATE", "ALTER", "ATTACH", "PRAGMA", "REPLACE",
            "VACUUM", "CREATE", "GRANT", "REVOKE"
        ],
        description="List of explicitly blocked destructive or administrative SQL operations",
    )
    require_where_clause_on: list[str] = Field(default_factory=lambda: ["DELETE", "UPDATE"])


class RateLimitConfig(BaseModel):
    max_calls_per_run: int = Field(..., gt=0)


class InjectionScreeningConfig(BaseModel):
    enabled: bool = True
    default_action: str = Field("block", description="Default injection action: block | flag | sanitize")

    @field_validator("default_action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid_actions = {"block", "flag", "sanitize"}
        if v.lower() not in valid_actions:
            raise ValueError(f"default_action must be one of {valid_actions}, got '{v}'")
        return v.lower()


class PolicyRule(BaseModel):
    id: str
    tool: str  # specific tool name or '*'
    action: str  # allow | deny | require_approval
    timeout_seconds: Optional[int] = Field(60, ge=1)
    constraints: Optional[dict[str, Any]] = None  # argument regex or condition
    parameters: Optional[dict[str, Any]] = None   # alias for constraints
    sql_check: Optional[SQLCheckConfig] = None
    path_arg: Optional[str] = Field(None, description="Explicit tool argument name containing the file path (defaults to 'path')")
    path_allowlist: Optional[list[str]] = None
    path_denylist: Optional[list[str]] = None
    domain_arg: Optional[str] = Field(None, description="Explicit tool argument name containing the domain/URL (defaults to 'url')")
    domain_allowlist: Optional[list[str]] = None
    rate_limit: Optional[RateLimitConfig] = None
    injection_action: Optional[str] = Field(None, description="Per-tool injection action: 'block' | 'flag' | 'sanitize'")

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid_actions = {"allow", "deny", "require_approval"}
        if v.lower() not in valid_actions:
            raise ValueError(f"Action must be one of {valid_actions}, got '{v}'")
        return v.lower()

    @field_validator("injection_action")
    @classmethod
    def validate_injection_action(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid_actions = {"block", "flag", "sanitize"}
        if v.lower() not in valid_actions:
            raise ValueError(f"injection_action must be one of {valid_actions}, got '{v}'")
        return v.lower()


class PolicyConfig(BaseModel):
    version: int = 1
    default_action: str = Field("deny", description="Action when no rule matches: 'allow' or 'deny'")
    limits: Optional[PolicyLimits] = None
    injection_screening: Optional[InjectionScreeningConfig] = Field(default_factory=InjectionScreeningConfig)
    rules: list[PolicyRule] = Field(default_factory=list)

    @field_validator("default_action")
    @classmethod
    def validate_default_action(cls, v: str) -> str:
        if v.lower() not in ("allow", "deny"):
            raise ValueError("default_action must be 'allow' or 'deny'")
        return v.lower()


class PolicyUploadRequest(BaseModel):
    yaml_content: str
    change_note: Optional[str] = "Updated policy configuration"


class PolicyVersionResponse(BaseModel):
    id: str
    version_number: int
    change_note: Optional[str]
    is_active: bool
    created_at: str
    created_by: Optional[str]


class PolicyRollbackRequest(BaseModel):
    target_version_number: int
