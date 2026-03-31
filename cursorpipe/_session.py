"""CursorSession — multi-turn conversation with server-side history.

Use as an async context manager::

    async with client.session(model="claude-4.5-sonnet-thinking") as s:
        r1 = await s.prompt("Generate SQL for top 10 users")
        r2 = await s.prompt("Add a date filter")   # has full context of r1
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
    """

    def __init__(self, transport: AcpTransport, model: str) -> None:
        self._transport = transport
        self._model = model
        self._session_id: str | None = None
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

    async def __aenter__(self) -> CursorSession:
        await self._transport.ensure_started()
        self._session_id = await self._transport.get_or_create_session(self._model)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session_id:
            self._transport.drop_session(self._model)
            self._session_id = None

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
