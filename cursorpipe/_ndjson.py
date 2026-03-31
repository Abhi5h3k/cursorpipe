"""Async NDJSON parser for Cursor CLI ``--output-format stream-json`` output.

Parses newline-delimited JSON events from the agent subprocess stdout and
yields structured events.  Handles the deduplication needed because the CLI
emits partial deltas followed by a full assistant message.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)


async def iter_ndjson_lines(stream: asyncio.StreamReader) -> AsyncIterator[dict[str, Any]]:
    """Yield parsed JSON objects from a newline-delimited stream."""
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            yield json.loads(text)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON line: %s", text[:200])


class StreamAccumulator:
    """Accumulates assistant text from stream-json events.

    Handles the Cursor CLI pattern where partial ``assistant`` events are
    emitted as streaming deltas, and the final ``assistant`` event contains
    the full text (which we must de-duplicate).
    """

    def __init__(self) -> None:
        self._accumulated: str = ""
        self._done: bool = False
        self._result_event: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        return self._accumulated

    @property
    def done(self) -> bool:
        return self._done

    @property
    def result(self) -> dict[str, Any] | None:
        return self._result_event

    def feed(self, event: dict[str, Any]) -> str:
        """Process one NDJSON event.  Returns the NEW delta text (may be empty)."""
        if self._done:
            return ""

        event_type = event.get("type", "")

        if event_type == "assistant":
            message = event.get("message", {})
            content = message.get("content", [])
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
            if not text:
                return ""
            # De-duplicate: if the new text is a superset of what we have,
            # only emit the delta portion.
            if text.startswith(self._accumulated) and len(self._accumulated) > 0:
                delta = text[len(self._accumulated) :]
                self._accumulated = text
                return delta
            if text == self._accumulated:
                return ""
            # New chunk that doesn't overlap — append it.
            delta = text
            self._accumulated += text
            return delta

        if event_type == "result":
            self._done = True
            self._result_event = event
            final_text = event.get("result", "")
            if final_text and not self._accumulated:
                self._accumulated = final_text
                return final_text
            return ""

        return ""
