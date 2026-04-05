"""Unit tests — fast, no external dependencies.

Tests the internal components (config, models, resolve, NDJSON parser, errors,
session dispenser, JSON fast-path, and notification routing) without needing a
Cursor agent binary or network access.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

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

    def test_enable_profiling_default_false(self) -> None:
        cfg = CursorPipeConfig()
        assert cfg.enable_profiling is False

    def test_enable_profiling_set(self) -> None:
        cfg = CursorPipeConfig(enable_profiling=True)
        assert cfg.enable_profiling is True


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


# =========================================================================
# JSON fast-path (_json.py)
# =========================================================================


@pytest.mark.unit
class TestJsonFastpath:
    def test_loads_parses_valid_json(self) -> None:
        from cursorpipe._json import loads
        result = loads('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_dumps_serializes_dict(self) -> None:
        from cursorpipe._json import dumps
        result = dumps({"key": "value"})
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_loads_raises_on_invalid_json(self) -> None:
        from cursorpipe._json import loads
        with pytest.raises((ValueError, TypeError)):
            loads("not valid json {{{")

    def test_roundtrip(self) -> None:
        from cursorpipe._json import dumps, loads
        original = {"jsonrpc": "2.0", "id": 1, "method": "session/new"}
        assert loads(dumps(original)) == original


# =========================================================================
# Session Dispenser (_pool.py)
# =========================================================================


@pytest.mark.unit
class TestSessionDispenser:
    def _make_dispenser(self, session_ids: list[str] | None = None):
        """Create a dispenser with a mock transport."""
        from cursorpipe._pool import SessionDispenser

        mock_transport = MagicMock()
        ids = list(session_ids or [f"sess-{i}" for i in range(20)])
        mock_transport.create_session_raw = AsyncMock(side_effect=ids)

        dispenser = SessionDispenser(mock_transport, target_size=3)
        return dispenser, mock_transport

    async def test_warm_fills_queue(self) -> None:
        dispenser, transport = self._make_dispenser()
        await dispenser.warm(3)
        assert dispenser.available == 3
        assert transport.create_session_raw.call_count == 3

    async def test_acquire_returns_prewarmed_session(self) -> None:
        dispenser, _ = self._make_dispenser()
        await dispenser.warm(2)
        sid = await dispenser.acquire()
        assert sid == "sess-0"
        assert dispenser.available == 1

    async def test_acquire_when_empty_creates_on_demand(self) -> None:
        dispenser, transport = self._make_dispenser()
        sid = await dispenser.acquire()
        assert sid == "sess-0"
        assert transport.create_session_raw.call_count >= 1

    async def test_sessions_are_unique(self) -> None:
        dispenser, _ = self._make_dispenser()
        await dispenser.warm(5)
        acquired = set()
        for _ in range(5):
            sid = await dispenser.acquire()
            assert sid not in acquired
            acquired.add(sid)

    async def test_close_prevents_further_acquire(self) -> None:
        dispenser, _ = self._make_dispenser()
        await dispenser.warm(2)
        dispenser.close()
        with pytest.raises(SessionError):
            await dispenser.acquire()

    async def test_close_drains_queue(self) -> None:
        dispenser, _ = self._make_dispenser()
        await dispenser.warm(3)
        assert dispenser.available == 3
        dispenser.close()
        assert dispenser.available == 0


# =========================================================================
# Notification routing by sessionId
# =========================================================================


@pytest.mark.unit
class TestNotificationRouting:
    def _make_transport(self):
        """Create a minimal AcpTransport-like object for testing dispatch."""
        from cursorpipe._acp import AcpTransport
        from cursorpipe._config import CursorPipeConfig

        cfg = CursorPipeConfig()
        transport = AcpTransport(cfg)
        return transport

    def test_subscribe_returns_queue(self) -> None:
        transport = self._make_transport()
        queue = transport._subscribe("session/update", "sess-abc")
        assert isinstance(queue, asyncio.Queue)

    def test_dispatch_routes_to_correct_session(self) -> None:
        transport = self._make_transport()
        q1 = transport._subscribe("session/update", "sess-A")
        q2 = transport._subscribe("session/update", "sess-B")

        msg_a = {
            "method": "session/update",
            "params": {
                "sessionId": "sess-A",
                "update": {"sessionUpdate": "agent_message_chunk", "content": {"text": "hello"}},
            },
        }
        msg_b = {
            "method": "session/update",
            "params": {
                "sessionId": "sess-B",
                "update": {"sessionUpdate": "agent_message_chunk", "content": {"text": "world"}},
            },
        }

        transport._dispatch(msg_a)
        transport._dispatch(msg_b)

        assert q1.qsize() == 1
        assert q2.qsize() == 1
        assert q1.get_nowait() == msg_a
        assert q2.get_nowait() == msg_b

    def test_dispatch_does_not_cross_sessions(self) -> None:
        transport = self._make_transport()
        q1 = transport._subscribe("session/update", "sess-X")

        msg_other = {
            "method": "session/update",
            "params": {
                "sessionId": "sess-Y",
                "update": {"sessionUpdate": "agent_message_chunk", "content": {"text": "nope"}},
            },
        }
        transport._dispatch(msg_other)

        assert q1.empty()

    def test_unsubscribe_removes_queue(self) -> None:
        transport = self._make_transport()
        q = transport._subscribe("session/update", "sess-Z")
        transport._unsubscribe("session/update", "sess-Z", q)

        msg = {
            "method": "session/update",
            "params": {"sessionId": "sess-Z", "update": {}},
        }
        transport._dispatch(msg)
        assert q.empty()


# =========================================================================
# Active-requests counter (CursorClient + CursorSession)
# =========================================================================


@pytest.mark.unit
class TestActiveRequests:
    """Verify that CursorClient.active_requests tracks in-flight LLM calls."""

    def _make_client(self):
        """Return a CursorClient wired to mock transports."""
        from cursorpipe._client import CursorClient
        from cursorpipe._models import CompletionResult

        client = CursorClient()

        mock_acp = MagicMock()
        mock_acp.prompt = AsyncMock(
            return_value=CompletionResult(text="ok", model="m", session_id="s"),
        )

        async def _fake_stream(*a, **kw):
            yield "chunk1"
            yield "chunk2"

        mock_acp.prompt_stream = MagicMock(side_effect=_fake_stream)
        mock_acp.ensure_started = AsyncMock()
        mock_acp.dispenser = MagicMock()
        mock_acp.dispenser.acquire = AsyncMock(return_value="sess-test")

        client._acp = mock_acp
        client._config.strategy = Strategy.ACP
        return client

    def test_starts_at_zero(self) -> None:
        from cursorpipe._client import CursorClient

        client = CursorClient()
        assert client.active_requests == 0

    async def test_generate_increments_and_decrements(self) -> None:
        client = self._make_client()
        assert client.active_requests == 0
        await client.generate(model="m", prompt="hi")
        assert client.active_requests == 0

    async def test_generate_decrements_on_exception(self) -> None:
        client = self._make_client()
        client._acp.prompt = AsyncMock(side_effect=CursorPipeError("boom"))

        with pytest.raises(CursorPipeError):
            await client.generate(model="m", prompt="hi")
        assert client.active_requests == 0

    async def test_stream_increments_during_iteration(self) -> None:
        client = self._make_client()
        assert client.active_requests == 0

        chunks = []
        async for chunk in client.stream(model="m", prompt="hi"):
            assert client.active_requests == 1
            chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2"]
        assert client.active_requests == 0

    async def test_stream_decrements_on_exception(self) -> None:
        client = self._make_client()

        async def _exploding_stream(*a, **kw):
            yield "ok"
            raise CursorPipeError("stream boom")

        client._acp.prompt_stream = MagicMock(side_effect=_exploding_stream)

        with pytest.raises(CursorPipeError):
            async for _ in client.stream(model="m", prompt="hi"):
                pass
        assert client.active_requests == 0

    async def test_session_prompt_increments_and_decrements(self) -> None:
        client = self._make_client()

        async with client.session("m") as session:
            assert client.active_requests == 0
            await session.prompt("hi")
            assert client.active_requests == 0

    async def test_session_prompt_decrements_on_exception(self) -> None:
        client = self._make_client()
        client._acp.prompt = AsyncMock(side_effect=CursorPipeError("fail"))

        async with client.session("m") as session:
            with pytest.raises(CursorPipeError):
                await session.prompt("hi")
            assert client.active_requests == 0

    async def test_session_stream_prompt_increments_and_decrements(self) -> None:
        client = self._make_client()

        async with client.session("m") as session:
            chunks = []
            async for chunk in session.stream_prompt("hi"):
                assert client.active_requests == 1
                chunks.append(chunk)
            assert chunks == ["chunk1", "chunk2"]
            assert client.active_requests == 0

    async def test_concurrent_requests_stack(self) -> None:
        """Multiple overlapping generate() calls stack the counter."""
        client = self._make_client()
        observed: list[int] = []

        async def _slow_prompt(*a, **kw):
            from cursorpipe._models import CompletionResult

            observed.append(client.active_requests)
            await asyncio.sleep(0.01)
            return CompletionResult(text="ok", model="m", session_id="s")

        client._acp.prompt = AsyncMock(side_effect=_slow_prompt)

        await asyncio.gather(
            client.generate(model="m", prompt="a"),
            client.generate(model="m", prompt="b"),
        )
        assert client.active_requests == 0
        assert max(observed) == 2
