"""HTTP route handlers — OpenAI-compatible endpoints.

All routes pull the shared ``CursorClient`` from ``request.app.state.client``.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from cursorpipe_server.schemas import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    DeltaContent,
    ModelListResponse,
    ModelObject,
    StreamChoice,
    Usage,
)

if TYPE_CHECKING:
    from cursorpipe import CursorClient

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_client(request: Request) -> CursorClient:
    return request.app.state.client  # type: ignore[no-any-return]


# ------------------------------------------------------------------
# POST /v1/chat/completions
# ------------------------------------------------------------------


def _messages_to_kwargs(req: ChatCompletionRequest) -> dict:
    """Extract system prompt and build generate() kwargs from the request."""
    system_parts: list[str] = []
    user_parts: list[str] = []
    for msg in req.messages:
        if msg.role == "system":
            system_parts.append(msg.content)
        else:
            user_parts.append(f"[{msg.role}]\n{msg.content}")

    prompt = "\n\n".join(user_parts) if user_parts else ""
    system = "\n\n".join(system_parts)
    return {"model": req.model, "prompt": prompt, "system": system}


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    client = _get_client(request)
    kwargs = _messages_to_kwargs(req)

    if req.stream:
        return EventSourceResponse(
            _stream_response(client, req, kwargs),
            media_type="text/event-stream",
        )

    text = await client.generate(**kwargs)

    return ChatCompletionResponse(
        model=req.model,
        choices=[
            Choice(message=ChoiceMessage(content=text)),
        ],
        usage=Usage(),
    )


async def _stream_response(client: CursorClient, req: ChatCompletionRequest, kwargs: dict):
    """Async generator that yields SSE ``data:`` payloads."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    # First chunk with the role
    first_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=req.model,
        choices=[StreamChoice(delta=DeltaContent(role="assistant", content=""))],
    )
    yield {"data": first_chunk.model_dump_json()}

    async for text in client.stream(**kwargs):
        chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=req.model,
            choices=[StreamChoice(delta=DeltaContent(content=text))],
        )
        yield {"data": chunk.model_dump_json()}

    # Final chunk signalling completion
    done_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=req.model,
        choices=[StreamChoice(delta=DeltaContent(), finish_reason="stop")],
    )
    yield {"data": done_chunk.model_dump_json()}
    yield {"data": "[DONE]"}


# ------------------------------------------------------------------
# GET /v1/models
# ------------------------------------------------------------------


@router.get("/v1/models")
async def list_models(request: Request):
    client = _get_client(request)
    try:
        names = await client.list_models()
    except Exception:
        logger.warning("list_models failed, returning empty list", exc_info=True)
        names = []

    return ModelListResponse(
        data=[ModelObject(id=name) for name in names],
    )


# ------------------------------------------------------------------
# GET /health
# ------------------------------------------------------------------


@router.get("/health")
async def health():
    return {"status": "ok"}
