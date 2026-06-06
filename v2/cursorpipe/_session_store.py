"""Stateful session store: maps session IDs to live AsyncAgent instances.

Design notes
------------
- Each session owns exactly one AsyncAgent created via cursor_client.agents.create().
- Sessions are evicted after CURSORPIPE_SESSION_TTL_MINUTES of inactivity.
- A background asyncio task runs every 5 minutes to sweep stale sessions.
- All mutations are protected by asyncio.Lock (single event loop).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from cursor_sdk import LocalAgentOptions

from cursorpipe._config import settings

if TYPE_CHECKING:
    from cursor_sdk import AsyncAgent, AsyncClient


@dataclass
class SessionEntry:
    session_id: str
    agent: "AsyncAgent"
    model: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.last_used_at = datetime.now(timezone.utc)

    def is_expired(self, ttl_minutes: int) -> bool:
        age = datetime.now(timezone.utc) - self.last_used_at
        return age > timedelta(minutes=ttl_minutes)

    def to_dict(self) -> dict:
        return {
            "id": self.session_id,
            "model": self.model,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
        }


class SessionStore:
    """In-memory store for stateful SDK AsyncAgent sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionEntry] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    def start_cleanup(self) -> None:
        """Start the background TTL sweep. Call once from the server lifespan."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self) -> None:
        """Cancel the cleanup loop and close all open agents."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            for entry in list(self._sessions.values()):
                await _close_agent(entry.agent)
            self._sessions.clear()

    async def get_or_create(
        self,
        session_id: str,
        model: str,
        cursor_client: "AsyncClient",
    ) -> SessionEntry:
        """Return an existing session or create a new Agent for *session_id*."""
        async with self._lock:
            entry = self._sessions.get(session_id)
            if entry is not None:
                entry.touch()
                return entry

            agent = await cursor_client.agents.create(
                model=model,
                api_key=settings.cursor_api_key or None,
                local=LocalAgentOptions(cwd=settings.workspace),
            )
            entry = SessionEntry(session_id=session_id, agent=agent, model=model)
            self._sessions[session_id] = entry
            return entry

    async def create_new(self, model: str, cursor_client: "AsyncClient") -> SessionEntry:
        """Create a fresh session with an auto-generated UUID."""
        session_id = str(uuid.uuid4())
        return await self.get_or_create(session_id, model, cursor_client)

    async def get(self, session_id: str) -> SessionEntry | None:
        async with self._lock:
            entry = self._sessions.get(session_id)
            if entry is not None:
                entry.touch()
            return entry

    async def delete(self, session_id: str) -> bool:
        """Delete and close a session. Returns True if it existed."""
        async with self._lock:
            entry = self._sessions.pop(session_id, None)
            if entry is not None:
                await _close_agent(entry.agent)
                return True
            return False

    def list_all(self) -> list[SessionEntry]:
        """Return a snapshot of all active sessions (no lock needed for reads)."""
        return list(self._sessions.values())

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    # ── Internal ────────────────────────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        """Sweep stale sessions every 5 minutes."""
        while True:
            await asyncio.sleep(5 * 60)
            await self._evict_expired()

    async def _evict_expired(self) -> None:
        ttl = settings.session_ttl_minutes
        async with self._lock:
            stale = [sid for sid, e in self._sessions.items() if e.is_expired(ttl)]
            for sid in stale:
                entry = self._sessions.pop(sid)
                await _close_agent(entry.agent)


async def _close_agent(agent: "AsyncAgent") -> None:
    """Close an agent, swallowing any errors so cleanup never raises."""
    try:
        await agent.close()
    except Exception:
        pass
