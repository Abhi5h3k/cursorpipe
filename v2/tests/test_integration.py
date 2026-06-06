"""Integration tests — real SDK calls against the Cursor API.

These tests are skipped automatically when CURSOR_API_KEY is not set.

Run with:
    cd v2
    uv run pytest tests/test_integration.py -v -m integration

CURSOR_API_KEY is loaded automatically from v2/.env by pydantic-settings.
You can also override it explicitly:
    uv run pytest tests/test_integration.py -v -m integration

Or skip integration tests with:
    uv run pytest -m "not integration"

All tests start a fresh FastAPI app and manually invoke its lifespan so the
real SDK bridge starts before requests are made (httpx.ASGITransport does not
send ASGI lifespan events automatically).
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

# Load .env so os.getenv() sees CURSOR_API_KEY even when it is not already
# exported in the shell (pydantic-settings loads it at Settings instantiation,
# which is too late for the module-level skip check below).
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

skip_no_api_key = pytest.mark.skipif(
    not os.getenv("CURSOR_API_KEY"),
    reason="CURSOR_API_KEY not set — skipping integration tests",
)

# Override via env var to use a model allowed by your Cursor admin policy.
# Defaults to "auto" (same as v1 tests) so Cursor picks the best available model.
TEST_MODEL = os.getenv("CURSORPIPE_TEST_MODEL", "auto")


# ---------------------------------------------------------------------------
# Async client that uses the real lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _real_app_client():
    """Async context manager: real FastAPI app with full lifespan.

    httpx.ASGITransport does not send ASGI lifespan events automatically, so
    we invoke the app's lifespan context manager ourselves to start the real
    SDK bridge and populate app.state before any requests are made.

    Usage::

        async with _real_app_client() as client:
            response = await client.get("/health")
    """
    from cursorpipe_server.app import create_app

    app = create_app()

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@skip_no_api_key
class TestIntegrationNonStreaming:
    """Non-streaming stateless completions against the real SDK."""

    async def test_simple_completion_returns_text(self) -> None:
        async with _real_app_client() as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "Reply with the single word: PONG"}],
                },
                timeout=90,
            )
        assert response.status_code == 200
        body = response.json()
        assert body["object"] == "chat.completion"
        content = body["choices"][0]["message"]["content"]
        assert isinstance(content, str)
        assert len(content) > 0

    async def test_response_has_cursor_metadata(self) -> None:
        async with _real_app_client() as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "Say hi"}],
                },
                timeout=90,
            )
        body = response.json()
        meta = body.get("cursor_metadata", {})
        assert meta.get("duration_ms", 0) > 0

    async def test_model_field_in_response(self) -> None:
        async with _real_app_client() as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                timeout=90,
            )
        body = response.json()
        assert "model" in body
        assert isinstance(body["model"], str)


@pytest.mark.integration
@skip_no_api_key
class TestIntegrationStreaming:
    """Streaming SSE completions against the real SDK."""

    async def test_streaming_yields_chunks(self) -> None:
        async with _real_app_client() as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": TEST_MODEL,
                    "stream": True,
                    "messages": [
                        {"role": "user", "content": "Count: one two three"}
                    ],
                },
                timeout=90,
            )
        assert response.status_code == 200
        raw = response.text
        data_lines = [
            l for l in raw.splitlines()
            if l.startswith("data:") and "[DONE]" not in l
        ]
        assert len(data_lines) > 0, "No SSE chunks received"
        # Join all content chunks into a full text
        full_text = ""
        for line in data_lines:
            chunk = json.loads(line.removeprefix("data:").strip())
            delta = chunk["choices"][0]["delta"]
            full_text += delta.get("content", "")
        assert len(full_text) > 0

    async def test_streaming_ends_with_done(self) -> None:
        async with _real_app_client() as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": TEST_MODEL,
                    "stream": True,
                    "messages": [{"role": "user", "content": "Say: ok"}],
                },
                timeout=90,
            )
        assert "[DONE]" in response.text


@pytest.mark.integration
@skip_no_api_key
class TestIntegrationStateful:
    """Stateful multi-turn completions using X-Cursor-Session-ID."""

    async def test_second_turn_recalls_first(self) -> None:
        session_id = "integration-test-session"
        async with _real_app_client() as client:
            # First turn: establish context
            r1 = await client.post(
                "/v1/chat/completions",
                headers={"X-Cursor-Session-ID": session_id},
                json={
                    "model": TEST_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": "The secret code is BANANA. Reply with: ACK",
                        }
                    ],
                },
                timeout=90,
            )
            assert r1.status_code == 200

            # Second turn: verify context is retained
            r2 = await client.post(
                "/v1/chat/completions",
                headers={"X-Cursor-Session-ID": session_id},
                json={
                    "model": TEST_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": "What is the secret code? Reply with just the word.",
                        }
                    ],
                },
                timeout=90,
            )
            assert r2.status_code == 200
            content = r2.json()["choices"][0]["message"]["content"]
            assert "BANANA" in content.upper(), (
                f"Expected BANANA in second turn, got: {content[:200]}"
            )

        # Clean up: delete the session
        async with _real_app_client() as client:
            await client.delete(f"/v1/sessions/{session_id}")


@pytest.mark.integration
@skip_no_api_key
class TestIntegrationHealth:
    async def test_health_ok_with_real_bridge(self) -> None:
        async with _real_app_client() as client:
            response = await client.get("/health", timeout=30)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["bridge"] == "connected"


@pytest.mark.integration
@skip_no_api_key
class TestIntegrationModels:
    async def test_list_models_returns_entries(self) -> None:
        async with _real_app_client() as client:
            response = await client.get("/v1/models", timeout=30)
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) >= 1
