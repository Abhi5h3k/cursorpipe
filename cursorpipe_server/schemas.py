"""OpenAI-compatible request / response schemas.

These Pydantic models mirror the OpenAI Chat Completions API so that any
client speaking that protocol (OpenAI SDK, LangChain, LiteLLM, Open WebUI,
curl, etc.) works out of the box against cursorpipe-server.
"""

from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = 0
    max_tokens: int | None = None


# ---------------------------------------------------------------------------
# Non-streaming response
# ---------------------------------------------------------------------------


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChoiceMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:24]}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)


# ---------------------------------------------------------------------------
# Streaming (SSE) chunk
# ---------------------------------------------------------------------------


class DeltaContent(BaseModel):
    role: str | None = None
    content: str | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaContent
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[StreamChoice]


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------


class ModelObject(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "cursor"


class ModelListResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelObject]


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    message: str
    type: str
    code: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
