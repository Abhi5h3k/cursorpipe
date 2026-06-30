"""Async completion helpers wrapping cursor-sdk's AsyncAgent.

All paths use run.messages() so we can capture thinking content and real
RunResult metadata (run_id, duration_ms, actual_model) uniformly.

Stateless path  → create temp agent → send → iterate messages → close
Streaming path  → create temp agent → send → yield StreamChunk objects → close
Stateful path   → caller supplies a live SessionEntry whose agent persists
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cursor_sdk import AgentOptions, LocalAgentOptions, ModelParameterValue, ModelSelection

from cursorpipe._config import settings

if TYPE_CHECKING:
    from cursor_sdk import AsyncClient

    from cursorpipe._session_store import SessionEntry

logger = logging.getLogger(__name__)


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class CompletionResult:
    """Structured result from a non-streaming completion."""

    text: str
    finish_reason: str = "stop"
    actual_model: str | None = None
    duration_ms: int = 0
    run_id: str | None = None
    agent_id: str | None = None
    thinking: str | None = None
    thinking_duration_ms: int = 0


@dataclass
class StreamChunk:
    """A single chunk yielded during streaming."""

    type: Literal["text", "thinking"]
    text: str
    thinking_duration_ms: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────


def _agent_options(model: str, cursor_params: dict[str, str] | None = None) -> AgentOptions:
    """Build AgentOptions with model parameters.

    Priority:
      1. Per-request cursor_params (explicit dict from request body)
      2. Global CURSORPIPE_THINKING_LEVEL fallback (legacy thinking=low|high)
      3. Plain model string when neither is set
    """
    if cursor_params:
        model_sel: str | ModelSelection = ModelSelection(
            id=model,
            params=[ModelParameterValue(id=k, value=v) for k, v in cursor_params.items()],
        )
    else:
        thinking = settings.thinking_param
        if thinking:
            model_sel = ModelSelection(
                id=model,
                params=[ModelParameterValue(id="thinking", value=thinking)],
            )
        else:
            model_sel = model

    return AgentOptions(
        model=model_sel,
        api_key=settings.cursor_api_key or None,
        local=LocalAgentOptions(cwd=settings.workspace),
    )


def _map_status(status: str) -> str:
    """Map SDK RunResult.status to OpenAI finish_reason."""
    return "stop"  # SDK doesn't distinguish length cutoffs; all terminal states → stop


def _flatten_messages(messages: list[dict]) -> tuple[str, str]:
    """Convert an OpenAI messages array into (prompt, system) strings.

    System messages are extracted and joined. All other messages are
    formatted as 'role: content' lines and joined into a single prompt.
    """
    system_parts: list[str] = []
    prompt_parts: list[str] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "")
                for block in content
                if block.get("type") == "text"
            )
        if role == "system":
            system_parts.append(content)
        else:
            prompt_parts.append(f"{role}: {content}")

    return "\n".join(prompt_parts), "\n".join(system_parts)


async def _collect_messages(run) -> tuple[str, str, int]:
    """Drain run.messages(), returning (text, thinking_text, thinking_duration_ms).

    After this coroutine returns the run stream is exhausted and run.result,
    run.duration_ms, run.id, run.model are all populated.
    """
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    thinking_ms: int = 0

    async for message in run.messages():
        try:
            if message.type == "thinking":
                thinking_parts.append(getattr(message, "text", "") or "")
                thinking_ms += getattr(message, "thinking_duration_ms", 0) or 0
            elif message.type == "assistant":
                content = getattr(getattr(message, "message", None), "content", None)
                if content:
                    for block in content:
                        if getattr(block, "type", None) == "text":
                            text_parts.append(block.text or "")
        except Exception:
            pass  # unknown message types are safe to skip

    text = "".join(text_parts)
    thinking = "\n".join(t for t in thinking_parts if t)
    return text, thinking, thinking_ms


# ── Stateless ────────────────────────────────────────────────────────────────


async def complete(
    messages: list[dict],
    model: str | None,
    cursor_client: "AsyncClient",
    cursor_params: dict[str, str] | None = None,
) -> CompletionResult:
    """One-shot stateless non-streaming completion."""
    effective_model = model or settings.model
    prompt, _ = _flatten_messages(messages)

    agent = await cursor_client.agents.create(_agent_options(effective_model, cursor_params))
    try:
        run = await agent.send(prompt)
        text, thinking, thinking_ms = await _collect_messages(run)

        result_text = text or getattr(run, "result", "") or ""
        actual_model: str | None = None
        m = getattr(run, "model", None)
        if m is not None:
            actual_model = getattr(m, "id", None)

        has_thinking = bool(cursor_params) or bool(settings.thinking_param)
        return CompletionResult(
            text=result_text,
            finish_reason=_map_status(getattr(run, "status", "finished")),
            actual_model=actual_model or effective_model,
            duration_ms=getattr(run, "duration_ms", 0) or 0,
            run_id=getattr(run, "id", None),
            agent_id=getattr(run, "agent_id", None),
            thinking=thinking if has_thinking else None,
            thinking_duration_ms=thinking_ms if has_thinking else 0,
        )
    finally:
        await _close_agent(agent)


async def stream_complete(
    messages: list[dict],
    model: str | None,
    cursor_client: "AsyncClient",
    cursor_params: dict[str, str] | None = None,
) -> AsyncIterator[StreamChunk]:
    """One-shot stateless streaming completion. Yields StreamChunk objects."""
    effective_model = model or settings.model
    prompt, _ = _flatten_messages(messages)

    has_thinking = bool(cursor_params) or bool(settings.thinking_param)
    agent = await cursor_client.agents.create(_agent_options(effective_model, cursor_params))
    try:
        run = await agent.send(prompt)
        async for message in run.messages():
            try:
                if message.type == "thinking" and has_thinking:
                    text = getattr(message, "text", "") or ""
                    ms = getattr(message, "thinking_duration_ms", 0) or 0
                    if text:
                        yield StreamChunk(type="thinking", text=text, thinking_duration_ms=ms)
                elif message.type == "assistant":
                    content = getattr(getattr(message, "message", None), "content", None)
                    if content:
                        for block in content:
                            if getattr(block, "type", None) == "text" and block.text:
                                yield StreamChunk(type="text", text=block.text)
            except Exception:
                pass
    finally:
        await _close_agent(agent)


# ── Stateful ─────────────────────────────────────────────────────────────────


async def complete_stateful(
    session_entry: "SessionEntry",
    last_user_message: str,
) -> CompletionResult:
    """Send one turn to a persistent Agent. The SDK holds full history."""
    run = await session_entry.agent.send(last_user_message)
    text, thinking, thinking_ms = await _collect_messages(run)

    result_text = text or getattr(run, "result", "") or ""
    actual_model: str | None = None
    m = getattr(run, "model", None)
    if m is not None:
        actual_model = getattr(m, "id", None)

    session_entry.touch()
    return CompletionResult(
        text=result_text,
        finish_reason=_map_status(getattr(run, "status", "finished")),
        actual_model=actual_model or session_entry.model,
        duration_ms=getattr(run, "duration_ms", 0) or 0,
        run_id=getattr(run, "id", None),
        agent_id=getattr(run, "agent_id", None),
        thinking=thinking if settings.thinking_param else None,
        thinking_duration_ms=thinking_ms if settings.thinking_param else 0,
    )


async def stream_complete_stateful(
    session_entry: "SessionEntry",
    last_user_message: str,
) -> AsyncIterator[StreamChunk]:
    """Stream one turn to a persistent Agent. Yields StreamChunk objects."""
    run = await session_entry.agent.send(last_user_message)
    async for message in run.messages():
        try:
            if message.type == "thinking" and settings.thinking_param:
                text = getattr(message, "text", "") or ""
                ms = getattr(message, "thinking_duration_ms", 0) or 0
                if text:
                    yield StreamChunk(type="thinking", text=text, thinking_duration_ms=ms)
            elif message.type == "assistant":
                content = getattr(getattr(message, "message", None), "content", None)
                if content:
                    for block in content:
                        if getattr(block, "type", None) == "text" and block.text:
                            yield StreamChunk(type="text", text=block.text)
        except Exception:
            pass
    session_entry.touch()


# ── Utility ───────────────────────────────────────────────────────────────────


async def _close_agent(agent) -> None:
    try:
        await agent.close()
    except Exception:
        pass
