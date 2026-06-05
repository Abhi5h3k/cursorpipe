"""Shared fixtures for cursorpipe tests."""

from __future__ import annotations

import time

import pytest

from cursorpipe import CursorClient, CursorPipeConfig, Strategy

# ---------------------------------------------------------------------------
# Per-test: breathing room between integration calls.
# A short sleep after each integration test reduces back-to-back API pressure
# and keeps response times consistent across sequential calls.
# When running with -n (xdist parallel), this applies within each worker,
# naturally spacing that worker's own calls.
# ---------------------------------------------------------------------------

_INTEGRATION_BREATHING_S = 3


@pytest.fixture(autouse=True)
def _inter_test_delay(request: pytest.FixtureRequest) -> None:
    """Sleep briefly after each integration test to avoid hammering the API."""
    yield
    if request.node.get_closest_marker("integration"):
        time.sleep(_INTEGRATION_BREATHING_S)


# ---------------------------------------------------------------------------
# Integration client fixtures — use a 60s timeout (vs 300s production default)
# so a hung agent call fails fast rather than blocking the suite for 5 minutes.
# Tests are also protected by the global pytest-timeout = 90s safety net.
# ---------------------------------------------------------------------------

_TEST_TIMEOUT_S = 60


@pytest.fixture
def integration_config() -> CursorPipeConfig:
    """CursorPipeConfig with a test-appropriate 60s request timeout."""
    return CursorPipeConfig(request_timeout_s=_TEST_TIMEOUT_S)


@pytest.fixture
def sub_client(integration_config: CursorPipeConfig) -> CursorClient:
    """Subprocess-transport client for integration tests."""
    return CursorClient(CursorPipeConfig(
        strategy=Strategy.SUBPROCESS,
        request_timeout_s=_TEST_TIMEOUT_S,
    ))


@pytest.fixture
def acp_client(integration_config: CursorPipeConfig) -> CursorClient:
    """ACP-transport client for integration tests."""
    return CursorClient(CursorPipeConfig(
        strategy=Strategy.ACP,
        request_timeout_s=_TEST_TIMEOUT_S,
    ))


# ---------------------------------------------------------------------------
# Shared generic fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config() -> CursorPipeConfig:
    """Config loaded from env with defaults (production values)."""
    return CursorPipeConfig()


@pytest.fixture
def client(default_config: CursorPipeConfig) -> CursorClient:
    """A CursorClient instance using default config."""
    return CursorClient(default_config)
