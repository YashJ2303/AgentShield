"""Live external API integrations for the AgentShield gateway.

Every integration in this module follows one rule:

    **A simulated call must never be indistinguishable from a real one.**

Each function returns a payload carrying an ``execution_mode`` field taken from the
constants below, plus a human-readable ``source`` string. The gateway stores both on the
telemetry span, and the dashboard renders the mode as a coloured badge. Nothing here ever
fabricates a "success" without labelling itself as simulated.

Design notes
------------
* Network egress is gated behind :func:`network_allowed`, so demos, CI, and the test suite
  can run fully hermetic by setting ``LIVE_ALLOW_NETWORK=false``.
* Credentials are optional. An unkeyed provider degrades to a labelled simulation
  (``LIVE_SIMULATE_WHEN_UNKEYED``) or to ``MODE_UNCONFIGURED``.
* Outbound calls use ``requests`` only. No subprocess is ever spawned, which preserves the
  "zero host execution" invariant asserted by ``tests/test_no_host_execution.py``.
* PII redaction is applied *before* any outbound dispatch, not after.
"""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from server.app.config import settings
from server.app.services.pricing import calculate_cost, PRICING_AS_OF

# --------------------------------------------------------------------------------------
# Execution modes
# --------------------------------------------------------------------------------------

MODE_LIVE = "live"                  # a real network call was made and returned success
MODE_SIMULATED = "simulated"        # no credentials / network disabled; local simulation
MODE_OFFLINE = "offline"            # credentials present but the network was unreachable
MODE_UNCONFIGURED = "unconfigured"  # required credentials missing, call refused
MODE_BLOCKED = "blocked"            # refused before dispatch by policy / threat intel
MODE_ERROR = "error"                # the live call was attempted and failed

GITHUB_API_URL = "https://api.github.com/repos"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HACKERNEWS_URL = "https://hacker-news.firebaseio.com/v0"
URLSCAN_SEARCH_URL = "https://urlscan.io/api/v1/search/"

_GITHUB_UA = "AgentShield-Security-Gateway/1.0"

# Static, curated sample of phishing domains used when no live threat-intel source is
# reachable. Deliberately small and documented: this is a *demonstration denylist*, not a
# substitute for a maintained feed.
LOCAL_PHISH_SAMPLE: Tuple[str, ...] = (
    "paypa1-secure-verify.com",
    "account-recovery-login.net",
    "free-crypto-airdrop.xyz",
    "update-your-browser-now.info",
    "agentshield-security-audit.example",  # reserved for demos; never a real domain
)

# Stable pseudo-value source. Python's built-in hash() is salted per process, which would
# make simulated latency/tokens jitter across restarts; md5 keeps demos reproducible.
def _stable_int(seed: str, modulus: int) -> int:
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % modulus


@dataclass(frozen=True)
class ProviderStatus:
    """Availability report for one external provider."""

    id: str
    name: str
    category: str
    auth_required: bool
    configured: bool
    mode: str
    detail: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------------------
# Network gating
# --------------------------------------------------------------------------------------

_probe_cache: Dict[str, Any] = {}
_PROBE_TTL_SECONDS = 30.0


def network_allowed() -> bool:
    """Master switch for outbound egress, plus a cached reachability probe.

    Returns False when ``LIVE_ALLOW_NETWORK`` is off, or when outbound HTTPS has been
    observed to fail recently (so a sandboxed laptop keeps reporting ``offline`` instead of
    burning a timeout on every call).
    """
    if not settings.LIVE_ALLOW_NETWORK:
        return False
    now = time.time()
    cached = _probe_cache.get("reachable")
    if cached is not None:
        ok, ts = cached
        if now - ts < _PROBE_TTL_SECONDS:
            return ok
    return True


def _mark_unreachable() -> None:
    _probe_cache["reachable"] = (False, time.time())


def _mark_reachable() -> None:
    _probe_cache["reachable"] = (True, time.time())


def reset_network_probe_cache() -> None:
    """Test hook: forget the cached reachability probe."""
    _probe_cache.clear()


def _http_request(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Any] = None,
    form_body: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[int], Optional[Any], Optional[str]]:
    """Single outbound HTTP helper.

    Returns ``(status_code, parsed_json_or_text, error)``. Errors are returned, never
    raised, so callers can map them onto a labelled payload without crashing the gateway.
    """
    try:
        resp = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            data=form_body,
            timeout=timeout or settings.LIVE_HTTP_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - boundary with the public internet
        _mark_unreachable()
        return None, None, f"{type(exc).__name__}: {exc}"

    _mark_reachable()
    body: Any
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return resp.status_code, body, None


# --------------------------------------------------------------------------------------
# Provider registry
# --------------------------------------------------------------------------------------

def _llm_provider_for_model(model: str) -> Optional[str]:
    lowered = (model or "").lower()
    if "gemini" in lowered:
        return "gemini"
    if lowered.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")):
        return "openai"
    return None


def provider_statuses() -> List[ProviderStatus]:
    """Report, for every external provider, whether a live call is actually possible.

    This is the honesty layer behind the dashboard: an operator can see at a glance which
    cards are backed by a real API key and which are simulations.
    """
    online = network_allowed()
    statuses: List[ProviderStatus] = []

    def _mode(auth_required: bool, configured: bool) -> str:
        if not configured:
            return MODE_UNCONFIGURED if auth_required else (MODE_LIVE if online else MODE_OFFLINE)
        return MODE_LIVE if online else MODE_OFFLINE

    statuses.append(
        ProviderStatus(
            id="github",
            name="GitHub Public REST API",
            category="Public API (Zero-Auth)",
            auth_required=False,
            configured=True,
            mode=_mode(False, True),
            detail="No credentials required. Unauthenticated quota is 60 requests/hour per IP.",
        )
    )
    statuses.append(
        ProviderStatus(
            id="open_meteo",
            name="Open-Meteo Forecast API",
            category="Public API (Zero-Auth)",
            auth_required=False,
            configured=True,
            mode=_mode(False, True),
            detail="No credentials required. Live current-weather readings.",
        )
    )
    statuses.append(
        ProviderStatus(
            id="hackernews",
            name="Hacker News Firebase API",
            category="Public API (Zero-Auth)",
            auth_required=False,
            configured=True,
            mode=_mode(False, True),
            detail="No credentials required. Live front-page story fetch.",
        )
    )
    statuses.append(
        ProviderStatus(
            id="urlscan",
            name="urlscan.io Threat Intelligence",
            category="Security / Threat Intel",
            auth_required=False,
            configured=settings.URLSCAN_API_KEY is not None,
            mode=_mode(False, settings.URLSCAN_API_KEY is not None),
            detail=(
                "Public read-only search endpoint; an API key raises the rate limit."
                if settings.URLSCAN_API_KEY
                else "Running against the unauthenticated read-only search endpoint."
            ),
        )
    )
    statuses.append(
        ProviderStatus(
            id="stripe",
            name="Stripe Payment Intents",
            category="Enterprise Tool API",
            auth_required=True,
            configured=settings.STRIPE_API_KEY is not None,
            mode=_mode(True, settings.STRIPE_API_KEY is not None),
            detail="Requires STRIPE_API_KEY. Falls back to a labelled payment simulator.",
        )
    )
    statuses.append(
        ProviderStatus(
            id="sendgrid",
            name="SendGrid Transactional Email",
            category="Communication API",
            auth_required=True,
            configured=settings.SENDGRID_API_KEY is not None,
            mode=_mode(True, settings.SENDGRID_API_KEY is not None),
            detail="Requires SENDGRID_API_KEY. Payload is PII-redacted before dispatch.",
        )
    )
    statuses.append(
        ProviderStatus(
            id="slack",
            name="Slack Bot Messaging",
            category="Communication API",
            auth_required=True,
            configured=settings.SLACK_BOT_TOKEN is not None,
            mode=_mode(True, settings.SLACK_BOT_TOKEN is not None),
            detail="Requires SLACK_BOT_TOKEN. Payload is PII-redacted before dispatch.",
        )
    )
    statuses.append(
        ProviderStatus(
            id="twilio",
            name="Twilio SMS",
            category="Communication API",
            auth_required=True,
            configured=bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN),
            mode=_mode(True, bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)),
            detail="Requires TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN. Redacted before dispatch.",
        )
    )
    statuses.append(
        ProviderStatus(
            id="openai",
            name="OpenAI Chat & Moderation",
            category="LLM Provider",
            auth_required=True,
            configured=settings.OPENAI_API_KEY is not None,
            mode=_mode(True, settings.OPENAI_API_KEY is not None),
            detail=f"Requires OPENAI_API_KEY. Base URL: {settings.OPENAI_BASE_URL}",
        )
    )
    statuses.append(
        ProviderStatus(
            id="gemini",
            name="Google Gemini",
            category="LLM Provider",
            auth_required=True,
            configured=settings.GEMINI_API_KEY is not None,
            mode=_mode(True, settings.GEMINI_API_KEY is not None),
            detail=f"Requires GEMINI_API_KEY. Pricing table as of {PRICING_AS_OF}.",
        )
    )
    return statuses


def providers_payload() -> Dict[str, Any]:
    return {
        "providers": [p.as_dict() for p in provider_statuses()],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


# --------------------------------------------------------------------------------------
# Public zero-auth APIs (GitHub / Open-Meteo / Hacker News)
# --------------------------------------------------------------------------------------

def fetch_github_repo(owner: str = "pallets", repo: str = "flask") -> Dict[str, Any]:
    """Fetch live repository metadata from the public GitHub REST API."""
    url = f"{GITHUB_API_URL}/{owner}/{repo}"
    t0 = time.perf_counter()
    if network_allowed():
        status, body, err = _http_request("GET", url, headers={"User-Agent": _GITHUB_UA})
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if err is None and status == 200 and isinstance(body, dict):
            return {
                "source": "GitHub Public REST API",
                "execution_mode": MODE_LIVE,
                "full_name": body.get("full_name"),
                "description": body.get("description"),
                "stargazers_count": body.get("stargazers_count"),
                "forks_count": body.get("forks_count"),
                "open_issues_count": body.get("open_issues_count"),
                "watchers_count": body.get("watchers_count"),
                "language": body.get("language"),
                "license": (body.get("license") or {}).get("name", "None"),
                "default_branch": body.get("default_branch"),
                "pushed_at": body.get("pushed_at"),
                "http_status": status,
                "latency_ms": latency_ms,
                "status": "success",
            }
        return _github_failure(owner, repo, status, err, latency_ms)
    return {
        "source": "GitHub Public REST API (offline snapshot)",
        "execution_mode": MODE_OFFLINE,
        "full_name": f"{owner}/{repo}",
        "description": "Network egress disabled via LIVE_ALLOW_NETWORK.",
        "stargazers_count": 68400,
        "language": "Python",
        "license": "BSD-3-Clause",
        "latency_ms": 0.0,
        "status": "offline_snapshot",
    }


def _github_failure(owner: str, repo: str, status: Optional[int], err: Optional[str], latency_ms: float) -> Dict[str, Any]:
    """Uniform failure payload for GitHub. Kept as a helper so the live and error branches
    cannot drift apart in field names (a past bug hid non-200 responses from callers)."""
    return {
        "source": "GitHub Public REST API (cached fallback)",
        "execution_mode": MODE_ERROR if err else MODE_OFFLINE,
        "full_name": f"{owner}/{repo}",
        "description": "Snapshot returned because the live GitHub call did not succeed.",
        "stargazers_count": 68420,
        "forks_count": 16210,
        "open_issues_count": 14,
        "language": "Python",
        "license": "BSD-3-Clause",
        "default_branch": "main",
        "http_status": status,
        "latency_ms": latency_ms,
        "status": "cached_fallback",
        "detail": err or f"HTTP {status}",
    }


def fetch_open_meteo_weather(
    city: str = "Tokyo", lat: float = 35.6895, lon: float = 139.6917
) -> Dict[str, Any]:
    """Fetch live weather from the Open-Meteo API (zero authentication required)."""
    params = {"latitude": lat, "longitude": lon, "current_weather": "true"}
    t0 = time.perf_counter()
    if network_allowed():
        status, body, err = _http_request("GET", OPEN_METEO_URL, params=params)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if err is None and status == 200 and isinstance(body, dict):
            current = body.get("current_weather", {}) or {}
            return {
                "source": "Open-Meteo Forecast API",
                "execution_mode": MODE_LIVE,
                "city": city,
                "coordinates": f"{lat}, {lon}",
                "temperature_celsius": current.get("temperature"),
                "windspeed_kmh": current.get("windspeed"),
                "winddirection": current.get("winddirection"),
                "weathercode": current.get("weathercode"),
                "is_day": current.get("is_day"),
                "time": current.get("time"),
                "http_status": status,
                "latency_ms": latency_ms,
                "status": "live",
            }
        return {
            "source": "Open-Meteo Forecast API (fallback)",
            "execution_mode": MODE_ERROR if err else MODE_OFFLINE,
            "city": city,
            "temperature_celsius": None,
            "windspeed_kmh": None,
            "http_status": status,
            "latency_ms": latency_ms,
            "status": "fallback",
            "detail": err or f"HTTP {status}",
        }
    return {
        "source": "Open-Meteo Forecast API (offline snapshot)",
        "execution_mode": MODE_OFFLINE,
        "city": city,
        "temperature_celsius": 19.0,
        "windspeed_kmh": 10.0,
        "latency_ms": 0.0,
        "status": "snapshot",
    }


def fetch_hackernews_top(count: int = 2) -> Dict[str, Any]:
    """Fetch live top trending stories from the Hacker News Firebase API."""
    count = max(1, min(int(count), 10))
    t0 = time.perf_counter()
    if network_allowed():
        status, body, err = _http_request(
            "GET",
            f"{HACKERNEWS_URL}/topstories.json",
            # Firebase rejects limitToFirst without orderBy, so both must be sent.
            params={"orderBy": '"$key"', "limitToFirst": count},
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if err is None and status == 200 and isinstance(body, list):
            stories: List[Dict[str, Any]] = []
            for sid in body[:count]:
                istatus, item, ierr = _http_request("GET", f"{HACKERNEWS_URL}/item/{sid}.json")
                if ierr is None and istatus == 200 and isinstance(item, dict):
                    stories.append(
                        {
                            "id": sid,
                            "title": item.get("title"),
                            "by": item.get("by"),
                            "score": item.get("score"),
                            "descendants": item.get("descendants"),
                            "url": item.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                        }
                    )
            return {
                "source": "Hacker News Firebase API",
                "execution_mode": MODE_LIVE,
                "stories_count": len(stories),
                "stories": stories,
                "http_status": status,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "status": "live",
            }
        return {
            "source": "Hacker News Firebase API (fallback)",
            "execution_mode": MODE_ERROR if err else MODE_OFFLINE,
            "stories_count": 0,
            "stories": [],
            "http_status": status,
            "latency_ms": latency_ms,
            "status": "fallback",
            "detail": err or f"HTTP {status}",
        }
    return {
        "source": "Hacker News Firebase API (offline snapshot)",
        "execution_mode": MODE_OFFLINE,
        "stories_count": 1,
        "stories": [
            {
                "id": 41200000,
                "title": "Show HN: AgentShield AI Governance Gateway (offline snapshot)",
                "by": "agentshield",
                "score": 0,
                "url": "https://example.invalid",
            }
        ],
        "latency_ms": 0.0,
        "status": "snapshot",
    }


# --------------------------------------------------------------------------------------
# Payments (Stripe)
# --------------------------------------------------------------------------------------

def _payment_tier(amount: float) -> str:
    if amount >= 500.0:
        return "high_risk"
    if amount >= 100.0:
        return "elevated"
    return "standard"


def create_payment_intent(
    amount: float,
    recipient: str,
    currency: str = "USD",
    vendor_verified: bool = False,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a payment. Uses the live Stripe API when STRIPE_API_KEY is configured,
    otherwise runs a clearly-labelled simulator.

    The Stripe ``client_secret`` is deliberately never returned: it is a bearer credential
    for confirming the payment, and echoing it into telemetry would leak it to every
    dashboard viewer.
    """
    currency = (currency or "USD").upper()
    tier = _payment_tier(amount)
    t0 = time.perf_counter()

    if settings.STRIPE_API_KEY and network_allowed():
        try:
            amount_minor = int(round(float(amount) * 100))
        except (TypeError, ValueError):
            amount_minor = 0
        status, body, err = _http_request(
            "POST",
            f"{settings.STRIPE_API_BASE}/payment_intents",
            headers={"Authorization": f"Bearer {settings.STRIPE_API_KEY}"},
            form_body={
                "amount": amount_minor,
                "currency": currency.lower(),
                "description": description or f"AgentShield demo payment to {recipient}",
                "metadata[recipient]": recipient,
                "metadata[agent_shield_tier]": tier,
                "metadata[vendor_verified]": str(bool(vendor_verified)).lower(),
            },
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if err is None and status == 200 and isinstance(body, dict):
            return {
                "source": "Stripe Payment Intents API",
                "execution_mode": MODE_LIVE,
                "gateway": "Stripe Payment Intent API",
                "amount": float(amount),
                "amount_minor": amount_minor,
                "currency": currency,
                "recipient": recipient,
                "vendor_verified": bool(vendor_verified),
                "tier": tier,
                "transaction_id": body.get("id"),
                "status": body.get("status", "requires_payment_method"),
                "http_status": status,
                "latency_ms": latency_ms,
            }
        return {
            "source": "Stripe Payment Intents API (failed)",
            "execution_mode": MODE_ERROR,
            "gateway": "Stripe Payment Intent API",
            "amount": float(amount),
            "currency": currency,
            "recipient": recipient,
            "tier": tier,
            "transaction_id": None,
            "status": "failed",
            "http_status": status,
            "latency_ms": latency_ms,
            "detail": err or (body.get("error", {}).get("message") if isinstance(body, dict) else f"HTTP {status}"),
        }

    # Simulator path
    seed = f"{amount}:{currency}:{recipient}"
    tx_id = f"ch_sim_{_stable_int(seed, 10**8):08d}"
    return {
        "source": "Stripe simulator (no STRIPE_API_KEY configured)",
        "execution_mode": MODE_SIMULATED,
        "gateway": "Stripe Payment Intent API",
        "amount": float(amount),
        "currency": currency,
        "recipient": recipient,
        "vendor_verified": bool(vendor_verified),
        "tier": tier,
        "transaction_id": tx_id,
        "status": "processed" if tier == "standard" else "flagged_high_risk",
        "latency_ms": round(8.0 + _stable_int(seed, 20), 2),
        "note": "No funds moved. This call never reached Stripe.",
    }


# Backwards-compatible name used by earlier demo code and scenarios.
def process_stripe_payment(amount: float, recipient: str, currency: str = "USD") -> Dict[str, Any]:
    return create_payment_intent(amount, recipient, currency)


# --------------------------------------------------------------------------------------
# Communication dispatch (SendGrid / Slack / Twilio)
# --------------------------------------------------------------------------------------

def dispatch_communication(
    channel: str,
    recipient: str,
    subject: str = "",
    body: str = "",
    message: str = "",
) -> Dict[str, Any]:
    """Dispatch an outbound message, redacting PII first.

    Redaction is unconditional and happens *before* the provider call, so a live dispatch
    genuinely cannot leak the email/phone/SSN that was in the agent's original draft.
    """
    from server.app.services.redaction import redact_text

    channel = (channel or "").lower()
    text = body or message or ""
    redacted_subject, sub_redactions = redact_text(subject or "")
    redacted_body, body_redactions = redact_text(text)
    redactions = sub_redactions + body_redactions

    base = {
        "channel": channel,
        "recipient": recipient,
        "subject": redacted_subject,
        "redacted_body": redacted_body,
        "redactions_applied": redactions,
        "original_body_had_pii": bool(redactions),
    }
    t0 = time.perf_counter()

    if channel == "email":
        if settings.SENDGRID_API_KEY and network_allowed():
            status, resp_body, err = _http_request(
                "POST",
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json_body={
                    "personalizations": [{"to": [{"email": recipient}]}],
                    "from": {"email": "noreply@agentshield.example"},
                    "subject": redacted_subject or "(no subject)",
                    "content": [{"type": "text/plain", "value": redacted_body}],
                },
            )
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            delivered = err is None and status in (200, 202)
            return {
                **base,
                "source": "SendGrid v3 Mail Send API",
                "execution_mode": MODE_LIVE if delivered else MODE_ERROR,
                "dispatched": delivered,
                "provider_message_id": (resp_body or {}).get("x-message-id") if isinstance(resp_body, dict) else None,
                "http_status": status,
                "latency_ms": latency_ms,
                "status": "sent" if delivered else "failed",
                "detail": None if delivered else (err or f"HTTP {status}"),
            }
        return {
            **base,
            "source": "SendGrid simulator (no SENDGRID_API_KEY configured)",
            "execution_mode": MODE_SIMULATED,
            "dispatched": False,
            "provider_message_id": f"sim_msg_{_stable_int(recipient + redacted_body, 10**6):06d}",
            "latency_ms": round(5.0 + _stable_int(recipient, 12), 2),
            "status": "simulated_not_sent",
            "note": "No email was transmitted. Redaction still ran against the real payload.",
        }

    if channel == "slack":
        if settings.SLACK_BOT_TOKEN and network_allowed():
            status, resp_body, err = _http_request(
                "POST",
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json_body={"channel": recipient, "text": redacted_body},
            )
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            ok = err is None and status == 200 and isinstance(resp_body, dict) and resp_body.get("ok") is True
            return {
                **base,
                "source": "Slack Web API (chat.postMessage)",
                "execution_mode": MODE_LIVE if ok else MODE_ERROR,
                "dispatched": ok,
                "ts": (resp_body or {}).get("ts") if isinstance(resp_body, dict) else None,
                "http_status": status,
                "latency_ms": latency_ms,
                "status": "sent" if ok else "failed",
                "detail": None if ok else (err or (resp_body or {}).get("error", f"HTTP {status}") if isinstance(resp_body, dict) else f"HTTP {status}"),
            }
        return {
            **base,
            "source": "Slack simulator (no SLACK_BOT_TOKEN configured)",
            "execution_mode": MODE_SIMULATED,
            "dispatched": False,
            "ts": f"sim.{_stable_int(recipient + redacted_body, 10**9)}",
            "latency_ms": round(4.0 + _stable_int(recipient, 9), 2),
            "status": "simulated_not_sent",
            "note": "No Slack message was transmitted. Redaction still ran against the real payload.",
        }

    if channel == "sms":
        sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
        if sid and token and network_allowed():
            status, resp_body, err = _http_request(
                "POST",
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                headers={
                    "Authorization": "Basic "
                    + base64.b64encode(f"{sid}:{token}".encode()).decode()
                },
                form_body={"To": recipient, "From": "+15005550006", "Body": redacted_body},
            )
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            delivered = err is None and status == 201 and isinstance(resp_body, dict)
            return {
                **base,
                "source": "Twilio Messages API",
                "execution_mode": MODE_LIVE if delivered else MODE_ERROR,
                "dispatched": delivered,
                "provider_message_id": (resp_body or {}).get("sid") if isinstance(resp_body, dict) else None,
                "http_status": status,
                "latency_ms": latency_ms,
                "status": "sent" if delivered else "failed",
                "detail": None if delivered else (err or f"HTTP {status}"),
            }
        return {
            **base,
            "source": "Twilio simulator (credentials not configured)",
            "execution_mode": MODE_SIMULATED,
            "dispatched": False,
            "provider_message_id": f"SMsim{_stable_int(recipient + redacted_body, 10**10):010d}",
            "latency_ms": round(6.0 + _stable_int(recipient, 11), 2),
            "status": "simulated_not_sent",
            "note": "No SMS was transmitted. Redaction still ran against the real payload.",
        }

    return {
        **base,
        "source": "unsupported channel",
        "execution_mode": MODE_ERROR,
        "dispatched": False,
        "status": "unsupported_channel",
        "detail": f"Unknown channel '{channel}'. Supported: email, slack, sms.",
    }


# --------------------------------------------------------------------------------------
# Threat intelligence (urlscan.io + local denylist) and content moderation
# --------------------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    candidate = url if "://" in url else f"https://{url}"
    try:
        return (urlparse(candidate).hostname or "").lower().lstrip(".")
    except Exception:
        return ""


def check_url_reputation(url: str) -> Dict[str, Any]:
    """Reputation-check a URL before an agent crawls it.

    Combines a curated local denylist (always available, offline) with urlscan.io search
    results (live). Sources consulted are listed explicitly in ``sources_consulted`` so a
    reviewer can tell how much of the verdict was real.
    """
    domain = _extract_domain(url)
    t0 = time.perf_counter()
    sources: List[str] = ["local_denylist_sample"]
    matches: List[Dict[str, str]] = []

    for bad in LOCAL_PHISH_SAMPLE:
        if domain == bad or domain.endswith("." + bad):
            matches.append({"source": "local_denylist_sample", "domain": domain, "reason": "domain in curated sample denylist"})

    verdict = "malicious" if matches else "unknown"
    live_checked = False

    if domain and network_allowed():
        status, body, err = _http_request(
            "GET",
            URLSCAN_SEARCH_URL,
            params={"q": f"domain:{domain}", "size": 1},
            headers={"User-Agent": _GITHUB_UA},
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if err is None and status == 200 and isinstance(body, dict):
            live_checked = True
            sources.append("urlscan.io")
            results = body.get("results") or []
            if results:
                overall = ((results[0].get("verdicts") or {}).get("overall")) or {}
                score = overall.get("score")
                if overall.get("malicious") is True:
                    matches.append(
                        {
                            "source": "urlscan.io",
                            "domain": domain,
                            "reason": f"urlscan flagged malicious (score={score})",
                        }
                    )
                    verdict = "malicious"
                elif verdict == "unknown":
                    verdict = "known"
            elif verdict == "unknown":
                verdict = "unseen"
        elif not live_checked and verdict == "unknown":
            verdict = "unknown"

    return {
        "url": url,
        "domain": domain,
        "verdict": verdict,
        "execution_mode": MODE_LIVE if live_checked else MODE_SIMULATED,
        "sources_consulted": sources,
        "matches": matches,
        "should_block": bool(matches),
        "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "note": (
            "Live urlscan.io verdict plus curated sample denylist."
            if live_checked
            else "Live threat intel unreachable; only the curated sample denylist was consulted."
        ),
    }


_LOCAL_MODERATION_CATEGORIES = {
    "harassment": ("kill yourself", "idiot", "worthless", "hate you"),
    "violence": ("bomb", "shoot", "attack", "murder", "weapon"),
    "sexual": ("explicit sexual", "nsfw"),
    "self_harm": ("hurt myself", "end my life", "suicide"),
    "illicit": ("buy drugs", "stolen credit card", "hack into", "ransomware"),
}


def moderate_content(text: str) -> Dict[str, Any]:
    """Screen text for policy-violating categories.

    Uses the live OpenAI Moderation endpoint when OPENAI_API_KEY is configured; otherwise
    falls back to a deterministic keyword classifier that is explicitly reported as
    ``local_heuristic``. The heuristic is a demo aid, not a safety guarantee.
    """
    lowered = (text or "").lower()
    t0 = time.perf_counter()

    if settings.OPENAI_API_KEY and network_allowed():
        status, body, err = _http_request(
            "POST",
            f"{settings.OPENAI_BASE_URL}/moderations",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
            json_body={"model": "omni-moderation-latest", "input": text},
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if err is None and status == 200 and isinstance(body, dict) and body.get("results"):
            entry = body["results"][0]
            categories = entry.get("categories") or {}
            scores = entry.get("category_scores") or {}
            flagged = bool(entry.get("flagged"))
            return {
                "source": "OpenAI Moderation API (omni-moderation-latest)",
                "execution_mode": MODE_LIVE,
                "flagged": flagged,
                "categories": categories,
                "category_scores": scores,
                "http_status": status,
                "latency_ms": latency_ms,
            }
        return {
            "source": "OpenAI Moderation API (failed)",
            "execution_mode": MODE_ERROR,
            "flagged": False,
            "categories": {},
            "http_status": status,
            "latency_ms": latency_ms,
            "detail": err or f"HTTP {status}",
        }

    categories: Dict[str, bool] = {}
    scores: Dict[str, float] = {}
    for cat, needles in _LOCAL_MODERATION_CATEGORIES.items():
        hits = sum(1 for n in needles if n in lowered)
        categories[cat] = hits > 0
        scores[cat] = min(1.0, hits / max(1, len(needles)))
    return {
        "source": "Local heuristic classifier (no OPENAI_API_KEY configured)",
        "execution_mode": MODE_SIMULATED,
        "flagged": any(categories.values()),
        "categories": categories,
        "category_scores": scores,
        "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "note": "Keyword heuristic for demonstration only. Not a production moderation safety net.",
    }


# --------------------------------------------------------------------------------------
# LLM inference proxy (Gemini / OpenAI)
# --------------------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate used only for labelled simulations.

    ~4 characters per token is a deliberately crude heuristic; it is never presented as a
    provider-reported count because ``execution_mode`` will be ``simulated``.
    """
    return max(1, int(len(text or "") / 4))


def execute_llm_inference(
    prompt: str,
    model: str = "gemini-2.5-flash",
    provider: Optional[str] = None,
    system_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one LLM completion through the gateway's provider proxy.

    Live calls report provider-reported token counts and measured wall-clock latency; cost
    is computed from the pricing table. When the provider is unkeyed, a labelled
    simulation returns estimated tokens so the dashboard cost model stays demonstrable.
    """
    provider = (provider or _llm_provider_for_model(model) or "").lower()
    t0 = time.perf_counter()

    if provider == "gemini":
        if settings.GEMINI_API_KEY and network_allowed():
            payload: Dict[str, Any] = {"contents": [{"parts": [{"text": prompt}]}]}
            if system_instruction:
                payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            status, body, err = _http_request(
                "POST",
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent",
                headers={"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"},
                json_body=payload,
            )
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if err is None and status == 200 and isinstance(body, dict):
                candidates = body.get("candidates") or []
                text = ""
                if candidates:
                    parts = (candidates[0].get("content") or {}).get("parts") or []
                    text = "".join(p.get("text", "") for p in parts)
                usage = body.get("usageMetadata") or {}
                p_tok = int(usage.get("promptTokenCount") or _estimate_tokens(prompt))
                c_tok = int(usage.get("candidatesTokenCount") or _estimate_tokens(text))
                return {
                    "source": "Google Gemini API",
                    "provider": "gemini",
                    "execution_mode": MODE_LIVE,
                    "model": model,
                    "response": text.strip(),
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "total_tokens": p_tok + c_tok,
                    "latency_ms": latency_ms,
                    "cost_usd": calculate_cost(model, p_tok, c_tok),
                    "status": "success",
                    "http_status": status,
                }
            return {
                "source": "Google Gemini API (failed)",
                "provider": "gemini",
                "execution_mode": MODE_ERROR,
                "model": model,
                "response": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "cost_usd": None,
                "status": "failed",
                "http_status": status,
                "detail": err or (body.get("error", {}).get("message") if isinstance(body, dict) else f"HTTP {status}"),
            }

    elif provider == "openai":
        if settings.OPENAI_API_KEY and network_allowed():
            messages: List[Dict[str, str]] = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            status, body, err = _http_request(
                "POST",
                f"{settings.OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
                json_body={"model": model, "messages": messages},
            )
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if err is None and status == 200 and isinstance(body, dict):
                choices = body.get("choices") or []
                text = ""
                if choices:
                    text = ((choices[0].get("message") or {}).get("content")) or ""
                usage = body.get("usage") or {}
                p_tok = int(usage.get("prompt_tokens") or _estimate_tokens(prompt))
                c_tok = int(usage.get("completion_tokens") or _estimate_tokens(text))
                return {
                    "source": "OpenAI Chat Completions API",
                    "provider": "openai",
                    "execution_mode": MODE_LIVE,
                    "model": model,
                    "response": text.strip(),
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "total_tokens": p_tok + c_tok,
                    "latency_ms": latency_ms,
                    "cost_usd": calculate_cost(model, p_tok, c_tok),
                    "status": "success",
                    "http_status": status,
                }
            return {
                "source": "OpenAI Chat Completions API (failed)",
                "provider": "openai",
                "execution_mode": MODE_ERROR,
                "model": model,
                "response": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "cost_usd": None,
                "status": "failed",
                "http_status": status,
                "detail": err or (body.get("error", {}).get("message") if isinstance(body, dict) else f"HTTP {status}"),
            }

    # ---- Labelled simulation ---------------------------------------------------------
    seed = f"{provider}|{model}|{prompt}"
    p_tok = _estimate_tokens(prompt)
    reply = (
        f"[SIMULATED RESPONSE — no {provider or 'model'} credentials configured] "
        f"Echo of task: {prompt[:120]}{'...' if len(prompt) > 120 else ''}"
    )
    c_tok = _estimate_tokens(reply)
    latency = 90.0 + _stable_int(seed, 260)
    cost = calculate_cost(model, p_tok, c_tok)
    return {
        "source": f"{provider or 'LLM'} simulator (no API key configured)",
        "provider": provider or "unknown",
        "execution_mode": MODE_SIMULATED,
        "model": model,
        "response": reply,
        "prompt_tokens": p_tok,
        "completion_tokens": c_tok,
        "total_tokens": p_tok + c_tok,
        "latency_ms": latency,
        "cost_usd": cost,
        "status": "simulated",
        "note": (
            "Tokens and latency are estimates so the cost model stays demonstrable without "
            f"credentials. Pricing table as of {PRICING_AS_OF}."
        ),
    }


# Backwards-compatible wrapper used by existing scenario code.
def execute_gemini_inference(prompt: str, model: str = "gemini-1.5-flash") -> Dict[str, Any]:
    return execute_llm_inference(prompt, model=model, provider="gemini")


def compare_llm_models(prompt: str, models: List[str]) -> Dict[str, Any]:
    """Run the same prompt against several models and summarise cost/latency differences."""
    results = [execute_llm_inference(prompt, model=m) for m in models]

    def _cost(r: Dict[str, Any]) -> float:
        c = r.get("cost_usd")
        return float(c) if isinstance(c, (int, float)) else float("inf")

    def _lat(r: Dict[str, Any]) -> float:
        l = r.get("latency_ms")
        return float(l) if isinstance(l, (int, float)) else float("inf")

    summary: Dict[str, Any] = {}
    if results:
        priced = [r for r in results if isinstance(r.get("cost_usd"), (int, float))]
        cheapest = min(priced, key=_cost) if priced else None
        fastest = min(results, key=_lat)
        summary = {
            "cheapest_model": cheapest.get("model") if cheapest else None,
            "faster_model": fastest.get("model"),
            "cost_delta_usd": (
                round(max(_cost(r) for r in priced) - min(_cost(r) for r in priced), 8) if len(priced) >= 2 else None
            ),
            "latency_delta_ms": (
                round(max(_lat(r) for r in results) - min(_lat(r) for r in results), 2) if len(results) >= 2 else None
            ),
            "all_simulated": all(r.get("execution_mode") == MODE_SIMULATED for r in results),
        }
    return {"prompt": prompt, "results": results, "comparison": summary}


__all__ = [
    "MODE_LIVE",
    "MODE_SIMULATED",
    "MODE_OFFLINE",
    "MODE_UNCONFIGURED",
    "MODE_BLOCKED",
    "MODE_ERROR",
    "ProviderStatus",
    "provider_statuses",
    "providers_payload",
    "network_allowed",
    "reset_network_probe_cache",
    "fetch_github_repo",
    "fetch_open_meteo_weather",
    "fetch_hackernews_top",
    "create_payment_intent",
    "process_stripe_payment",
    "dispatch_communication",
    "check_url_reputation",
    "moderate_content",
    "execute_llm_inference",
    "execute_gemini_inference",
    "compare_llm_models",
    "LOCAL_PHISH_SAMPLE",
]
