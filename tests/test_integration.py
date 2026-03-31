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

    @pytest.fixture
    def sub_client(self) -> CursorClient:
        return CursorClient(CursorPipeConfig(strategy=Strategy.SUBPROCESS))

    async def test_simple_generate(self, sub_client: CursorClient) -> None:
        result = await sub_client.generate(
            model="claude-4.5-sonnet-thinking",
            prompt="Reply with exactly: INTEGRATION_TEST_OK",
        )
        assert len(result) > 0, "Empty response from generate()"
        await sub_client.close()

    async def test_generate_with_system(self, sub_client: CursorClient) -> None:
        result = await sub_client.generate(
            model="claude-4.5-sonnet-thinking",
            prompt="What is 2+2?",
            system="You are a math tutor. Always reply with just the number.",
        )
        assert "4" in result
        await sub_client.close()

    async def test_chat_with_messages(self, sub_client: CursorClient) -> None:
        result = await sub_client.chat(
            model="claude-4.5-sonnet-thinking",
            messages=[
                {"role": "system", "content": "Reply with exactly the word requested."},
                {"role": "user", "content": "Say: CHAT_OK"},
            ],
        )
        assert len(result) > 0
        await sub_client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestSubprocessStream:
    """Test stream() via subprocess transport."""

    @pytest.fixture
    def sub_client(self) -> CursorClient:
        return CursorClient(CursorPipeConfig(strategy=Strategy.SUBPROCESS))

    async def test_streaming(self, sub_client: CursorClient) -> None:
        chunks: list[str] = []
        async for chunk in sub_client.stream(
            model="claude-4.5-sonnet-thinking",
            prompt="Count from 1 to 5, one number per line.",
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

    @pytest.fixture
    def acp_client(self) -> CursorClient:
        return CursorClient(CursorPipeConfig(strategy=Strategy.ACP))

    async def test_simple_generate(self, acp_client: CursorClient) -> None:
        result = await acp_client.generate(
            model="claude-4.5-sonnet-thinking",
            prompt="Reply with exactly: ACP_TEST_OK",
        )
        assert len(result) > 0, "Empty response from ACP generate()"
        await acp_client.close()

    async def test_model_switching(self, acp_client: CursorClient) -> None:
        """Switching models between calls should work (different sessions)."""
        r1 = await acp_client.generate(
            model="claude-4.5-sonnet-thinking",
            prompt="Reply with: MODEL_A",
        )
        r2 = await acp_client.generate(
            model="gpt-5.4-mini-medium",
            prompt="Reply with: MODEL_B",
        )
        assert len(r1) > 0
        assert len(r2) > 0
        await acp_client.close()


@pytest.mark.integration
@skip_no_agent
@skip_no_auth
class TestAcpStream:
    """Test stream() via ACP transport."""

    async def test_streaming_via_acp(self) -> None:
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP))
        chunks: list[str] = []
        async for chunk in client.stream(
            model="claude-4.5-sonnet-thinking",
            prompt="Count from 1 to 5, one number per line.",
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
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP))
        async with client.session("claude-4.5-sonnet-thinking") as session:
            r1 = await session.prompt("Remember this number: 42. Just say OK.")
            assert len(r1.text) > 0

            r2 = await session.prompt("What number did I ask you to remember?")
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
        client = CursorClient(CursorPipeConfig(strategy=Strategy.ACP))
        async with client.session("claude-4.5-sonnet-thinking") as session:
            chunks: list[str] = []
            async for chunk in session.stream_prompt(
                "Write a haiku about Python programming."
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
        client = CursorClient(CursorPipeConfig(strategy=Strategy.AUTO))
        result = await client.generate(
            model="claude-4.5-sonnet-thinking",
            prompt="Reply with exactly: AUTO_OK",
        )
        assert len(result) > 0
        await client.close()
