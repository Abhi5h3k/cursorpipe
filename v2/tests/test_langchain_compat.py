"""LangChain `ChatOpenAI` compatibility tests.

These exercise cursorpipe v2 end-to-end through the real OpenAI Python SDK
and LangChain's `ChatOpenAI`. The OpenAI async client is wired to our
FastAPI app via `httpx.ASGITransport`, so no network or API key is needed —
the underlying cursor-sdk is mocked through the standard conftest fixtures.

What this catches that the raw-httpx tests don't:
- OpenAI SDK response-shape strictness (model, choices, finish_reason, …).
- SSE chunk framing parsed by the OpenAI streaming parser.
- Custom headers (X-Cursor-Session-ID) surviving openai → httpx → FastAPI.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from dotenv import load_dotenv

pytest.importorskip("langchain_openai")
pytest.importorskip("openai")

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from cursorpipe._session_store import SessionStore

load_dotenv(Path(__file__).parent.parent / ".env")

skip_no_api_key = pytest.mark.skipif(
    not os.getenv("CURSOR_API_KEY"),
    reason="CURSOR_API_KEY not set — skipping integration tests",
)
TEST_MODEL = os.getenv("CURSORPIPE_TEST_MODEL", "auto")


@asynccontextmanager
async def _noop_lifespan(app):
    yield


def _make_app(mock_cursor_client):
    """Build a cursorpipe FastAPI app with the SDK bridge mocked out."""
    from cursorpipe_server.app import create_app

    with patch("cursorpipe_server.app.lifespan", _noop_lifespan):
        app = create_app()

    store = SessionStore()
    app.state.cursor_client = mock_cursor_client
    app.state.session_store = store
    return app, store


@asynccontextmanager
async def _openai_http_client(app, default_headers: dict | None = None):
    """An httpx.AsyncClient that routes OpenAI SDK calls into our ASGI app."""
    transport = httpx.ASGITransport(app=app)
    headers = default_headers or {}
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=headers,
    ) as client:
        yield client


def _make_chat(http_client, *, default_headers: dict | None = None) -> ChatOpenAI:
    """Build a ChatOpenAI wired to our in-process app."""
    return ChatOpenAI(
        base_url="http://test/v1",
        api_key="not-needed",
        model="composer-2.5",
        http_async_client=http_client,
        default_headers=default_headers or {},
        max_retries=0,
        timeout=30,
    )


# ── Stateless ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestLangChainStateless:
    """ChatOpenAI talking to cursorpipe without a session header."""

    async def test_ainvoke_returns_content(self, mock_cursor_client) -> None:
        app, store = _make_app(mock_cursor_client)
        try:
            async with _openai_http_client(app) as http:
                llm = _make_chat(http)
                response = await llm.ainvoke("Reply with PONG.")
            assert response.content == "PONG"
            assert response.response_metadata.get("model_name") == "composer-2.5"
        finally:
            await store.stop_cleanup()

    async def test_ainvoke_with_system_message(self, mock_cursor_client) -> None:
        """System + Human messages flow through without parser errors.

        Note: cursorpipe's stateless path currently drops the system prompt
        (see `_flatten_messages` in `cursorpipe/_client.py` — it returns
        `(prompt, system)` but `complete()` does `prompt, _ = ...`). This
        test pins that current behavior; once system prompts are forwarded
        the second assertion should be flipped to `in`.
        """
        app, store = _make_app(mock_cursor_client)
        try:
            async with _openai_http_client(app) as http:
                llm = _make_chat(http)
                response = await llm.ainvoke(
                    [
                        SystemMessage(content="You are terse."),
                        HumanMessage(content="Say PONG."),
                    ]
                )
            assert response.content == "PONG"
            sent_prompt = mock_cursor_client.agents.create.return_value.send.call_args.args[0]
            assert "Say PONG." in sent_prompt
            assert "You are terse." not in sent_prompt  # known limitation
        finally:
            await store.stop_cleanup()

    async def test_astream_yields_chunks(self, mock_cursor_client) -> None:
        """astream() must parse SSE chunks and reconstruct the assistant text."""
        app, store = _make_app(mock_cursor_client)
        try:
            async with _openai_http_client(app) as http:
                llm = _make_chat(http)
                pieces: list[str] = []
                async for chunk in llm.astream("Reply with PONG."):
                    if chunk.content:
                        pieces.append(chunk.content)
            assert "".join(pieces) == "PONG"
        finally:
            await store.stop_cleanup()


# ── Stateful ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestLangChainStateful:
    """ChatOpenAI pinned to a session via the X-Cursor-Session-ID header."""

    async def test_session_header_creates_session(self, mock_cursor_client) -> None:
        app, store = _make_app(mock_cursor_client)
        session_id = "lc-stateful-1"
        try:
            async with _openai_http_client(app) as http:
                llm = _make_chat(http, default_headers={"X-Cursor-Session-ID": session_id})
                response = await llm.ainvoke("Remember the word BANANA.")
            assert response.content == "PONG"
            assert store.active_count == 1
            assert store.list_all()[0].session_id == session_id
        finally:
            await store.stop_cleanup()

    async def test_two_turns_reuse_same_agent(self, mock_cursor_client) -> None:
        """Two ainvoke calls with the same session header share one Agent."""
        app, store = _make_app(mock_cursor_client)
        session_id = "lc-stateful-2"
        try:
            async with _openai_http_client(app) as http:
                llm = _make_chat(http, default_headers={"X-Cursor-Session-ID": session_id})
                await llm.ainvoke("First turn.")
                await llm.ainvoke("Second turn.")
            assert store.active_count == 1
            # agents.create() must only have been called once for the whole session.
            assert mock_cursor_client.agents.create.call_count == 1
            # And send() must have been called twice on that single agent.
            agent = mock_cursor_client.agents.create.return_value
            assert agent.send.call_count == 2
        finally:
            await store.stop_cleanup()

    async def test_distinct_sessions_get_distinct_agents(self, mock_cursor_client) -> None:
        app, store = _make_app(mock_cursor_client)
        try:
            async with _openai_http_client(app) as http:
                llm_a = _make_chat(http, default_headers={"X-Cursor-Session-ID": "sess-A"})
                llm_b = _make_chat(http, default_headers={"X-Cursor-Session-ID": "sess-B"})
                await llm_a.ainvoke("hi A")
                await llm_b.ainvoke("hi B")
            assert store.active_count == 2
            assert mock_cursor_client.agents.create.call_count == 2
        finally:
            await store.stop_cleanup()


# ── Real-recall integration ──────────────────────────────────────────────────


@asynccontextmanager
async def _real_app_and_http():
    """Build a real cursorpipe app (full lifespan → real SDK bridge) and an
    httpx.AsyncClient wired into it via ASGITransport, so LangChain's
    ChatOpenAI talks to the real cursor-sdk without a network port.
    """
    from cursorpipe_server.app import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=120
        ) as http:
            yield app, http


@pytest.mark.integration
@skip_no_api_key
class TestLangChainRealRecall:
    """End-to-end: LangChain ChatOpenAI + real Cursor SDK actually remembers."""

    async def test_two_turns_recall_secret(self) -> None:
        """Turn 1 plants a secret; turn 2 must recall it via the same session."""
        session_id = "lc-integration-recall"
        async with _real_app_and_http() as (_app, http):
            llm = ChatOpenAI(
                base_url="http://test/v1",
                api_key="not-needed",
                model=TEST_MODEL,
                default_headers={"X-Cursor-Session-ID": session_id},
                http_async_client=http,
                max_retries=0,
                timeout=120,
            )
            await llm.ainvoke(
                "The secret code is BANANA. Reply with: ACK"
            )
            r2 = await llm.ainvoke(
                "What is the secret code? Reply with just the word."
            )
            assert "BANANA" in r2.content.upper(), (
                f"Expected BANANA in second turn, got: {r2.content[:200]}"
            )
            await http.delete(f"/v1/sessions/{session_id}")

    async def test_streaming_second_turn_recalls(self) -> None:
        """Same recall property must hold when the second turn is streamed."""
        session_id = "lc-integration-recall-stream"
        async with _real_app_and_http() as (_app, http):
            llm = ChatOpenAI(
                base_url="http://test/v1",
                api_key="not-needed",
                model=TEST_MODEL,
                default_headers={"X-Cursor-Session-ID": session_id},
                http_async_client=http,
                max_retries=0,
                timeout=120,
            )
            await llm.ainvoke("My favourite fruit is MANGO. Reply: ACK")

            pieces: list[str] = []
            async for chunk in llm.astream(
                "What is my favourite fruit? Reply with just the word."
            ):
                if chunk.content:
                    pieces.append(chunk.content)
            full = "".join(pieces)
            assert "MANGO" in full.upper(), (
                f"Expected MANGO in streamed second turn, got: {full[:200]}"
            )
            await http.delete(f"/v1/sessions/{session_id}")

    async def test_three_turn_chain(self) -> None:
        """Memory must accumulate, not just span two turns."""
        session_id = "lc-integration-recall-three"
        async with _real_app_and_http() as (_app, http):
            llm = ChatOpenAI(
                base_url="http://test/v1",
                api_key="not-needed",
                model=TEST_MODEL,
                default_headers={"X-Cursor-Session-ID": session_id},
                http_async_client=http,
                max_retries=0,
                timeout=120,
            )
            await llm.ainvoke("My name is Alice. Reply: ACK")
            await llm.ainvoke("My city is Tokyo. Reply: ACK")
            r3 = await llm.ainvoke(
                "What is my name and my city? Reply in the form 'NAME / CITY'."
            )
            text = r3.content.upper()
            assert "ALICE" in text and "TOKYO" in text, (
                f"Expected both Alice and Tokyo in turn 3, got: {r3.content[:200]}"
            )
            await http.delete(f"/v1/sessions/{session_id}")

    async def test_distinct_sessions_dont_leak(self) -> None:
        """Different X-Cursor-Session-ID values must be fully isolated."""
        async with _real_app_and_http() as (_app, http):
            llm_a = ChatOpenAI(
                base_url="http://test/v1",
                api_key="not-needed",
                model=TEST_MODEL,
                default_headers={"X-Cursor-Session-ID": "lc-isolate-A"},
                http_async_client=http,
                max_retries=0,
                timeout=120,
            )
            llm_b = ChatOpenAI(
                base_url="http://test/v1",
                api_key="not-needed",
                model=TEST_MODEL,
                default_headers={"X-Cursor-Session-ID": "lc-isolate-B"},
                http_async_client=http,
                max_retries=0,
                timeout=120,
            )
            await llm_a.ainvoke("The codeword is PURPLE. Reply: ACK")
            r_b = await llm_b.ainvoke(
                "What is the codeword? If you do not know, reply exactly: UNKNOWN."
            )
            # Session B must NOT see session A's secret.
            assert "PURPLE" not in r_b.content.upper(), (
                f"Session B leaked session A's secret: {r_b.content[:200]}"
            )

            await http.delete("/v1/sessions/lc-isolate-A")
            await http.delete("/v1/sessions/lc-isolate-B")

    async def test_no_session_header_is_stateless(self) -> None:
        """Without the header LangChain must get stateless behavior — no recall."""
        async with _real_app_and_http() as (_app, http):
            llm = ChatOpenAI(
                base_url="http://test/v1",
                api_key="not-needed",
                model=TEST_MODEL,
                http_async_client=http,
                max_retries=0,
                timeout=120,
            )
            await llm.ainvoke("Remember the magic word: ELEPHANT. Reply: ACK")
            r2 = await llm.ainvoke(
                "What was the magic word I just told you? "
                "If you do not know, reply exactly: UNKNOWN."
            )
            # Stateless: turn 2 has no access to turn 1's context.
            assert "ELEPHANT" not in r2.content.upper(), (
                f"Stateless call leaked prior turn: {r2.content[:200]}"
            )
