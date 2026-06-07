"""OpenAI-compatible request and response Pydantic models."""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Request ─────────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = "user"
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    # Accept and silently ignore unknown OpenAI fields (stream_options,
    # logit_bias, top_p, frequency_penalty, etc.) so clients never get 422s
    # for fields cursorpipe doesn't implement.
    model_config = ConfigDict(extra="ignore")

    model: str = Field(default="composer-2.5")
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


# ── Non-streaming response ───────────────────────────────────────────────────────


class ChatCompletionMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    reasoning_content: str | None = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionMessage
    finish_reason: Literal["stop", "length"] = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CursorMetadata(BaseModel):
    duration_ms: int = 0
    run_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    thinking: str | None = None
    thinking_duration_ms: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageInfo = Field(default_factory=UsageInfo)
    cursor_metadata: CursorMetadata = Field(default_factory=CursorMetadata)


# ── Streaming response (SSE chunks) ─────────────────────────────────────────────


class DeltaMessage(BaseModel):
    role: Literal["assistant"] | None = None
    content: str | None = None
    reasoning_content: str | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: Literal["stop", "length"] | None = None


class ChatCompletionChunk(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[StreamChoice]


# ── Models endpoint ──────────────────────────────────────────────────────────────


class ModelParamValueDef(BaseModel):
    """One accepted value for a model parameter (e.g. value="high")."""

    value: str
    display_name: str = ""


class ModelParamDef(BaseModel):
    """A per-model parameter definition exposed by the Cursor SDK (e.g. thinking)."""

    id: str
    display_name: str = ""
    values: list[ModelParamValueDef] = Field(default_factory=list)


class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "cursor"
    # cursorpipe extension: per-model parameters from the SDK (e.g. thinking=low|high).
    # Standard OpenAI clients will ignore this field.
    cursor_parameters: list[ModelParamDef] = Field(default_factory=list)


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]


# ── Sessions endpoint ────────────────────────────────────────────────────────────


class SessionInfo(BaseModel):
    id: str
    model: str
    created_at: str
    last_used_at: str


class SessionList(BaseModel):
    object: Literal["list"] = "list"
    data: list[SessionInfo]


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str = Field(default="composer-2.5")
