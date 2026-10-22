"""Real-world tool integrations for AgentShield Live Demos and Sandbox.

This module is the legacy import surface. The implementations now live in
``server.app.services.live_integrations``, which adds explicit execution-mode labelling
(``live`` vs ``simulated`` vs ``offline``), provider availability reporting, threat
intelligence, and multi-provider LLM inference.

The functions here are thin re-exports so that existing callers
(``server.app.api.v1.live_agent``, ``scripts/live_demo.py``) keep working unchanged while
sharing a single, honest implementation.
"""

from server.app.services.live_integrations import (
    GITHUB_API_URL,
    HACKERNEWS_URL,
    OPEN_METEO_URL,
    create_payment_intent,
    execute_gemini_inference,
    execute_llm_inference,
    fetch_github_repo,
    fetch_hackernews_top,
    fetch_open_meteo_weather,
    process_stripe_payment,
    provider_statuses,
)

__all__ = [
    "GITHUB_API_URL",
    "OPEN_METEO_URL",
    "HACKERNEWS_URL",
    "fetch_github_repo",
    "fetch_open_meteo_weather",
    "fetch_hackernews_top",
    "process_stripe_payment",
    "create_payment_intent",
    "execute_gemini_inference",
    "execute_llm_inference",
    "provider_statuses",
]
