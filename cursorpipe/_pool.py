"""Session dispenser — pre-creates virgin ACP sessions for zero-latency acquire.

Each session is used once then discarded (never returned to the pool).  This
guarantees conversation-history isolation between requests and users without
the library needing any concept of "user identity".

Background refill keeps the queue topped up so the next request gets an instant
session even if the previous batch was consumed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from cursorpipe._errors import SessionError

if TYPE_CHECKING:
    from cursorpipe._acp import AcpTransport

logger = logging.getLogger(__name__)

_DEFAULT_POOL_SIZE = 5


class SessionDispenser:
    """Pre-creates virgin ACP sessions.  Each is used once, then discarded.

    Parameters
    ----------
    transport : AcpTransport
        The transport used to send ``session/new`` RPCs.
    target_size : int
        Number of sessions to keep ready in the queue.
    """

    def __init__(self, transport: AcpTransport, target_size: int = _DEFAULT_POOL_SIZE) -> None:
        self._transport = transport
        self._target = target_size
        self._ready: asyncio.Queue[str] = asyncio.Queue()
        self._refill_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def available(self) -> int:
        """Number of pre-created sessions ready for immediate use."""
        return self._ready.qsize()

    @property
    def target_size(self) -> int:
        return self._target

    async def warm(self, count: int | None = None) -> None:
        """Pre-create *count* sessions (defaults to *target_size*).

        Called during ``client.warmup()``.  Blocks until all sessions are ready.
        """
        n = count or self._target
        for _ in range(n):
            sid = await self._transport.create_session_raw()
            self._ready.put_nowait(sid)
        logger.info("Session dispenser warmed with %d sessions", n)

    async def acquire(self) -> str:
        """Get a virgin session ID.

        Pops from the pre-created queue (O(1)).  If the queue is empty, falls
        back to creating a session on-demand (slower, logs a warning).
        """
        if self._closed:
            raise SessionError("Session dispenser is closed", None)

        if not self._ready.empty():
            sid = self._ready.get_nowait()
        else:
            logger.warning(
                "Session dispenser empty — creating session on-demand. "
                "Consider increasing pool_size or calling warmup() earlier."
            )
            sid = await self._transport.create_session_raw()

        self._maybe_refill()
        return sid

    def _maybe_refill(self) -> None:
        """Trigger background refill if below target size."""
        if self._closed:
            return
        if self._ready.qsize() < self._target and (
            self._refill_task is None or self._refill_task.done()
        ):
            self._refill_task = asyncio.create_task(self._refill())

    async def _refill(self) -> None:
        """Background task: create sessions until the queue reaches target size."""
        while self._ready.qsize() < self._target and not self._closed:
            try:
                sid = await self._transport.create_session_raw()
                self._ready.put_nowait(sid)
                logger.debug("Session dispenser refilled to %d", self._ready.qsize())
            except Exception:
                logger.debug("Session dispenser refill failed, will retry later", exc_info=True)
                break

    def close(self) -> None:
        """Stop background refill and discard queued sessions."""
        self._closed = True
        if self._refill_task and not self._refill_task.done():
            self._refill_task.cancel()
        # Drain the queue
        while not self._ready.empty():
            try:
                self._ready.get_nowait()
            except asyncio.QueueEmpty:
                break
