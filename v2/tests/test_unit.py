"""Unit tests — fast, no external dependencies, no HTTP calls.

Tests the internal components of cursorpipe v2:
  - Settings / config parsing
  - _flatten_messages() message conversion
  - CompletionResult / StreamChunk dataclasses
  - SessionEntry and SessionStore logic
  - Pydantic schema validation
  - Error handler response shapes
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError


# =========================================================================
# Config / Settings
# =========================================================================


@pytest.mark.unit
class TestConfig:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CURSORPIPE_HOST", raising=False)
        monkeypatch.delenv("CURSORPIPE_PORT", raising=False)
        monkeypatch.delenv("CURSORPIPE_EXPOSE_THINKING", raising=False)
        monkeypatch.delenv("CURSORPIPE_THINKING_LEVEL", raising=False)
        monkeypatch.delenv("CURSORPIPE_LOG_LEVEL", raising=False)
        monkeypatch.delenv("CURSOR_API_KEY", raising=False)

        from cursorpipe._config import Settings

        s = Settings(_env_file=None)
        assert s.host == "0.0.0.0"
        assert s.port == 8080
        assert s.thinking_level == "off"
        assert s.thinking_param is None
        assert s.log_level == "info"
        assert s.bearer_token == ""
        assert s.model == "composer-2.5"

    def test_cors_origins_wildcard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSORPIPE_CORS_ORIGINS", "*")
        from cursorpipe._config import Settings

        s = Settings(_env_file=None)
        assert s.cors_origins_list() == ["*"]

    def test_cors_origins_comma_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "CURSORPIPE_CORS_ORIGINS", "http://localhost:3000,http://app.example.com"
        )
        from cursorpipe._config import Settings

        s = Settings(_env_file=None)
        result = s.cors_origins_list()
        assert "http://localhost:3000" in result
        assert "http://app.example.com" in result
        assert len(result) == 2

    def test_cors_origins_single(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSORPIPE_CORS_ORIGINS", "https://myapp.com")
        from cursorpipe._config import Settings

        s = Settings(_env_file=None)
        assert s.cors_origins_list() == ["https://myapp.com"]

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSORPIPE_PORT", "9090")
        monkeypatch.setenv("CURSORPIPE_MODEL", "gpt-5.4-mini")
        from cursorpipe._config import Settings

        s = Settings(_env_file=None)
        assert s.port == 9090
        assert s.model == "gpt-5.4-mini"

    def test_cursor_api_key_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSOR_API_KEY", "crsr_test123")
        from cursorpipe._config import Settings

        s = Settings(_env_file=None)
        assert s.cursor_api_key == "crsr_test123"


# =========================================================================
# Thinking / thinking_level config
# =========================================================================


@pytest.mark.unit
class TestThinkingConfig:
    """Tests for CURSORPIPE_THINKING_LEVEL and backward-compat EXPOSE_THINKING."""

    def _settings(self, monkeypatch: pytest.MonkeyPatch, **env: str):
        """Helper: clear thinking-related env vars then set the provided ones."""
        from cursorpipe._config import Settings

        monkeypatch.delenv("CURSORPIPE_THINKING_LEVEL", raising=False)
        monkeypatch.delenv("CURSORPIPE_EXPOSE_THINKING", raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return Settings(_env_file=None)

    def test_default_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch)
        assert s.thinking_level == "off"
        assert s.thinking_param is None

    def test_low_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch, CURSORPIPE_THINKING_LEVEL="low")
        assert s.thinking_level == "low"
        assert s.thinking_param == "low"

    def test_high_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch, CURSORPIPE_THINKING_LEVEL="high")
        assert s.thinking_level == "high"
        assert s.thinking_param == "high"

    def test_off_level_returns_none_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch, CURSORPIPE_THINKING_LEVEL="off")
        assert s.thinking_param is None

    def test_legacy_expose_thinking_true_maps_to_high(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CURSORPIPE_EXPOSE_THINKING=true must upgrade thinking_level to 'high'."""
        s = self._settings(monkeypatch, CURSORPIPE_EXPOSE_THINKING="true")
        assert s.thinking_level == "high"
        assert s.thinking_param == "high"

    def test_legacy_expose_thinking_false_leaves_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch, CURSORPIPE_EXPOSE_THINKING="false")
        assert s.thinking_level == "off"
        assert s.thinking_param is None

    def test_thinking_level_wins_over_expose_thinking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit CURSORPIPE_THINKING_LEVEL takes precedence over old EXPOSE_THINKING."""
        s = self._settings(
            monkeypatch,
            CURSORPIPE_THINKING_LEVEL="low",
            CURSORPIPE_EXPOSE_THINKING="true",
        )
        assert s.thinking_level == "low"
        assert s.thinking_param == "low"


# =========================================================================
# _agent_options — ModelSelection with thinking param
# =========================================================================


@pytest.mark.unit
class TestAgentOptions:
    """Tests that _agent_options() builds the correct AgentOptions payload."""

    def test_no_thinking_uses_plain_model_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CURSORPIPE_THINKING_LEVEL", raising=False)
        monkeypatch.delenv("CURSORPIPE_EXPOSE_THINKING", raising=False)

        # Re-import after env change so settings is fresh
        import importlib
        import cursorpipe._config as cfg_mod
        importlib.reload(cfg_mod)
        import cursorpipe._client as client_mod
        importlib.reload(client_mod)

        opts = client_mod._agent_options("composer-2.5")
        # model should be plain string, not a ModelSelection
        from cursor_sdk import ModelSelection
        assert not isinstance(opts.model, ModelSelection), (
            "Expected plain string model when thinking is off"
        )
        assert opts.model == "composer-2.5"

    def test_thinking_high_uses_model_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSORPIPE_THINKING_LEVEL", "high")
        monkeypatch.delenv("CURSORPIPE_EXPOSE_THINKING", raising=False)

        import importlib
        import cursorpipe._config as cfg_mod
        importlib.reload(cfg_mod)
        import cursorpipe._client as client_mod
        importlib.reload(client_mod)

        opts = client_mod._agent_options("composer-2.5")
        from cursor_sdk import ModelSelection, ModelParameterValue
        assert isinstance(opts.model, ModelSelection), (
            "Expected ModelSelection when thinking_level=high"
        )
        assert opts.model.id == "composer-2.5"
        params = {p.id: p.value for p in opts.model.params}
        assert params.get("thinking") == "high"

    def test_thinking_low_uses_model_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSORPIPE_THINKING_LEVEL", "low")
        monkeypatch.delenv("CURSORPIPE_EXPOSE_THINKING", raising=False)

        import importlib
        import cursorpipe._config as cfg_mod
        importlib.reload(cfg_mod)
        import cursorpipe._client as client_mod
        importlib.reload(client_mod)

        opts = client_mod._agent_options("composer-2.5")
        from cursor_sdk import ModelSelection
        assert isinstance(opts.model, ModelSelection)
        params = {p.id: p.value for p in opts.model.params}
        assert params.get("thinking") == "low"

    def test_cursor_params_creates_model_selection(self) -> None:
        """Explicit cursor_params build ModelSelection regardless of THINKING_LEVEL."""
        import importlib
        import cursorpipe._config as cfg_mod
        importlib.reload(cfg_mod)
        import cursorpipe._client as client_mod
        importlib.reload(client_mod)

        from cursor_sdk import ModelSelection
        opts = client_mod._agent_options("gpt-5.5", cursor_params={"reasoning": "medium"})
        assert isinstance(opts.model, ModelSelection)
        assert opts.model.id == "gpt-5.5"
        params = {p.id: p.value for p in opts.model.params}
        assert params["reasoning"] == "medium"

    def test_cursor_params_multiple_params_all_passed(self) -> None:
        """Multiple cursor_params entries each become a ModelParameterValue."""
        import importlib
        import cursorpipe._config as cfg_mod
        importlib.reload(cfg_mod)
        import cursorpipe._client as client_mod
        importlib.reload(client_mod)

        from cursor_sdk import ModelSelection
        opts = client_mod._agent_options(
            "claude-opus-4-8",
            cursor_params={"thinking": "true", "effort": "medium"},
        )
        assert isinstance(opts.model, ModelSelection)
        params = {p.id: p.value for p in opts.model.params}
        assert params["thinking"] == "true"
        assert params["effort"] == "medium"

    def test_cursor_params_overrides_thinking_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cursor_params must take priority over CURSORPIPE_THINKING_LEVEL."""
        monkeypatch.setenv("CURSORPIPE_THINKING_LEVEL", "high")
        monkeypatch.delenv("CURSORPIPE_EXPOSE_THINKING", raising=False)

        import importlib
        import cursorpipe._config as cfg_mod
        importlib.reload(cfg_mod)
        import cursorpipe._client as client_mod
        importlib.reload(client_mod)

        from cursor_sdk import ModelSelection
        opts = client_mod._agent_options(
            "claude-opus-4-8",
            cursor_params={"effort": "low"},
        )
        assert isinstance(opts.model, ModelSelection)
        params = {p.id: p.value for p in opts.model.params}
        # cursor_params wins; global thinking=high must NOT bleed in
        assert params.get("effort") == "low"
        assert "thinking" not in params


# =========================================================================
# ModelCard cursor_parameters schema
# =========================================================================


@pytest.mark.unit
class TestModelCardSchema:
    """Tests for the cursor_parameters extension field on ModelCard."""

    def test_model_card_without_params(self) -> None:
        from cursorpipe_server.schemas import ModelCard

        card = ModelCard(id="composer-2.5")
        assert card.cursor_parameters == []

    def test_model_card_with_thinking_param(self) -> None:
        from cursorpipe_server.schemas import ModelCard, ModelParamDef, ModelParamValueDef

        card = ModelCard(
            id="composer-2.5",
            cursor_parameters=[
                ModelParamDef(
                    id="thinking",
                    display_name="Thinking",
                    values=[
                        ModelParamValueDef(value="low", display_name="Low"),
                        ModelParamValueDef(value="high", display_name="High"),
                    ],
                )
            ],
        )
        assert len(card.cursor_parameters) == 1
        param = card.cursor_parameters[0]
        assert param.id == "thinking"
        assert len(param.values) == 2
        assert param.values[0].value == "low"
        assert param.values[1].value == "high"

    def test_model_card_serializes_cursor_parameters(self) -> None:
        from cursorpipe_server.schemas import ModelCard, ModelParamDef, ModelParamValueDef

        card = ModelCard(
            id="composer-2.5",
            cursor_parameters=[
                ModelParamDef(
                    id="thinking",
                    values=[ModelParamValueDef(value="high", display_name="High")],
                )
            ],
        )
        data = card.model_dump()
        assert "cursor_parameters" in data
        assert data["cursor_parameters"][0]["id"] == "thinking"


# =========================================================================
# _flatten_messages
# =========================================================================


@pytest.mark.unit
class TestFlattenMessages:
    def _flatten(self, messages: list[dict]) -> tuple[str, str]:
        from cursorpipe._client import _flatten_messages

        return _flatten_messages(messages)

    def test_system_and_user(self) -> None:
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        prompt, system = self._flatten(messages)
        assert "Hello" in prompt
        assert "You are helpful." in system

    def test_only_user(self) -> None:
        messages = [{"role": "user", "content": "Hi"}]
        prompt, system = self._flatten(messages)
        assert "Hi" in prompt
        assert system == ""

    def test_only_system(self) -> None:
        messages = [{"role": "system", "content": "Context only"}]
        prompt, system = self._flatten(messages)
        assert prompt == ""
        assert "Context only" in system

    def test_list_content_blocks(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Part one"},
                    {"type": "text", "text": " part two"},
                    {"type": "image_url", "text": "ignored"},
                ],
            }
        ]
        prompt, _ = self._flatten(messages)
        assert "Part one" in prompt
        assert "part two" in prompt

    def test_none_content_treated_as_empty(self) -> None:
        messages = [{"role": "user", "content": None}]
        prompt, system = self._flatten(messages)
        # Should not raise; empty content produces empty string
        assert isinstance(prompt, str)

    def test_assistant_messages_included_in_prompt(self) -> None:
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "Goodbye"},
        ]
        prompt, _ = self._flatten(messages)
        assert "assistant: Hi there" in prompt


# =========================================================================
# CompletionResult / StreamChunk dataclasses
# =========================================================================


@pytest.mark.unit
class TestResultDataclasses:
    def test_completion_result_defaults(self) -> None:
        from cursorpipe._client import CompletionResult

        r = CompletionResult(text="hello")
        assert r.finish_reason == "stop"
        assert r.actual_model is None
        assert r.duration_ms == 0
        assert r.run_id is None
        assert r.agent_id is None
        assert r.thinking is None
        assert r.thinking_duration_ms == 0

    def test_completion_result_populated(self) -> None:
        from cursorpipe._client import CompletionResult

        r = CompletionResult(
            text="answer",
            finish_reason="stop",
            actual_model="composer-2.5",
            duration_ms=500,
            run_id="run-abc",
            agent_id="agent-xyz",
        )
        assert r.text == "answer"
        assert r.actual_model == "composer-2.5"
        assert r.duration_ms == 500

    def test_stream_chunk_text(self) -> None:
        from cursorpipe._client import StreamChunk

        chunk = StreamChunk(type="text", text="hello")
        assert chunk.type == "text"
        assert chunk.text == "hello"
        assert chunk.thinking_duration_ms == 0

    def test_stream_chunk_thinking(self) -> None:
        from cursorpipe._client import StreamChunk

        chunk = StreamChunk(type="thinking", text="hmm...", thinking_duration_ms=300)
        assert chunk.type == "thinking"
        assert chunk.thinking_duration_ms == 300


# =========================================================================
# SessionEntry
# =========================================================================


@pytest.mark.unit
class TestSessionEntry:
    def _make_entry(self, session_id: str = "sess-1", model: str = "composer-2.5"):
        from cursorpipe._session_store import SessionEntry

        return SessionEntry(session_id=session_id, agent=MagicMock(), model=model)

    def test_not_expired_immediately(self) -> None:
        entry = self._make_entry()
        assert not entry.is_expired(ttl_minutes=30)

    def test_expired_after_ttl(self) -> None:
        from cursorpipe._session_store import SessionEntry

        entry = SessionEntry(session_id="s", agent=MagicMock(), model="m")
        # Backdate last_used_at
        entry.last_used_at = datetime.now(timezone.utc) - timedelta(minutes=31)
        assert entry.is_expired(ttl_minutes=30)

    def test_touch_resets_last_used(self) -> None:
        from cursorpipe._session_store import SessionEntry

        entry = SessionEntry(session_id="s", agent=MagicMock(), model="m")
        entry.last_used_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        entry.touch()
        # After touch, should not be expired with a 30-minute TTL
        assert not entry.is_expired(ttl_minutes=30)

    def test_to_dict_keys(self) -> None:
        entry = self._make_entry(session_id="sess-abc", model="composer-2.5")
        d = entry.to_dict()
        assert d["id"] == "sess-abc"
        assert d["model"] == "composer-2.5"
        assert "created_at" in d
        assert "last_used_at" in d


# =========================================================================
# SessionStore
# =========================================================================


@pytest.mark.unit
class TestSessionStore:
    def _make_store(self):
        from cursorpipe._session_store import SessionStore

        return SessionStore()

    def _make_mock_client(self):
        client = AsyncMock()
        agent = AsyncMock()
        agent.close = AsyncMock()
        client.agents.create = AsyncMock(return_value=agent)
        return client, agent

    async def test_get_or_create_creates_once(self) -> None:
        store = self._make_store()
        client, agent = self._make_mock_client()

        e1 = await store.get_or_create("sess-1", "composer-2.5", client)
        e2 = await store.get_or_create("sess-1", "composer-2.5", client)

        assert e1 is e2
        assert client.agents.create.call_count == 1

    async def test_get_or_create_different_sessions(self) -> None:
        store = self._make_store()
        client, _ = self._make_mock_client()

        e1 = await store.get_or_create("sess-A", "composer-2.5", client)
        e2 = await store.get_or_create("sess-B", "composer-2.5", client)

        assert e1 is not e2
        assert client.agents.create.call_count == 2

    async def test_delete_returns_true_for_known(self) -> None:
        store = self._make_store()
        client, _ = self._make_mock_client()

        await store.get_or_create("sess-1", "composer-2.5", client)
        result = await store.delete("sess-1")
        assert result is True

    async def test_delete_returns_false_for_unknown(self) -> None:
        store = self._make_store()
        result = await store.delete("nonexistent")
        assert result is False

    async def test_list_all_snapshot(self) -> None:
        store = self._make_store()
        client, _ = self._make_mock_client()

        assert store.list_all() == []
        await store.get_or_create("sess-X", "composer-2.5", client)
        entries = store.list_all()
        assert len(entries) == 1
        assert entries[0].session_id == "sess-X"

    async def test_model_stored_on_entry(self) -> None:
        store = self._make_store()
        client, _ = self._make_mock_client()

        entry = await store.get_or_create("sess-1", "gpt-5.4-mini", client)
        assert entry.model == "gpt-5.4-mini"


# =========================================================================
# Schemas
# =========================================================================


@pytest.mark.unit
class TestSchemas:
    def test_request_ignores_unknown_fields(self) -> None:
        from cursorpipe_server.schemas import ChatCompletionRequest

        # These OpenAI fields are not implemented in v2 but must not cause 422
        req = ChatCompletionRequest(
            model="composer-2.5",
            messages=[{"role": "user", "content": "hi"}],
            stream_options={"include_usage": True},
            logit_bias={"50256": -100},
            top_p=0.9,
            frequency_penalty=0.5,
        )
        assert req.model == "composer-2.5"

    def test_request_requires_messages(self) -> None:
        from cursorpipe_server.schemas import ChatCompletionRequest

        with pytest.raises(ValidationError):
            ChatCompletionRequest(model="composer-2.5", messages=[])

    def test_cursor_metadata_defaults(self) -> None:
        from cursorpipe_server.schemas import CursorMetadata

        meta = CursorMetadata()
        assert meta.duration_ms == 0
        assert meta.run_id is None
        assert meta.agent_id is None
        assert meta.session_id is None
        assert meta.thinking is None
        assert meta.thinking_duration_ms == 0

    def test_response_has_cursor_metadata(self) -> None:
        from cursorpipe_server.schemas import (
            ChatCompletionChoice,
            ChatCompletionMessage,
            ChatCompletionResponse,
        )

        resp = ChatCompletionResponse(
            model="composer-2.5",
            choices=[
                ChatCompletionChoice(
                    message=ChatCompletionMessage(content="hello"),
                )
            ],
        )
        assert hasattr(resp, "cursor_metadata")
        assert resp.cursor_metadata.duration_ms == 0


# =========================================================================
# cursor_params request field
# =========================================================================


@pytest.mark.unit
class TestCursorParamsSchema:
    """Tests for the cursor_params extension field on request models."""

    def test_chat_request_cursor_params_none_by_default(self) -> None:
        from cursorpipe_server.schemas import ChatCompletionRequest

        req = ChatCompletionRequest(
            model="composer-2.5",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert req.cursor_params is None

    def test_chat_request_accepts_cursor_params(self) -> None:
        from cursorpipe_server.schemas import ChatCompletionRequest

        req = ChatCompletionRequest(
            model="gpt-5.5",
            messages=[{"role": "user", "content": "hi"}],
            cursor_params={"reasoning": "medium"},
        )
        assert req.cursor_params == {"reasoning": "medium"}

    def test_chat_request_accepts_multiple_cursor_params(self) -> None:
        from cursorpipe_server.schemas import ChatCompletionRequest

        req = ChatCompletionRequest(
            model="claude-opus-4-8",
            messages=[{"role": "user", "content": "hi"}],
            cursor_params={"thinking": "true", "effort": "medium", "context": "1m"},
        )
        assert req.cursor_params == {"thinking": "true", "effort": "medium", "context": "1m"}

    def test_create_session_request_cursor_params_none_by_default(self) -> None:
        from cursorpipe_server.schemas import CreateSessionRequest

        req = CreateSessionRequest(model="composer-2.5")
        assert req.cursor_params is None

    def test_create_session_request_accepts_cursor_params(self) -> None:
        from cursorpipe_server.schemas import CreateSessionRequest

        req = CreateSessionRequest(model="gpt-5.5", cursor_params={"reasoning": "high"})
        assert req.cursor_params == {"reasoning": "high"}


# =========================================================================
# Error handlers
# =========================================================================


@pytest.mark.unit
class TestErrorHandlers:
    async def _call_handler(self, handler, exc):
        """Call a handler and return its JSON content."""
        from starlette.requests import Request
        from starlette.testclient import TestClient

        # Build a minimal mock request
        mock_request = MagicMock()
        response = await handler(mock_request, exc)
        return response.status_code, response.body

    async def test_validation_error_shape(self) -> None:
        from fastapi.exceptions import RequestValidationError

        from cursorpipe_server.errors import validation_error_handler

        exc = RequestValidationError(
            errors=[{"loc": ("body", "messages"), "msg": "field required", "type": "missing"}]
        )
        request = MagicMock()
        response = await validation_error_handler(request, exc)
        import json

        body = json.loads(response.body)
        assert response.status_code == 422
        assert "error" in body
        assert body["error"]["type"] == "invalid_request_error"

    async def test_generic_error_returns_500(self) -> None:
        from cursorpipe_server.errors import generic_error_handler

        request = MagicMock()
        response = await generic_error_handler(request, RuntimeError("boom"))
        assert response.status_code == 500
