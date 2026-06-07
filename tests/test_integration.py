"""Integration tests — require a running Cursor agent with valid auth.

These tests make REAL calls to the Cursor API through the agent CLI.
They are slow and consume API quota.

Run with:  pytest tests/test_integration.py -v -m integration
Skip with: pytest -m "not integration"
"""

from __future__ import annotations

import os
import subprocess

import pytest

from cursorpipe import CursorClient, CursorPipeConfig, Strategy
from cursorpipe._errors import AgentNotFoundError
from cursorpipe._resolve import resolve_agent_command

# Override via CURSORPIPE_TEST_MODEL to use a different model (e.g. one
# allowed by your Cursor admin policy).
TEST_MODEL = os.getenv("CURSORPIPE_TEST_MODEL", "auto")


def _agent_available() -> bool:
    try:
        resolve_agent_command(CursorPipeConfig())
        return True
    except AgentNotFoundError:
        return False


def _auth_available() -> bool:
    if os.getenv("CURSOR_API_KEY") or os.getenv("CURSOR_AUTH_TOKEN"):
        return True
    try:
        cmd = resolve_agent_command(CursorPipeConfig())
        result = subprocess.run(
            [*cmd, "status"], capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (AgentNotFoundError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


skip_no_agent = pytest.mark.skipif(not _agent_available(), reason="Cursor agent not installed")
skip_no_auth = pytest.mark.skipif(not _auth_available(), reason="Cursor auth not configured")


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestSubprocessGenerate:
    """Test generate() via subprocess transport."""

    async def test_simple_generate(self, sub_client: CursorClient) -> None:
        result = await sub_client.generate(
            model=TEST_MODEL,
            prompt="Reply with the single word: PONG",
        )
        assert "PONG" in result.upper(), f"Expected PONG in response, got: {result}"
        await sub_client.close()

    async def test_generate_with_system(self, sub_client: CursorClient) -> None:
        result = await sub_client.generate(
            model=TEST_MODEL,
            prompt="Reply with the single word: FOUR",
            system="Echo the exact word the user asks for. No other text.",
        )
        assert "FOUR" in result.upper(), f"Expected FOUR in response, got: {result}"
        await sub_client.close()

    async def test_chat_with_messages(self, sub_client: CursorClient) -> None:
        sys_prompt = "Echo the exact word the user asks for. No other text."
        result = await sub_client.chat(
            model=TEST_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "Reply with the single word: CHAT"},
            ],
        )
        assert "CHAT" in result.upper(), f"Expected CHAT in response, got: {result}"
        await sub_client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestSubprocessStream:
    """Test stream() via subprocess transport."""

    async def test_streaming(self, sub_client: CursorClient) -> None:
        chunks: list[str] = []
        async for chunk in sub_client.stream(
            model=TEST_MODEL,
            prompt="Reply with exactly three words: ONE TWO THREE",
        ):
            chunks.append(chunk)
        assert len(chunks) > 0, "No chunks received from stream()"
        full_text = "".join(chunks)
        assert len(full_text) > 0
        await sub_client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestAcpGenerate:
    """Test generate() via ACP transport."""

    async def test_simple_generate(self, acp_client: CursorClient) -> None:
        result = await acp_client.generate(
            model=TEST_MODEL,
            prompt="Reply with the single word: PING",
        )
        assert "PING" in result.upper(), f"Expected PING in response, got: {result}"
        await acp_client.close()

    async def test_consecutive_calls(self, acp_client: CursorClient) -> None:
        """Two consecutive ACP calls should both return responses.

        Note: ACP does NOT switch models per-call. The ACP process is started
        without --model, so Cursor auto-selects the model for every request
        regardless of the model argument. This test verifies that consecutive
        calls work correctly, not that a specific model is used.
        """
        r1 = await acp_client.generate(
            model=TEST_MODEL,
            prompt="Reply with the single word: ALPHA",
        )
        r2 = await acp_client.generate(
            model=TEST_MODEL,
            prompt="Reply with the single word: BETA",
        )
        assert "ALPHA" in r1.upper(), f"Expected ALPHA, got: {r1}"
        assert "BETA" in r2.upper(), f"Expected BETA, got: {r2}"
        await acp_client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestAcpStream:
    """Test stream() via ACP transport."""

    async def test_streaming_via_acp(self) -> None:
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP, request_timeout_s=60))
        chunks: list[str] = []
        async for chunk in client.stream(
            model=TEST_MODEL,
            prompt="Reply with exactly three words: ONE TWO THREE",
        ):
            chunks.append(chunk)
        assert len(chunks) > 0, "No chunks received from ACP stream()"
        full_text = "".join(chunks)
        assert len(full_text) > 0
        await client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestAcpSession:
    """Test multi-turn sessions via ACP."""

    async def test_multi_turn_session(self) -> None:
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP, request_timeout_s=60))
        async with client.session(TEST_MODEL) as session:
            r1 = await session.prompt("The code is 42. Reply with the single word: ACK")
            assert len(r1.text) > 0

            r2 = await session.prompt("What code did I give you? Reply with just the number.")
            assert "42" in r2.text, (
                f"Session history lost — model didn't recall '42'. Got: {r2.text[:200]}"
            )
            assert session.turn_count == 2
        await client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestAcpSessionStream:
    """Test streaming within a multi-turn session."""

    async def test_session_stream_prompt(self) -> None:
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP, request_timeout_s=60))
        async with client.session(TEST_MODEL) as session:
            chunks: list[str] = []
            async for chunk in session.stream_prompt(
                "Reply with exactly three words: ONE TWO THREE"
            ):
                chunks.append(chunk)
            assert len(chunks) > 0, "No chunks from session stream_prompt()"
            assert session.turn_count == 1
        await client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestModelDiscovery:
    """Test listing available models."""

    async def test_list_models(self) -> None:
        client = CursorClient()
        models = await client.list_models()
        assert len(models) > 0, "No models returned by list_models()"
        await client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestAutoFallback:
    """Test AUTO strategy falls back from ACP to subprocess."""

    async def test_auto_strategy_works(self) -> None:
        client = CursorClient(CursorPipeConfig(strategy=Strategy.AUTO, request_timeout_s=60))
        result = await client.generate(
            model=TEST_MODEL,
            prompt="Reply with the single word: PING",
        )
        assert len(result) > 0
        await client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestAutoModelRouting:
    """Test AUTO strategy model-aware transport routing.

    In AUTO mode, requests with a specific model name are routed through
    subprocess (so --model is passed correctly to the CLI). Requests with
    model="auto" stay on ACP for the warm-session benefit.
    """

    async def test_specific_model_uses_subprocess(self) -> None:
        """A specific model name should trigger subprocess transport in AUTO mode."""
        specific_model = os.getenv("CURSORPIPE_TEST_MODEL", "claude-4.5-sonnet-thinking")
        if specific_model == "auto":
            specific_model = "claude-4.5-sonnet-thinking"

        client = CursorClient(CursorPipeConfig(strategy=Strategy.AUTO, request_timeout_s=60))
        result = await client.generate(
            model=specific_model,
            prompt="Reply with the single word: SUBPROCESS",
        )
        assert len(result) > 0, "Expected a non-empty response"
        assert client._subprocess is not None, (
            "AUTO strategy with a specific model should have used the subprocess transport"
        )
        await client.close()

    async def test_auto_model_uses_acp(self) -> None:
        """model='auto' should keep the request on the ACP transport in AUTO mode."""
        client = CursorClient(CursorPipeConfig(strategy=Strategy.AUTO, request_timeout_s=60))
        result = await client.generate(
            model="auto",
            prompt="Reply with the single word: ACP",
        )
        assert len(result) > 0, "Expected a non-empty response"
        assert client._acp is not None, (
            "AUTO strategy with model='auto' should have used the ACP transport"
        )
        await client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestWarmup:
    """Test warmup pre-creates sessions for zero cold-start."""

    async def test_warmup_then_generate(self) -> None:
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP, request_timeout_s=60))
        await client.warmup(pool_size=2)

        acp = client._get_acp()
        assert acp.dispenser.available >= 1, "Warmup should pre-create sessions"

        result = await client.generate(
            model=TEST_MODEL,
            prompt="Reply with the single word: PING",
        )
        assert len(result) > 0
        await client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestExplicitSession:
    """Test create_session() with explicit lifecycle."""

    async def test_create_and_discard(self) -> None:
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP, request_timeout_s=60))
        await client.warmup(pool_size=2)

        session = await client.create_session(TEST_MODEL)
        assert session.session_id is not None

        r1 = await session.prompt("The code is 99. Reply with the single word: ACK")
        assert len(r1.text) > 0

        r2 = await session.prompt("What code did I give you? Reply with just the number.")
        assert "99" in r2.text

        session.discard()
        assert session.session_id is None

        await client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestSessionIsolation:
    """Test that different sessions don't share history."""

    async def test_two_sessions_isolated(self) -> None:
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP, request_timeout_s=60))
        await client.warmup(pool_size=3)

        s1 = await client.create_session(TEST_MODEL)
        s2 = await client.create_session(TEST_MODEL)

        assert s1.session_id != s2.session_id, "Sessions must have different IDs"

        await s1.prompt("The code word is BANANA. Reply with the single word: ACK")
        r2 = await s2.prompt(
            "Do you know a code word I gave you? Reply with YES or NO only."
        )
        assert "NO" in r2.text.upper(), (
            f"Session s2 should not know about BANANA. Got: {r2.text[:200]}"
        )

        s1.discard()
        s2.discard()
        await client.close()
