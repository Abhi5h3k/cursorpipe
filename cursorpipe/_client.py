"""CursorClient — the main entry point for cursorpipe.

Provides ``generate()``, ``chat()``, ``stream()``, ``session()``,
``create_session()``, and ``warmup()`` with per-call model selection.
Dispatches to the ACP transport (persistent) or subprocess transport
(per-request) based on the configured strategy.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from cursorpipe._acp import AcpTransport
from cursorpipe._config import CursorPipeConfig, Strategy
from cursorpipe._errors import CursorPipeError
from cursorpipe._models import ChatMessage
from cursorpipe._session import CursorSession
from cursorpipe._subprocess import SubprocessTransport

logger = logging.getLogger(__name__)


def _messages_to_prompt(messages: list[ChatMessage] | list[dict]) -> str:
    """Flatten a message list into a single prompt string.

    Cursor CLI in ``--mode ask`` doesn't accept multi-message arrays, so we
    merge system/user/assistant turns into a structured prompt.
    """
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = msg.role
            content = msg.content
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


class CursorClient:
    """Async client for the Cursor Agent CLI.

    Parameters
    ----------
    config : CursorPipeConfig | None
        Explicit config.  When *None*, settings are loaded from env vars
        and ``.env`` automatically.
    """

    def __init__(self, config: CursorPipeConfig | None = None) -> None:
        self._config = config or CursorPipeConfig()
        self._acp: AcpTransport | None = None
        self._subprocess: SubprocessTransport | None = None

    @property
    def config(self) -> CursorPipeConfig:
        return self._config

    # ------------------------------------------------------------------
    # Transport selection
    # ------------------------------------------------------------------

    def _get_acp(self) -> AcpTransport:
        if self._acp is None:
            self._acp = AcpTransport(self._config)
        return self._acp

    def _get_subprocess(self) -> SubprocessTransport:
        if self._subprocess is None:
            self._subprocess = SubprocessTransport(self._config)
        return self._subprocess

    def _should_use_acp(self) -> bool:
        if self._config.strategy == Strategy.ACP:
            return True
        if self._config.strategy == Strategy.SUBPROCESS:
            return False
        return True  # AUTO defaults to ACP

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    async def warmup(self, pool_size: int = 5) -> None:
        """Pre-start the ACP process and fill the session dispenser.

        Call once at app startup (e.g., FastAPI lifespan, Chainlit startup)
        to eliminate cold-start latency on the first real request.

        Parameters
        ----------
        pool_size : int
            Number of virgin sessions to pre-create.
        """
        acp = self._get_acp()
        await acp.ensure_started()
        await acp.dispenser.warm(pool_size)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0,
        max_tokens: int = 2048,
        timeout_s: float | None = None,
    ) -> str:
        """Generate a completion.  Returns the response text.

        Parameters
        ----------
        model : str
            Model name (e.g. ``claude-4.5-sonnet-thinking``).
        prompt : str
            The user prompt.
        system : str
            Optional system instructions (merged into prompt for CLI).
        temperature, max_tokens : float, int
            Generation parameters (advisory — the agent may not honour all).
        timeout_s : float | None
            Per-request timeout.  Falls back to config default.
        """
        full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt

        if self._should_use_acp():
            try:
                result = await self._get_acp().prompt(
                    model, full_prompt, timeout_s=timeout_s,
                )
                return result.text
            except CursorPipeError:
                if self._config.strategy == Strategy.ACP:
                    raise
                logger.warning("ACP failed, falling back to subprocess")

        result = await self._get_subprocess().generate(
            model, full_prompt, timeout_s=timeout_s,
        )
        return result.text

    async def chat(
        self,
        model: str,
        messages: list[dict] | list[ChatMessage],
        *,
        temperature: float = 0,
        max_tokens: int = 2048,
        timeout_s: float | None = None,
    ) -> str:
        """Chat completion with a message history.  Returns response text.

        Messages are flattened into a single prompt since the Cursor CLI
        doesn't accept multi-message arrays natively.  For true multi-turn
        with server-side history, use ``session()`` or ``create_session()``
        instead.
        """
        flat = _messages_to_prompt(messages)
        return await self.generate(
            model, flat, timeout_s=timeout_s,
            temperature=temperature, max_tokens=max_tokens,
        )

    async def stream(
        self,
        model: str,
        prompt: str,
        *,
        system: str = "",
        timeout_s: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream a completion, yielding text chunks as they arrive."""
        full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt

        if self._should_use_acp():
            try:
                async for chunk in self._get_acp().prompt_stream(
                    model, full_prompt, timeout_s=timeout_s,
                ):
                    yield chunk
                return
            except CursorPipeError:
                if self._config.strategy == Strategy.ACP:
                    raise
                logger.warning("ACP streaming failed, falling back to subprocess")

        async for chunk in self._get_subprocess().generate_stream(
            model, full_prompt, timeout_s=timeout_s,
        ):
            yield chunk

    def session(self, model: str) -> CursorSession:
        """Create a multi-turn session with server-side history (ACP only).

        Usage as a context manager::

            async with client.session("claude-4.5-sonnet-thinking") as s:
                r1 = await s.prompt("Generate SQL for ...")
                r2 = await s.prompt("Now add a WHERE clause")
        """
        return CursorSession(self._get_acp(), model)

    async def create_session(self, model: str) -> CursorSession:
        """Create a multi-turn session with explicit lifecycle control.

        Unlike ``session()`` (a context manager), this returns a ready-to-use
        session that you manage yourself — ideal for frameworks like Chainlit
        or FastAPI where creation, usage, and cleanup happen in different
        callback functions.

        Call ``session.discard()`` when done.

        Usage::

            session = await client.create_session("claude-4.5-sonnet-thinking")
            r1 = await session.prompt("Generate SQL for ...")
            r2 = await session.prompt("Now add a WHERE clause")
            session.discard()
        """
        acp = self._get_acp()
        await acp.ensure_started()
        sid = await acp.dispenser.acquire()
        return CursorSession(acp, model, session_id=sid)

    async def list_models(self) -> list[str]:
        """Discover available models via ``agent --list-models``."""
        import asyncio
        import os

        from cursorpipe._resolve import resolve_agent_command

        cmd = resolve_agent_command(self._config)
        auth_args = self._config.resolve_auth_args()
        env = {**os.environ, **self._config.resolve_auth_env()}
        proc = await asyncio.create_subprocess_exec(
            *cmd, *auth_args, "--list-models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode("utf-8", errors="replace").strip().splitlines()
        return [line.strip() for line in lines if line.strip()]

    async def close(self) -> None:
        """Shut down transports and release resources."""
        if self._acp:
            await self._acp.close()
            self._acp = None
        self._subprocess = None
