"""Server-layer tests — HTTP API via httpx.AsyncClient + mocked SDK.

No real Cursor SDK calls are made. The SDK bridge is replaced by fixtures
from conftest.py. All tests run offline and fast.

Coverage
--------
- GET /health        — bridge connected vs unavailable
- GET /v1/models     — model list (fallback to default)
- POST /v1/chat/completions — stateless, streaming, stateful, validation errors
- Bearer token auth  — enabled vs disabled, correct vs wrong token
- GET/POST/DELETE /v1/sessions — CRUD
- X-Request-ID header — generated and echoed
"""

from __future__ import annotations

import json

import pytest


# =========================================================================
# Health
# =========================================================================


@pytest.mark.unit
class TestHealth:
    async def test_health_ok_when_bridge_set(self, app_client) -> None:
        response = await app_client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["bridge"] == "connected"

    async def test_health_degraded_when_bridge_none(self, mock_cursor_client) -> None:
        """When app.state.cursor_client is None, /health returns 503."""
        from contextlib import asynccontextmanager
        from unittest.mock import patch

        import httpx

        from cursorpipe._session_store import SessionStore
        from cursorpipe_server.app import create_app

        @asynccontextmanager
        async def _none_bridge_lifespan(app):
            store = SessionStore()
            store.start_cleanup()
            app.state.cursor_client = None  # bridge not available
            app.state.session_store = store
            yield
            await store.stop_cleanup()

        with patch("cursorpipe_server.app.lifespan", _none_bridge_lifespan):
            app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["bridge"] == "unavailable"


# =========================================================================
# Models
# =========================================================================


@pytest.mark.unit
class TestModels:
    async def test_list_models_returns_list(self, app_client) -> None:
        response = await app_client.get("/v1/models")
        assert response.status_code == 200
        body = response.json()
        assert body["object"] == "list"
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 1
        # Each model card must have an id
        for card in body["data"]:
            assert "id" in card


# =========================================================================
# Chat completions — stateless
# =========================================================================


@pytest.mark.unit
class TestChatCompletionsStateless:
    _payload = {
        "model": "composer-2.5",
        "messages": [{"role": "user", "content": "Reply PONG"}],
    }

    async def test_non_streaming_200(self, app_client) -> None:
        response = await app_client.post(
            "/v1/chat/completions",
            json=self._payload,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["object"] == "chat.completion"
        assert len(body["choices"]) == 1
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert isinstance(body["choices"][0]["message"]["content"], str)

    async def test_non_streaming_has_cursor_metadata(self, app_client) -> None:
        response = await app_client.post("/v1/chat/completions", json=self._payload)
        body = response.json()
        assert "cursor_metadata" in body

    async def test_non_streaming_finish_reason(self, app_client) -> None:
        response = await app_client.post("/v1/chat/completions", json=self._payload)
        body = response.json()
        assert body["choices"][0]["finish_reason"] in ("stop", "length")

    async def test_unknown_openai_fields_ignored(self, app_client) -> None:
        """Fields like top_p, logit_bias, frequency_penalty must not cause 422."""
        response = await app_client.post(
            "/v1/chat/completions",
            json={
                **self._payload,
                "top_p": 0.9,
                "logit_bias": {"50256": -100},
                "frequency_penalty": 0.5,
                "stream_options": {"include_usage": True},
            },
        )
        assert response.status_code == 200

    async def test_missing_messages_returns_openai_422(self, app_client) -> None:
        """Missing required field must return OpenAI-shaped 422, not FastAPI default."""
        response = await app_client.post(
            "/v1/chat/completions",
            json={"model": "composer-2.5"},
        )
        assert response.status_code == 422
        body = response.json()
        assert "error" in body
        assert body["error"]["type"] == "invalid_request_error"

    async def test_empty_messages_returns_422(self, app_client) -> None:
        response = await app_client.post(
            "/v1/chat/completions",
            json={"model": "composer-2.5", "messages": []},
        )
        assert response.status_code == 422

    async def test_streaming_sse_format(self, app_client) -> None:
        """Streaming response must be valid SSE with [DONE] at the end."""
        response = await app_client.post(
            "/v1/chat/completions",
            json={**self._payload, "stream": True},
        )
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        raw = response.text
        # Must contain data: ... lines
        assert "data:" in raw
        # Must end with [DONE]
        assert "[DONE]" in raw

    async def test_streaming_first_chunk_has_role(self, app_client) -> None:
        """The first SSE chunk must set delta.role='assistant'."""
        response = await app_client.post(
            "/v1/chat/completions",
            json={**self._payload, "stream": True},
        )
        raw = response.text
        lines = [l for l in raw.splitlines() if l.startswith("data:") and "[DONE]" not in l]
        assert len(lines) >= 1
        first_chunk = json.loads(lines[0].removeprefix("data:").strip())
        assert first_chunk["choices"][0]["delta"].get("role") == "assistant"

    async def test_streaming_last_chunk_has_stop(self, app_client) -> None:
        """The last non-DONE SSE chunk must have finish_reason='stop'."""
        response = await app_client.post(
            "/v1/chat/completions",
            json={**self._payload, "stream": True},
        )
        raw = response.text
        data_lines = [l for l in raw.splitlines() if l.startswith("data:") and "[DONE]" not in l]
        last_chunk = json.loads(data_lines[-1].removeprefix("data:").strip())
        assert last_chunk["choices"][0]["finish_reason"] == "stop"


# =========================================================================
# Chat completions — stateful sessions
# =========================================================================


@pytest.mark.unit
class TestChatCompletionsStateful:
    _payload = {
        "model": "composer-2.5",
        "messages": [{"role": "user", "content": "Hello"}],
    }

    async def test_session_header_echoed(self, app_client) -> None:
        response = await app_client.post(
            "/v1/chat/completions",
            headers={"X-Cursor-Session-ID": "my-session"},
            json=self._payload,
        )
        assert response.status_code == 200
        assert response.headers.get("x-cursor-session-id") == "my-session"

    async def test_stateful_streaming_echoes_session(self, app_client) -> None:
        response = await app_client.post(
            "/v1/chat/completions",
            headers={"X-Cursor-Session-ID": "stream-session"},
            json={**self._payload, "stream": True},
        )
        assert response.status_code == 200
        assert response.headers.get("x-cursor-session-id") == "stream-session"


# =========================================================================
# Request ID header
# =========================================================================


@pytest.mark.unit
class TestRequestID:
    async def test_provided_request_id_echoed(self, app_client) -> None:
        response = await app_client.get(
            "/health", headers={"X-Request-ID": "trace-abc-123"}
        )
        assert response.headers.get("x-request-id") == "trace-abc-123"

    async def test_missing_request_id_generated(self, app_client) -> None:
        response = await app_client.get("/health")
        request_id = response.headers.get("x-request-id")
        assert request_id is not None
        assert len(request_id) > 0


# =========================================================================
# Bearer token auth
# =========================================================================


@pytest.mark.unit
class TestBearerAuth:
    """Auth tests use authed_app_client which has bearer_token='secret'."""

    async def test_no_auth_configured_allows_all(self, app_client) -> None:
        """Default app_client has no bearer token — all requests pass."""
        response = await app_client.get("/health")
        assert response.status_code == 200

    async def test_correct_token_allowed(self, authed_app_client) -> None:
        response = await authed_app_client.get(
            "/health",
            headers={"Authorization": "Bearer secret"},
        )
        # /health is public, so auth header is irrelevant here;
        # test a protected route
        response = await authed_app_client.get(
            "/v1/models",
            headers={"Authorization": "Bearer secret"},
        )
        assert response.status_code == 200

    async def test_wrong_token_rejected(self, authed_app_client) -> None:
        response = await authed_app_client.get(
            "/v1/models",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401

    async def test_missing_token_rejected(self, authed_app_client) -> None:
        response = await authed_app_client.get("/v1/models")
        assert response.status_code == 401


# =========================================================================
# Session management endpoints
# =========================================================================


@pytest.mark.unit
class TestSessionEndpoints:
    async def test_list_sessions_empty(self, app_client) -> None:
        response = await app_client.get("/v1/sessions")
        assert response.status_code == 200
        body = response.json()
        assert body["object"] == "list"
        assert body["data"] == []

    async def test_create_session(self, app_client) -> None:
        response = await app_client.post(
            "/v1/sessions",
            json={"model": "composer-2.5"},
        )
        assert response.status_code == 201
        body = response.json()
        assert "id" in body
        assert body["model"] == "composer-2.5"
        assert "created_at" in body
        assert "last_used_at" in body

    async def test_get_session_after_create(self, app_client) -> None:
        create_resp = await app_client.post(
            "/v1/sessions", json={"model": "composer-2.5"}
        )
        session_id = create_resp.json()["id"]

        get_resp = await app_client.get(f"/v1/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == session_id

    async def test_get_unknown_session_404(self, app_client) -> None:
        response = await app_client.get("/v1/sessions/nonexistent-id")
        assert response.status_code == 404

    async def test_delete_session(self, app_client) -> None:
        create_resp = await app_client.post(
            "/v1/sessions", json={"model": "composer-2.5"}
        )
        session_id = create_resp.json()["id"]

        del_resp = await app_client.delete(f"/v1/sessions/{session_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

    async def test_delete_unknown_session_404(self, app_client) -> None:
        response = await app_client.delete("/v1/sessions/does-not-exist")
        assert response.status_code == 404

    async def test_delete_then_list_empty(self, app_client) -> None:
        create_resp = await app_client.post(
            "/v1/sessions", json={"model": "composer-2.5"}
        )
        session_id = create_resp.json()["id"]
        await app_client.delete(f"/v1/sessions/{session_id}")

        list_resp = await app_client.get("/v1/sessions")
        assert list_resp.json()["data"] == []

    async def test_list_sessions_after_create(self, app_client) -> None:
        await app_client.post("/v1/sessions", json={"model": "composer-2.5"})
        response = await app_client.get("/v1/sessions")
        assert len(response.json()["data"]) >= 1
