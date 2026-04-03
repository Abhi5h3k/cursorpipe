"""cursorpipe — Async Python client for the Cursor Agent CLI.

Pipe prompts to frontier LLMs through Cursor's Agent Client Protocol (ACP)
with persistent sessions, streaming, and per-call model selection.

Quick start::

    from cursorpipe import CursorClient

    client = CursorClient()
    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Explain Python's GIL in one paragraph.",
    )

Module-level convenience (uses a default singleton)::

    from cursorpipe import generate, chat, close

    text = await generate(model="gpt-5.4-mini-medium", prompt="Hello!")
    await close()

Multi-turn sessions with server-side history::

    async with client.session("claude-4.5-sonnet-thinking") as s:
        r1 = await s.prompt("Generate SQL for top 10 users")
        r2 = await s.prompt("Add a date filter to that query")
"""

from __future__ import annotations

from cursorpipe._client import CursorClient
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
from cursorpipe._models import ChatMessage, CompletionResult, StreamChunk
from cursorpipe._session import CursorSession

__all__ = [
    # Client
    "CursorClient",
    "CursorSession",
    # Config
    "CursorPipeConfig",
    "Strategy",
    # Models
    "ChatMessage",
    "CompletionResult",
    "StreamChunk",
    # Errors
    "CursorPipeError",
    "AgentNotFoundError",
    "AuthenticationError",
    "AgentTimeoutError",
    "RateLimitError",
    "AgentCrashError",
    "SessionError",
    # Module-level convenience
    "generate",
    "chat",
    "warmup",
    "close",
]

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Module-level convenience functions (lazy singleton)
# ---------------------------------------------------------------------------

_default_client: CursorClient | None = None


def _get_default() -> CursorClient:
    global _default_client
    if _default_client is None:
        _default_client = CursorClient()
    return _default_client


async def generate(
    model: str,
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0,
    max_tokens: int = 2048,
) -> str:
    """Generate a completion using the default client singleton."""
    return await _get_default().generate(
        model=model, prompt=prompt, system=system,
        temperature=temperature, max_tokens=max_tokens,
    )


async def chat(
    model: str,
    messages: list[dict],
    *,
    temperature: float = 0,
    max_tokens: int = 2048,
) -> str:
    """Chat completion using the default client singleton."""
    return await _get_default().chat(
        model=model, messages=messages,
        temperature=temperature, max_tokens=max_tokens,
    )


async def warmup(pool_size: int = 5) -> None:
    """Pre-start the ACP process and fill the session dispenser."""
    await _get_default().warmup(pool_size=pool_size)


async def close() -> None:
    """Shut down the default client singleton."""
    global _default_client
    if _default_client:
        await _default_client.close()
        _default_client = None
