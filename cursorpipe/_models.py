"""Data models for cursorpipe.

Content uses an extensible ``ContentPart`` union so multimodal support
(images, files) can be added later without changing the transport layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Content parts (extensible for future multimodal)
# ---------------------------------------------------------------------------

class TextPart(BaseModel):
    """A plain-text content block."""

    type: Literal["text"] = "text"
    text: str


# Future: ImagePart, FilePart, etc. will be added here and included in the union.
ContentPart = TextPart


def text_block(text: str) -> TextPart:
    """Shortcut to build a TextPart."""
    return TextPart(text=text)


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """A single message in a conversation (OpenAI-style roles)."""

    role: Literal["system", "user", "assistant"] = "user"
    content: str


# ---------------------------------------------------------------------------
# Completion results
# ---------------------------------------------------------------------------

class CompletionResult(BaseModel):
    """The result of a generate / chat / session.prompt call."""

    text: str
    model: str = ""
    session_id: str = ""
    duration_ms: float = 0
    stop_reason: str = ""


class StreamChunk(BaseModel):
    """A single chunk emitted during streaming."""

    text: str
    done: bool = False


# ---------------------------------------------------------------------------
# ACP JSON-RPC envelope
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    """Outgoing JSON-RPC 2.0 request."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int
    method: str
    params: dict = Field(default_factory=dict)


class JsonRpcResponse(BaseModel):
    """Incoming JSON-RPC 2.0 response (may also be a notification)."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | None = None
    method: str | None = None
    result: dict | None = None
    error: dict | None = None
    params: dict | None = None


# ---------------------------------------------------------------------------
# Cursor CLI stream-json event types
# ---------------------------------------------------------------------------

class CliSystemEvent(BaseModel):
    """``type: system`` event from ``--output-format stream-json``."""

    type: Literal["system"] = "system"
    subtype: str = ""
    model: str = ""
    session_id: str = ""


class CliAssistantEvent(BaseModel):
    """``type: assistant`` event carrying model output text."""

    type: Literal["assistant"] = "assistant"
    message: dict = Field(default_factory=dict)

    @property
    def text(self) -> str:
        content = self.message.get("content", [])
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)


class CliResultEvent(BaseModel):
    """``type: result`` terminal event."""

    type: Literal["result"] = "result"
    subtype: str = ""
    is_error: bool = False
    result: str = ""
    duration_ms: float = 0
    session_id: str = ""
