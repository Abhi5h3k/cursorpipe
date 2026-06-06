"""Shared fixtures for cursorpipe v2 tests.

Architecture
------------
httpx.ASGITransport does NOT trigger the ASGI lifespan, so state must be
injected directly onto the app object before httpx requests are made.
The production lifespan is patched with a no-op so it cannot accidentally
launch the real SDK bridge if something does trigger it.

Integration tests (test_integration.py) use the real lifespan and SDK.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cursorpipe._session_store import SessionStore


# ── SDK mock building blocks ─────────────────────────────────────────────────


@pytest.fixture
def mock_text_block():
    """A single text content block returned inside an assistant message."""
    block = MagicMock()
    block.type = "text"
    block.text = "PONG"
    return block


@pytest.fixture
def mock_message(mock_text_block):
    """A fake SDK assistant message with one text block."""
    msg = MagicMock()
    msg.type = "assistant"
    msg.message = MagicMock()
    msg.message.content = [mock_text_block]
    return msg


@pytest.fixture
def mock_run(mock_message):
    """A fake SDK Run object.

    run.messages() is an async generator that yields one assistant message.
    Scalar attributes (result, status, duration_ms, id, agent_id, model) are
    set to representative values so CompletionResult can be populated.
    """
    run = MagicMock()

    captured_message = mock_message

    async def _messages():
        yield captured_message

    run.messages = _messages
    run.result = "PONG"
    run.status = "finished"
    run.duration_ms = 120
    run.id = "run-test-abc"
    run.agent_id = "agent-test-xyz"
    run.model = None  # actual_model falls back to the requested model
    return run


@pytest.fixture
def mock_agent(mock_run):
    """A fake SDK AsyncAgent whose send() returns mock_run."""
    agent = AsyncMock()
    agent.send = AsyncMock(return_value=mock_run)
    agent.close = AsyncMock()
    return agent


@pytest.fixture
def mock_cursor_client(mock_agent):
    """A fake SDK AsyncClient whose agents.create() returns mock_agent."""
    client = AsyncMock()
    client.agents.create = AsyncMock(return_value=mock_agent)
    return client


# ── FastAPI test client helpers ───────────────────────────────────────────────


@asynccontextmanager
async def _noop_lifespan(app):
    """No-op lifespan — prevents the real SDK bridge from launching in tests."""
    yield


def _build_app(mock_cursor_client):
    """Create a test FastAPI app with state injected directly.

    httpx.ASGITransport does not send lifespan events, so we set
    cursor_client and session_store directly on app.state instead of
    relying on the lifespan context manager.
    """
    from cursorpipe_server.app import create_app

    with patch("cursorpipe_server.app.lifespan", _noop_lifespan):
        app = create_app()

    store = SessionStore()
    app.state.cursor_client = mock_cursor_client
    app.state.session_store = store
    return app, store


# ── FastAPI test client fixtures ──────────────────────────────────────────────


@pytest.fixture
async def app_client(mock_cursor_client):
    """Async HTTP client wired to a cursorpipe v2 FastAPI app.

    Bearer auth is disabled (default empty token).
    """
    app, store = _build_app(mock_cursor_client)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    await store.stop_cleanup()


@pytest.fixture
async def authed_app_client(mock_cursor_client):
    """Same as app_client but with bearer token auth enabled (token='secret')."""
    from cursorpipe_server.app import settings

    original_token = settings.bearer_token
    settings.__dict__["bearer_token"] = "secret"

    try:
        app, store = _build_app(mock_cursor_client)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

        await store.stop_cleanup()
    finally:
        settings.__dict__["bearer_token"] = original_token
