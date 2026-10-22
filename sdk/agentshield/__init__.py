import uuid
import contextlib
from typing import Optional, Any
from .context import (
    RunContext,
    set_current_run,
    get_current_run,
)
from .decorators import trace_model_call, trace_tool_call
from .client import (
    GatewayClient,
    GatewayConfig,
    get_active_client,
    set_active_client,
)
from .otlp_exporter import init_otlp, flush_otel
from .exceptions import (
    AgentShieldError,
    PolicyViolationError,
    GatewayUnreachableError,
)



def init(
    server_url: str = "http://localhost:8000",
    api_key: str = "agentshield-dev-key-12345",
    admin_token: Optional[str] = None,
    otlp_endpoint: Optional[str] = None,
    service_name: str = "agentshield-agent",
    fail_mode: str = "fail_closed",
    check_policy: bool = True,
    gateway_timeout: float = 2.0,
    http_client: Optional[Any] = None,
    timeout: float = 10.0,
) -> GatewayClient:
    """
    Initialize AgentShield SDK with server, fail_mode, and optional OTLP endpoints.
    fail_mode: 'fail_closed' (default) blocks tool execution if gateway server is unreachable.
               'fail_open' logs warning and permits execution.
    check_policy: whether tool calls query the gateway policy before execution.
    """
    config = GatewayConfig(
        server_url=server_url,
        api_key=api_key,
        admin_token=admin_token,
        otlp_endpoint=otlp_endpoint,
        fail_mode=fail_mode,
        check_policy=check_policy,
        gateway_timeout=gateway_timeout,
        http_client=http_client,
        timeout=timeout,
    )

    client = GatewayClient(config)
    set_active_client(client)
    init_otlp(service_name=service_name, otlp_endpoint=otlp_endpoint)
    return client


def get_client() -> GatewayClient:
    return get_active_client()


def set_client(client: Optional[GatewayClient]):
    set_active_client(client)

    _default_client = client


@contextlib.contextmanager
def run(
    task_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    tags: Optional[dict[str, Any]] = None,
    run_id: Optional[str] = None,
):
    """
    Context manager for an agent execution run.
    Captures all model and tool calls within the block, records latency,
    and automatically ingests the trace upon completion.
    """
    actual_run_id = run_id or str(uuid.uuid4())
    run_ctx = RunContext(
        run_id=actual_run_id,
        session_id=session_id,
        task_id=task_id,
        prompt_version=prompt_version,
        model=model,
        tags=tags or {},
    )
    token = set_current_run(run_ctx)
    outcome = "success"

    try:
        yield run_ctx
    except PolicyViolationError:
        outcome = "blocked"
        raise
    except Exception:
        outcome = "failure"
        raise
    finally:
        set_current_run(None)
        client = get_client()
        # Ingest collected spans to server
        if run_ctx.spans:
            client.ingest_spans(
                spans=run_ctx.spans,
                session_id=run_ctx.session_id,
                task_id=run_ctx.task_id,
                prompt_version=run_ctx.prompt_version,
                model=run_ctx.model,
                outcome=outcome,
                tags=run_ctx.tags,
            )
        flush_otel()


def get_current_run_id() -> Optional[str]:
    ctx = get_current_run()
    return ctx.run_id if ctx else None


def get_current_session_id() -> Optional[str]:
    ctx = get_current_run()
    return ctx.session_id if ctx else None


__all__ = [
    "init",
    "run",
    "trace_model_call",
    "trace_tool_call",
    "get_current_run_id",
    "get_current_session_id",
    "get_client",
    "set_client",
    "AgentShieldError",
    "PolicyViolationError",
    "GatewayUnreachableError",
]
