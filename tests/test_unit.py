"""Unit tests — fast, no external dependencies.

Tests the internal components (config, models, resolve, NDJSON parser, errors)
without needing a Cursor agent binary or network access.
"""

from __future__ import annotations

import json

import pytest

from cursorpipe._config import CursorPipeConfig, Strategy
from cursorpipe._errors import (
    AgentCrashError,
    AgentNotFoundError,
    AgentTimeoutError,
    AuthenticationError,
    CursorPipeError,
    RateLimitError,
    SessionError,
)
from cursorpipe._models import (
    ChatMessage,
    CliAssistantEvent,
    CliResultEvent,
    CompletionResult,
    JsonRpcRequest,
    TextPart,
    text_block,
)
from cursorpipe._ndjson import StreamAccumulator

# =========================================================================
# Config
# =========================================================================


@pytest.mark.unit
class TestConfig:
    def test_defaults(self) -> None:
        cfg = CursorPipeConfig()
        assert cfg.agent_bin == "agent"
        assert cfg.strategy == Strategy.AUTO
        assert cfg.default_mode == "ask"
        assert cfg.request_timeout_s == 300.0

    def test_custom_values(self) -> None:
        cfg = CursorPipeConfig(
            agent_bin="/usr/local/bin/agent",
            strategy=Strategy.SUBPROCESS,
            request_timeout_s=60,
        )
        assert cfg.agent_bin == "/usr/local/bin/agent"
        assert cfg.strategy == Strategy.SUBPROCESS
        assert cfg.request_timeout_s == 60

    def test_auth_env_resolution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSOR_API_KEY", "test-key-123")
        cfg = CursorPipeConfig()
        env = cfg.resolve_auth_env()
        assert env["CURSOR_API_KEY"] == "test-key-123"

    def test_auth_config_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSOR_API_KEY", "env-key")
        cfg = CursorPipeConfig(api_key="config-key")
        env = cfg.resolve_auth_env()
        assert env["CURSOR_API_KEY"] == "config-key"

    def test_auth_args_with_api_key(self) -> None:
        cfg = CursorPipeConfig(api_key="my-key")
        assert cfg.resolve_auth_args() == ["--api-key", "my-key"]

    def test_auth_args_empty_when_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        cfg = CursorPipeConfig()
        assert cfg.resolve_auth_args() == []

    def test_auth_args_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CURSOR_API_KEY", "env-key-456")
        cfg = CursorPipeConfig()
        assert cfg.resolve_auth_args() == ["--api-key", "env-key-456"]


# =========================================================================
# Models
# =========================================================================


@pytest.mark.unit
class TestModels:
    def test_text_block_helper(self) -> None:
        part = text_block("hello")
        assert isinstance(part, TextPart)
        assert part.type == "text"
        assert part.text == "hello"

    def test_chat_message(self) -> None:
        msg = ChatMessage(role="user", content="test prompt")
        assert msg.role == "user"
        assert msg.content == "test prompt"

    def test_completion_result(self) -> None:
        r = CompletionResult(text="SELECT 1", model="gpt-5.4-mini-medium", duration_ms=1234)
        assert r.text == "SELECT 1"
        assert r.model == "gpt-5.4-mini-medium"
        assert r.duration_ms == 1234

    def test_json_rpc_request_serialization(self) -> None:
        req = JsonRpcRequest(id=1, method="session/new", params={"cwd": "/tmp"})
        data = json.loads(req.model_dump_json())
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["method"] == "session/new"
        assert data["params"]["cwd"] == "/tmp"

    def test_cli_assistant_event_text(self) -> None:
        event = CliAssistantEvent(
            message={
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world"},
                ]
            }
        )
        assert event.text == "Hello world"

    def test_cli_assistant_event_empty(self) -> None:
        event = CliAssistantEvent(message={})
        assert event.text == ""

    def test_cli_result_event(self) -> None:
        event = CliResultEvent(subtype="success", result="done", duration_ms=500)
        assert event.subtype == "success"
        assert not event.is_error


# =========================================================================
# Errors
# =========================================================================


@pytest.mark.unit
class TestErrors:
    def test_all_inherit_from_base(self) -> None:
        errors = [
            AgentNotFoundError(["/usr/bin/agent"]),
            AuthenticationError("bad token"),
            AgentTimeoutError(30.0),
            RateLimitError(60.0),
            AgentCrashError(1, "segfault"),
            SessionError("failed", "sess-123"),
        ]
        for err in errors:
            assert isinstance(err, CursorPipeError)
            assert isinstance(err, Exception)

    def test_agent_not_found_details(self) -> None:
        err = AgentNotFoundError(["/usr/bin/agent", "/home/user/.local/bin/agent"])
        assert "/usr/bin/agent" in str(err)
        assert len(err.searched_paths) == 2

    def test_rate_limit_retry_after(self) -> None:
        err = RateLimitError(retry_after_s=42.0)
        assert err.retry_after_s == 42.0
        assert "42.0s" in str(err)

    def test_agent_crash_stderr(self) -> None:
        err = AgentCrashError(137, "out of memory")
        assert err.exit_code == 137
        assert "out of memory" in str(err)

    def test_session_error_with_id(self) -> None:
        err = SessionError("timeout", "sess-abc")
        assert "sess-abc" in str(err)

    def test_catch_broadly(self) -> None:
        """Callers can catch CursorPipeError to handle all library errors."""
        try:
            raise RateLimitError(10)
        except CursorPipeError as e:
            assert isinstance(e, RateLimitError)


# =========================================================================
# NDJSON StreamAccumulator
# =========================================================================


@pytest.mark.unit
class TestStreamAccumulator:
    def test_simple_assistant_event(self) -> None:
        acc = StreamAccumulator()
        delta = acc.feed({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello world"}]},
        })
        assert delta == "Hello world"
        assert acc.text == "Hello world"
        assert not acc.done

    def test_incremental_deltas(self) -> None:
        acc = StreamAccumulator()
        d1 = acc.feed({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello"}]},
        })
        assert d1 == "Hello"

        d2 = acc.feed({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello world"}]},
        })
        assert d2 == " world"
        assert acc.text == "Hello world"

    def test_duplicate_suppression(self) -> None:
        acc = StreamAccumulator()
        acc.feed({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello"}]},
        })
        d2 = acc.feed({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello"}]},
        })
        assert d2 == ""

    def test_result_event_marks_done(self) -> None:
        acc = StreamAccumulator()
        acc.feed({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hi"}]},
        })
        acc.feed({"type": "result", "subtype": "success", "result": "Hi"})
        assert acc.done
        assert acc.text == "Hi"

    def test_events_after_done_ignored(self) -> None:
        acc = StreamAccumulator()
        acc.feed({"type": "result", "subtype": "success", "result": "done"})
        assert acc.done

        d = acc.feed({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "ignored"}]},
        })
        assert d == ""

    def test_non_assistant_events_return_empty(self) -> None:
        acc = StreamAccumulator()
        assert acc.feed({"type": "system", "subtype": "init"}) == ""
        assert acc.feed({"type": "user", "message": {}}) == ""
        assert acc.feed({"type": "tool_call", "subtype": "started"}) == ""

    def test_result_provides_text_when_no_prior_chunks(self) -> None:
        """When using --output-format json, there are no assistant events."""
        acc = StreamAccumulator()
        d = acc.feed({
            "type": "result",
            "subtype": "success",
            "result": "The final answer",
            "duration_ms": 1234,
        })
        assert d == "The final answer"
        assert acc.text == "The final answer"
        assert acc.done
