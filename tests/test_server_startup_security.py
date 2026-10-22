"""Tests for server startup environment gating and example token refusal."""

import pytest
from unittest.mock import patch
from server.app.config import settings
from server.app.main import _seed_initial_data


def test_server_refuses_example_admin_token_in_production():
    """Server must raise RuntimeError if starting in prod with default example admin token."""
    with patch.object(settings, "ENV", "prod"):
        with patch.object(settings, "ADMIN_TOKEN", "agentshield-admin-supersecret-token-2026"):
            with pytest.raises(RuntimeError, match="Security violation: Server startup aborted"):
                _seed_initial_data()


def test_server_refuses_example_api_key_as_admin_token_in_staging():
    """Server must raise RuntimeError if starting in staging with default example dev key as admin token."""
    with patch.object(settings, "ENV", "staging"):
        with patch.object(settings, "ADMIN_TOKEN", "agentshield-dev-key-12345"):
            with pytest.raises(RuntimeError, match="Security violation: Server startup aborted"):
                _seed_initial_data()


def test_server_allows_secure_token_in_production_without_seeding_dev_keys():
    """In prod with a secure custom token, _seed_initial_data returns cleanly without seeding dev keys."""
    with patch.object(settings, "ENV", "prod"):
        with patch.object(settings, "ADMIN_TOKEN", "prod-secure-randomly-generated-token-xyz-987"):
            # Should return cleanly without error
            _seed_initial_data()


def test_server_seeds_in_dev_environment():
    """In dev environment, _seed_initial_data executes cleanly."""
    with patch.object(settings, "ENV", "dev"):
        _seed_initial_data()


def test_server_defaults_to_fail_safe_production_when_env_unconfigured():
    """When ENV is unconfigured (None), it defaults to fail-safe production and refuses example tokens."""
    with patch.object(settings, "ENV", None):
        with patch.object(settings, "ADMIN_TOKEN", "agentshield-admin-supersecret-token-2026"):
            with pytest.raises(RuntimeError, match="Security violation: Server startup aborted"):
                _seed_initial_data()

