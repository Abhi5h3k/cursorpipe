"""Compatibility module for projects with an existing generate/chat/close interface.

Exposes module-level ``generate()``, ``chat()``, and ``close()`` functions
so you can swap in cursorpipe with a single import-path change::

    from cursorpipe import _compat as my_llm_client
    result = await my_llm_client.generate(model="...", prompt="...")
"""

from __future__ import annotations

from cursorpipe._client import CursorClient
from cursorpipe._config import CursorPipeConfig

_client: CursorClient | None = None


def _get_client() -> CursorClient:
    global _client
    if _client is None:
        _client = CursorClient(CursorPipeConfig())
    return _client


async def generate(
    model: str,
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0,
    max_tokens: int = 2048,
) -> str:
    """Generate a completion — drop-in for ``cursor_client.generate()``."""
    return await _get_client().generate(
        model=model,
        prompt=prompt,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def chat(
    model: str,
    messages: list[dict],
    *,
    temperature: float = 0,
    max_tokens: int = 2048,
) -> str:
    """Chat completion — drop-in for ``cursor_client.chat()``."""
    return await _get_client().chat(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def close() -> None:
    """Shut down the shared client."""
    global _client
    if _client:
        await _client.close()
        _client = None
