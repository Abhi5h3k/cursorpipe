"""CursorSession — multi-turn conversation with server-side history.

Use as an async context manager::

    async with client.session(model="claude-4.5-sonnet-thinking") as s:
        r1 = await s.prompt("Generate SQL for top 10 users")
        r2 = await s.prompt("Add a date filter")   # has full context of r1

Or with explicit lifecycle (for frameworks like Chainlit)::

    session = await client.create_session("claude-4.5-sonnet-thinking")
    r1 = await session.prompt("Generate SQL for top 10 users")
    session.discard()
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from cursorpipe._models import CompletionResult

if TYPE_CHECKING:
    from cursorpipe._acp import AcpTransport

logger = logging.getLogger(__name__)


class CursorSession:
    """A multi-turn conversation backed by an ACP session.

    The Cursor agent maintains conversation history server-side, so
    follow-up prompts automatically have full context without resending
    the message list.

    Parameters
    ----------
    transport : AcpTransport
        The underlying ACP transport.
    model : str
        Default model for prompts in this session.
    session_id : str | None
        Pre-acquired session ID.  When *None*, a session is acquired from
        the dispenser on first use (or on ``__aenter__``).
    """

    def __init__(
        self,
        transport: AcpTransport,
        model: str,
        *,
        session_id: str | None = None,
    ) -> None:
        self._transport = transport
        self._model = model
        self._session_id: str | None = session_id
        self._turn_count: int = 0

    @property
    def model(self) -> str:
        return self._model

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def turn_count(self) -> int:
        return self._turn_count

    # ------------------------------------------------------------------
    # Context manager (async with client.session(...) as s)
    # ------------------------------------------------------------------

    async def __aenter__(self) -> CursorSession:
        await self._transport.ensure_started()
        if self._session_id is None:
            self._session_id = await self._transport.dispenser.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.discard()

    # ------------------------------------------------------------------
    # Explicit lifecycle
    # ------------------------------------------------------------------

    def discard(self) -> None:
        """Release this session.  No-op if already discarded.

        After discard, further ``prompt()`` / ``stream_prompt()`` calls will
        raise.  The session is NOT returned to any pool — history isolation
        is guaranteed.
        """
        self._session_id = None

    # ------------------------------------------------------------------
    # Prompting
    # ------------------------------------------------------------------

    async def prompt(self, text: str, *, timeout_s: float | None = None) -> CompletionResult:
        """Send a prompt within this session.  History is preserved server-side."""
        if self._session_id is None:
            await self.__aenter__()
        assert self._session_id is not None

        result = await self._transport.prompt(
            self._model,
            text,
            session_id=self._session_id,
            timeout_s=timeout_s,
        )
        self._turn_count += 1
        return result

    async def stream_prompt(
        self, text: str, *, timeout_s: float | None = None
    ) -> AsyncIterator[str]:
        """Send a prompt and yield text chunks as they arrive."""
        if self._session_id is None:
            await self.__aenter__()
        assert self._session_id is not None

        self._turn_count += 1
        async for chunk in self._transport.prompt_stream(
            self._model,
            text,
            session_id=self._session_id,
            timeout_s=timeout_s,
        ):
            yield chunk
