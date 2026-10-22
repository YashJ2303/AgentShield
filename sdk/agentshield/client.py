import time
import json
import hashlib
import logging
import httpx
from typing import Optional, Any
from dataclasses import dataclass
from .exceptions import GatewayUnreachableError


logger = logging.getLogger("agentshield.client")


def _normalize_numbers(obj: Any) -> Any:
    """Recursively normalize float integers (e.g. 250000.0 -> 250000) for stable JSON canonicalization."""
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    elif isinstance(obj, dict):
        return {str(k): _normalize_numbers(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_normalize_numbers(v) for v in obj]
    return obj


def compute_call_hash(run_id: str, tool_name: str, tool_args: Optional[dict[str, Any]]) -> str:
    """
    Computes a deterministic SHA-256 hash over canonical call attributes.
    Binds the approval strictly to (run_id, tool_name, tool_args).
    Ensures stable number canonicalization (250000 == 250000.0).
    """
    norm_args = _normalize_numbers(tool_args) if tool_args is not None else {}
    canonical_repr = {
        "run_id": str(run_id),
        "tool_name": str(tool_name),
        "tool_args": norm_args,
    }
    canonical_json = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@dataclass
class GatewayConfig:
    """
    Configuration for the AgentShield Gateway Client.
    fail_mode: 'fail_closed' (default: blocks tool calls if gateway server is unreachable)
               or 'fail_open' (logs warning and allows tool call).
    gateway_timeout: Short timeout (seconds) for synchronous tool policy checks.
    """
    server_url: str = "http://localhost:8000"
    api_key: str = "agentshield-dev-key-12345"
    admin_token: Optional[str] = None
    timeout: float = 10.0
    gateway_timeout: float = 2.0
    fail_mode: str = "fail_closed"
    check_policy: bool = True
    otlp_endpoint: Optional[str] = None
    http_client: Optional[Any] = None


class GatewayClient:
    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig()
        self.headers = {
            "X-API-Key": self.config.api_key,
            "Content-Type": "application/json",
        }
        if self.config.admin_token:
            self.headers["X-Admin-Token"] = self.config.admin_token
        self._buffered_spans: list[dict[str, Any]] = []

    def get_buffered_spans(self) -> list[dict[str, Any]]:
        """Return list of spans currently buffered due to unreachable server."""
        return list(self._buffered_spans)

    def get_buffered_spans_count(self) -> int:
        """Return count of currently buffered spans."""
        return len(self._buffered_spans)

    def flush_buffered_spans(self) -> Optional[dict[str, Any]]:
        """Attempt to flush any locally buffered spans to the server."""
        if not self._buffered_spans:
            return None
        spans_to_send = list(self._buffered_spans)
        self._buffered_spans = []
        return self.ingest_spans(spans_to_send)

    def check_tool(
        self,
        run_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        current_cost: float = 0.0,
        current_tokens: int = 0,
        current_steps: int = 0,
        elapsed_wall_time: float = 0.0,
    ) -> dict[str, Any]:
        """
        Check security policy before executing a tool.
        Sends running metrics (cost, tokens, steps, wall-clock time) to gateway.
        Raises GatewayUnreachableError if server is unreachable and fail_mode is fail_closed.
        """
        if not self.config.check_policy:
            return {"decision": "allow", "rule_id": "policy_check_disabled"}

        url = f"{self.config.server_url.rstrip('/')}/gateway/check"
        payload = {
            "run_id": run_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "current_running_cost": current_cost,
            "current_total_tokens": current_tokens,
            "current_step_count": current_steps,
            "elapsed_wall_time_seconds": elapsed_wall_time,
        }

        try:
            if self.config.http_client is not None:
                resp = self.config.http_client.post(url, headers=self.headers, json=payload)
            else:
                with httpx.Client(timeout=self.config.gateway_timeout) as client:
                    resp = client.post(url, headers=self.headers, json=payload)

            if resp.status_code == 200:
                return resp.json()
            else:
                raise Exception(f"Gateway check failed with HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            if self.config.fail_mode == "fail_closed":
                raise GatewayUnreachableError(f"AgentShield gateway unreachable ({str(e)}) - fail closed")
            else:
                logger.warning("AgentShield gateway unreachable (%s) - fail open", e)
                return {
                    "decision": "allow",
                    "rule_id": "fail_open_fallback",
                    "reason": "Gateway unreachable (fail_open mode)",
                }

    def screen_output(
        self,
        run_id: str,
        tool_name: str,
        tool_output: Any,
        span_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Screen tool output for prompt injection attacks via POST /gateway/screen-output.
        Defaults to fail-closed on network error (configurable via config.fail_mode).
        """
        url = f"{self.config.server_url.rstrip('/')}/gateway/screen-output"
        payload = {
            "run_id": run_id,
            "tool_name": tool_name,
            "tool_output": tool_output,
            "span_id": span_id,
        }
        try:
            if self.config.http_client is not None:
                resp = self.config.http_client.post(url, headers=self.headers, json=payload)
            else:
                with httpx.Client(timeout=self.config.gateway_timeout) as client:
                    resp = client.post(url, headers=self.headers, json=payload)

            if resp.status_code == 200:
                return resp.json()
            else:
                raise GatewayUnreachableError(f"Gateway returned status {resp.status_code}")
        except Exception as e:
            if getattr(self.config, "fail_mode", "fail_closed") == "fail_closed":
                raise GatewayUnreachableError(f"Prompt injection screening unreachable: {str(e)}") from e
            else:
                logger.warning("Gateway unreachable during output screening (%s) - fail open", e)
                return {
                    "action_taken": "allow",
                    "is_safe": True,
                    "injection_flag": False,
                    "sanitized_output": tool_output,
                    "matches": [],
                    "reason": "Gateway unreachable (fail_open fallback)",
                }

    def ingest_spans(
        self,
        spans: list[dict[str, Any]],
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        prompt_version: Optional[str] = None,
        model: Optional[str] = None,
        outcome: Optional[str] = None,
        tags: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Send batch of spans to server /ingest/spans.
        If server is unreachable or responds with error, buffers spans locally in-memory
        to be flushed on next available connection.
        """
        all_spans = list(self._buffered_spans) + list(spans)
        if not all_spans:
            return None

        url = f"{self.config.server_url.rstrip('/')}/ingest/spans"
        payload = {
            "session_id": session_id,
            "task_id": task_id,
            "prompt_version": prompt_version,
            "model": model,
            "outcome": outcome,
            "tags": tags or {},
            "spans": all_spans,
        }

        try:
            if self.config.http_client is not None:
                resp = self.config.http_client.post(url, headers=self.headers, json=payload)
            else:
                with httpx.Client(timeout=self.config.timeout) as client:
                    resp = client.post(url, headers=self.headers, json=payload)

            if resp.status_code == 200:
                # Successfully delivered all spans; clear local buffer
                self._buffered_spans = []
                return resp.json()
            else:
                logger.warning(
                    "AgentShield ingest failed [status %s]: %s; buffering %d spans",
                    resp.status_code,
                    resp.text,
                    len(all_spans),
                )
                self._buffered_spans = all_spans
        except Exception as e:
            logger.warning(
                "AgentShield server unreachable during span ingest: %s; buffering %d spans",
                e,
                len(all_spans),
            )
            self._buffered_spans = all_spans

        return None

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        """
        Retrieves current approval status from GET /approvals/{id}.
        Triggers read-time expiry check on the server.
        """
        url = f"{self.config.server_url.rstrip('/')}/approvals/{approval_id}"
        if self.config.http_client is not None:
            resp = self.config.http_client.get(url, headers=self.headers)
        else:
            with httpx.Client(timeout=self.config.gateway_timeout) as client:
                resp = client.get(url, headers=self.headers)

        if resp.status_code == 200:
            return resp.json()
        raise Exception(f"Failed to fetch approval {approval_id}: HTTP {resp.status_code} {resp.text}")

    def decide_approval(
        self,
        approval_id: str,
        decision: str,
        reason: Optional[str] = None,
        decided_by: Optional[str] = None,
        admin_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Decides an approval via POST /approvals/{id}/decision using X-Admin-Token.
        """
        url = f"{self.config.server_url.rstrip('/')}/approvals/{approval_id}/decision"
        token = admin_token or self.config.admin_token
        headers = dict(self.headers)
        if token:
            headers["X-Admin-Token"] = token

        payload = {
            "decision": decision,
            "reason": reason,
            "decided_by": decided_by,
        }

        if self.config.http_client is not None:
            resp = self.config.http_client.post(url, headers=headers, json=payload)
        else:
            with httpx.Client(timeout=self.config.gateway_timeout) as client:
                resp = client.post(url, headers=headers, json=payload)

        if resp.status_code == 200:
            return resp.json()
        raise Exception(f"Failed to decide approval: HTTP {resp.status_code} {resp.text}")

    def consume_approval(
        self,
        approval_id: str,
        run_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Atomically consumes an approved token via POST /approvals/{id}/consume.
        Enforces call_hash matching and single-use constraint.
        """
        url = f"{self.config.server_url.rstrip('/')}/approvals/{approval_id}/consume"
        payload = {
            "run_id": run_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
        }

        if self.config.http_client is not None:
            resp = self.config.http_client.post(url, headers=self.headers, json=payload)
        else:
            with httpx.Client(timeout=self.config.gateway_timeout) as client:
                resp = client.post(url, headers=self.headers, json=payload)

        if resp.status_code == 200:
            return resp.json()
        raise Exception(f"Failed to consume approval: HTTP {resp.status_code} {resp.text}")

    def poll_approval(
        self,
        approval_id: str,
        run_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        timeout_seconds: int = 60,
        poll_interval: float = 0.5,
    ) -> dict[str, Any]:
        """
        Polls GET /approvals/{id} until approved, rejected, or timed out.
        Enforces strict fail-closed semantics:
        - If server is unreachable mid-poll -> fail closed (decision='deny')
        - If timeout passes on server or client -> fail closed (decision='timed_out')
        - If approved -> atomically validates call_hash and consumes single-use token
        """
        start_time = time.monotonic()
        expected_call_hash = compute_call_hash(run_id, tool_name, tool_args)

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout_seconds:
                logger.warning("Approval %s timed out client-side after %.1fs (fail closed)", approval_id, elapsed)
                return {
                    "decision": "timed_out",
                    "reason": f"Client-side polling timed out after {timeout_seconds}s",
                    "approval_id": approval_id,
                }

            try:
                data = self.get_approval(approval_id)
            except Exception as e:
                logger.error("AgentShield server unreachable mid-poll for approval %s: %s (failing closed)", approval_id, e)
                if self.config.fail_mode == "fail_closed":
                    return {
                        "decision": "deny",
                        "reason": f"Gateway unreachable during approval polling: {e}",
                        "approval_id": approval_id,
                    }
                else:
                    return {
                        "decision": "allow",
                        "reason": "Gateway unreachable (fail_open mode)",
                        "approval_id": approval_id,
                    }

            current_status = data.get("status")
            if current_status == "approved":
                server_call_hash = data.get("call_hash")
                if server_call_hash != expected_call_hash:
                    logger.error("Approval call_hash mismatch! Server: %s, Expected: %s", server_call_hash, expected_call_hash)
                    return {
                        "decision": "deny",
                        "reason": "Approval call_hash mismatch: approval bound to different call arguments or run",
                        "approval_id": approval_id,
                    }

                # Atomically consume the single-use approval token
                try:
                    consume_res = self.consume_approval(
                        approval_id=approval_id,
                        run_id=run_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                    )
                    if consume_res.get("valid"):
                        return {
                            "decision": "approved",
                            "reason": data.get("decision_reason") or "Approved by human reviewer",
                            "approval_id": approval_id,
                            "decided_by": data.get("decided_by"),
                        }
                    else:
                        return {
                            "decision": "deny",
                            "reason": "Failed to consume single-use approval",
                            "approval_id": approval_id,
                        }
                except Exception as ce:
                    logger.error("Failed to consume approval %s: %s", approval_id, ce)
                    return {
                        "decision": "deny",
                        "reason": f"Approval consumption failed: {ce}",
                        "approval_id": approval_id,
                    }

            elif current_status == "rejected":
                return {
                    "decision": "rejected",
                    "reason": data.get("decision_reason") or "Rejected by human reviewer",
                    "approval_id": approval_id,
                    "decided_by": data.get("decided_by"),
                }

            elif current_status == "timed_out":
                return {
                    "decision": "timed_out",
                    "reason": data.get("decision_reason") or "Approval request timed out",
                    "approval_id": approval_id,
                }

            time.sleep(poll_interval)



_active_client: Optional[GatewayClient] = None


def get_active_client() -> GatewayClient:
    global _active_client
    if _active_client is None:
        _active_client = GatewayClient()
    return _active_client


def set_active_client(client: Optional[GatewayClient]) -> None:
    global _active_client
    _active_client = client
