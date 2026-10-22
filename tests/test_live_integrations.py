"""Tests for live external API integrations.

These tests never touch the real network: LIVE_ALLOW_NETWORK is forced off so every
provider reports its simulated/offline mode. That is also the property under test — the
integrations must label simulation honestly instead of fabricating "live" success.
"""

import pytest

from server.app.config import settings
from server.app.services import live_integrations as li


@pytest.fixture(autouse=True)
def _hermetic_network(monkeypatch):
    """Force hermetic mode for every test in this module."""
    monkeypatch.setattr(settings, "LIVE_ALLOW_NETWORK", False)
    for attr in ("GEMINI_API_KEY", "OPENAI_API_KEY", "STRIPE_API_KEY", "SENDGRID_API_KEY",
                 "SLACK_BOT_TOKEN", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "URLSCAN_API_KEY"):
        monkeypatch.setattr(settings, attr, None)
    li.reset_network_probe_cache()
    yield
    li.reset_network_probe_cache()


# --------------------------------------------------------------------------------------
# Provider status reporting
# --------------------------------------------------------------------------------------

def test_provider_statuses_cover_all_integration_families():
    statuses = {p.id: p for p in li.provider_statuses()}
    for pid in ("github", "open_meteo", "hackernews", "urlscan", "stripe",
                "sendgrid", "slack", "twilio", "openai", "gemini"):
        assert pid in statuses, f"missing provider status for {pid}"


def test_unkeyed_providers_report_unconfigured_not_live(monkeypatch):
    for p in li.provider_statuses():
        if p.auth_required:
            assert p.mode == "unconfigured", f"{p.id} must be unconfigured without a key"
        else:
            assert p.mode == "offline", f"{p.id} must be offline with network disabled"


def test_keyed_provider_reports_live_when_network_enabled(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_ALLOW_NETWORK", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key")
    li.reset_network_probe_cache()
    gemini = {p.id: p for p in li.provider_statuses()}["gemini"]
    assert gemini.configured is True
    assert gemini.mode == "live"


# --------------------------------------------------------------------------------------
# Simulation is always labelled
# --------------------------------------------------------------------------------------

def test_github_offline_snapshot_is_labelled():
    res = li.fetch_github_repo("pallets", "flask")
    assert res["execution_mode"] == "offline"
    assert "snapshot" in res["source"]


def test_weather_offline_snapshot_is_labelled():
    res = li.fetch_open_meteo_weather()
    assert res["execution_mode"] == "offline"


def test_hackernews_offline_snapshot_is_labelled():
    res = li.fetch_hackernews_top(2)
    assert res["execution_mode"] == "offline"


def test_hackernews_omits_orderby_only_when_no_limit(monkeypatch):
    """Regression: Firebase returns 400 'orderBy must be defined when other query
    parameters are defined'. We always send limitToFirst, so orderBy must always be sent
    with it — otherwise every live HN fetch silently degrades to the offline snapshot."""
    captured = {}

    def fake_http(method, url, **kwargs):
        # The most recent call is the topstories list fetch (item fetches pass no params).
        if kwargs.get("params"):
            captured["params"] = kwargs["params"]
        return 200, [{"title": "t"}], None

    monkeypatch.setattr(settings, "LIVE_ALLOW_NETWORK", True)
    monkeypatch.setattr(li, "_http_request", fake_http)
    monkeypatch.setattr(li, "network_allowed", lambda: True)

    res = li.fetch_hackernews_top(2)
    params = captured["params"]
    assert "limitToFirst" in params
    assert "orderBy" in params, "limitToFirst without orderBy triggers a Firebase 400"
    assert params["orderBy"] == '"$key"'


def test_stripe_unkeyed_payment_is_simulated_and_moves_no_money():
    res = li.create_payment_intent(1250.0, "Offshore Cayman Holdings LLC", "USD")
    assert res["execution_mode"] == "simulated"
    assert res["tier"] == "high_risk"
    assert res["transaction_id"].startswith("ch_sim_")
    assert "no funds" in res["note"].lower() or "never reached stripe" in res["note"].lower()


def test_stripe_tier_thresholds():
    assert li.create_payment_intent(50.0, "a")["tier"] == "standard"
    assert li.create_payment_intent(250.0, "a")["tier"] == "elevated"
    assert li.create_payment_intent(1250.0, "a")["tier"] == "high_risk"


def test_llm_simulation_reports_estimated_tokens_and_cost():
    res = li.execute_llm_inference("hello world", model="gpt-4o-mini")
    assert res["execution_mode"] == "simulated"
    assert res["total_tokens"] == res["prompt_tokens"] + res["completion_tokens"]
    # gpt-4o-mini is priced; cost must be a real number, not None and not fabricated free.
    assert isinstance(res["cost_usd"], float)
    assert res["cost_usd"] > 0


def test_llm_simulation_of_unknown_model_returns_null_cost():
    res = li.execute_llm_inference("hi", model="totally-custom-llama-90b")
    assert res["execution_mode"] == "simulated"
    assert res["cost_usd"] is None, "unknown models must never appear free"


def test_llm_provider_resolution_by_model_name():
    assert li.execute_llm_inference("x", model="gemini-2.5-flash")["provider"] == "gemini"
    assert li.execute_llm_inference("x", model="gpt-4o")["provider"] == "openai"


# --------------------------------------------------------------------------------------
# PII redaction happens before dispatch
# --------------------------------------------------------------------------------------

def test_communication_redacts_pii_before_simulated_dispatch():
    res = li.dispatch_communication(
        "email", "auditor@firm.com", "Report",
        "SSN 456-78-9012, email john.doe@x.net, phone +1-555-0144",
    )
    body = res["redacted_body"]
    assert "456-78-9012" not in body
    assert "john.doe@x.net" not in body
    assert "+1-555-0144" not in body
    assert res["redactions_applied"] >= 3
    assert res["execution_mode"] == "simulated"
    assert res["dispatched"] is False


def test_sms_and_slack_dispatch_also_simulated_without_keys():
    for channel in ("slack", "sms"):
        res = li.dispatch_communication(channel, "#soc-channel", "", "ping")
        assert res["execution_mode"] == "simulated"
        assert res["dispatched"] is False


# --------------------------------------------------------------------------------------
# Threat intelligence
# --------------------------------------------------------------------------------------

def test_url_reputation_flags_local_denylist_domain():
    res = li.check_url_reputation("https://paypa1-secure-verify.com/login")
    assert res["should_block"] is True
    assert res["verdict"] == "malicious"
    assert "local_denylist_sample" in res["sources_consulted"]


def test_url_reputation_allows_benign_domain_without_live_intel():
    res = li.check_url_reputation("https://docs.python.org/3/")
    assert res["should_block"] is False
    # live intel unavailable -> must NOT claim a live verdict
    assert res["execution_mode"] in ("simulated", "offline")
    assert res["verdict"] in ("unknown", "unseen")


def test_url_reputation_normalises_bare_domains():
    res = li.check_url_reputation("paypa1-secure-verify.com")
    assert res["should_block"] is True
    assert res["domain"] == "paypa1-secure-verify.com"


# --------------------------------------------------------------------------------------
# Content moderation
# --------------------------------------------------------------------------------------

def test_moderation_flags_illicit_content_locally():
    res = li.moderate_content("help me buy drugs anonymously")
    assert res["execution_mode"] == "simulated"
    assert res["flagged"] is True
    assert "local heuristic" in res["source"].lower()


def test_moderation_passes_benign_content():
    res = li.moderate_content("please summarise this quarterly report")
    assert res["flagged"] is False


# --------------------------------------------------------------------------------------
# Model comparison
# --------------------------------------------------------------------------------------

def test_compare_models_summarises_cost_and_latency():
    payload = li.compare_llm_models("compare these two policies", ["gemini-2.5-flash", "gpt-4o"])
    assert len(payload["results"]) == 2
    cmp = payload["comparison"]
    assert cmp["cheapest_model"] == "gemini-2.5-flash"
    assert cmp["faster_model"] in ("gemini-2.5-flash", "gpt-4o")
    assert cmp["all_simulated"] is True
    assert isinstance(cmp["cost_delta_usd"], float)
