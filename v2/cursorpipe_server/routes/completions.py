"""POST /v1/chat/completions — OpenAI-compatible chat completions.

Session routing
---------------
No X-Cursor-Session-ID header  → stateless (one-shot per request)
Header present, known ID       → stateful (existing agent.send())
Header present, unknown ID     → stateful (create new agent, return ID in response header)

For stateful requests only the *last* user message is forwarded to agent.send()
because the SDK Agent already holds the full conversation history internally.

Thinking / cursor_params
------------------------
Per-request cursor_params (via extra_body) take priority over the global
CURSORPIPE_THINKING_LEVEL. When either is active, thinking chunks arrive as
delta.reasoning_content (streaming) or cursor_metadata.thinking (non-streaming).
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from cursorpipe._client import (
    StreamChunk,
    complete,
    complete_stateful,
    stream_complete,
    stream_complete_stateful,
)
from cursorpipe_server.schemas import (
    ChatCompletionChunk,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    CursorMetadata,
    DeltaMessage,
    StreamChoice,
)

router = APIRouter()

SESSION_HEADER = "X-Cursor-Session-ID"


def _last_user_message(messages: list) -> str:
    """Extract the content of the last user-role message."""
    for msg in reversed(messages):
        if msg.role == "user":
            content = msg.content or ""
            if isinstance(content, list):
                return " ".join(
                    b.get("text", "") for b in content if b.get("type") == "text"
                )
            return content
    return ""


def _messages_as_dicts(messages: list) -> list[dict]:
    return [m.model_dump(exclude_none=True) for m in messages]


# ── Main endpoint ────────────────────────────────────────────────────────────


@router.post("/v1/chat/completions", tags=["completions"])
async def chat_completions(request: Request, body: ChatCompletionRequest):
    cursor_client = request.app.state.cursor_client
    session_store = request.app.state.session_store

    incoming_session_id = request.headers.get(SESSION_HEADER, "").strip()
    is_stateful = bool(incoming_session_id)
    model = body.model or settings.model

    if is_stateful:
        return await _handle_stateful(
            body=body,
            model=model,
            incoming_session_id=incoming_session_id,
            cursor_client=cursor_client,
            session_store=session_store,
        )
    return await _handle_stateless(body=body, model=model, cursor_client=cursor_client)


# ── Stateless ────────────────────────────────────────────────────────────────


async def _handle_stateless(body: ChatCompletionRequest, model: str, cursor_client):
    messages = _messages_as_dicts(body.messages)
    cursor_params = body.cursor_params or None

    if body.stream:
        return EventSourceResponse(
            _stateless_stream_generator(messages, model, cursor_client, cursor_params),
            media_type="text/event-stream",
        )

    result = await complete(messages, model, cursor_client, cursor_params)
    return JSONResponse(
        ChatCompletionResponse(
            model=result.actual_model or model,
            choices=[
                ChatCompletionChoice(
                    message=ChatCompletionMessage(
                        content=result.text,
                        reasoning_content=result.thinking or None,
                    ),
                    finish_reason=result.finish_reason,  # type: ignore[arg-type]
                )
            ],
            cursor_metadata=CursorMetadata(
                duration_ms=result.duration_ms,
                run_id=result.run_id,
                agent_id=result.agent_id,
                thinking=result.thinking,
                thinking_duration_ms=result.thinking_duration_ms,
            ),
        ).model_dump(exclude_none=True)
    )


async def _stateless_stream_generator(
    messages: list[dict],
    model: str,
    cursor_client,
    cursor_params: dict[str, str] | None = None,
):
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    # Opening chunk with role
    yield {"data": ChatCompletionChunk(
        id=completion_id, created=created, model=model,
        choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
    ).model_dump_json(exclude_none=True)}

    async for chunk in stream_complete(messages, model, cursor_client, cursor_params):
        yield {"data": _chunk_to_sse(chunk, completion_id, created, model)}

    # Final stop chunk
    yield {"data": ChatCompletionChunk(
        id=completion_id, created=created, model=model,
        choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
    ).model_dump_json(exclude_none=True)}
    yield {"data": "[DONE]"}


# ── Stateful ─────────────────────────────────────────────────────────────────


async def _handle_stateful(
    body: ChatCompletionRequest,
    model: str,
    incoming_session_id: str,
    cursor_client,
    session_store,
):
    last_msg = _last_user_message(body.messages)
    cursor_params = body.cursor_params or None
    entry = await session_store.get(incoming_session_id)
    if entry is None:
        entry = await session_store.get_or_create(
            incoming_session_id, model, cursor_client, cursor_params
        )

    response_headers = {SESSION_HEADER: entry.session_id}

    if body.stream:
        return EventSourceResponse(
            _stateful_stream_generator(entry, last_msg, model),
            media_type="text/event-stream",
            headers=response_headers,
        )

    result = await complete_stateful(entry, last_msg)
    return JSONResponse(
        content=ChatCompletionResponse(
            model=result.actual_model or model,
            choices=[
                ChatCompletionChoice(
                    message=ChatCompletionMessage(
                        content=result.text,
                        reasoning_content=result.thinking or None,
                    ),
                    finish_reason=result.finish_reason,  # type: ignore[arg-type]
                )
            ],
            cursor_metadata=CursorMetadata(
                duration_ms=result.duration_ms,
                run_id=result.run_id,
                agent_id=result.agent_id,
                session_id=entry.session_id,
                thinking=result.thinking,
                thinking_duration_ms=result.thinking_duration_ms,
            ),
        ).model_dump(exclude_none=True),
        headers=response_headers,
    )


async def _stateful_stream_generator(entry, last_user_message: str, model: str):
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    yield {"data": ChatCompletionChunk(
        id=completion_id, created=created, model=model,
        choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
    ).model_dump_json(exclude_none=True)}

    async for chunk in stream_complete_stateful(entry, last_user_message):
        yield {"data": _chunk_to_sse(chunk, completion_id, created, model)}

    yield {"data": ChatCompletionChunk(
        id=completion_id, created=created, model=model,
        choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
    ).model_dump_json(exclude_none=True)}
    yield {"data": "[DONE]"}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _chunk_to_sse(chunk: StreamChunk, completion_id: str, created: int, model: str) -> str:
    """Convert a StreamChunk to an SSE data payload string."""
    if chunk.type == "thinking":
        delta = DeltaMessage(reasoning_content=chunk.text)
    else:
        delta = DeltaMessage(content=chunk.text)

    return ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[StreamChoice(delta=delta)],
    ).model_dump_json(exclude_none=True)
