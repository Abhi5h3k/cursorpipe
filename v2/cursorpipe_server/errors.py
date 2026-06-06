"""Map cursor-sdk exceptions and FastAPI validation errors to OpenAI-shaped HTTP responses."""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

try:
    from cursor_sdk import (
        AgentBusyError,
        APITimeoutError,
        AuthenticationError,
        CursorAgentError,
        NetworkError,
        RateLimitError,
    )
except ImportError:  # pragma: no cover
    CursorAgentError = Exception  # type: ignore[misc,assignment]
    AuthenticationError = None  # type: ignore[assignment,misc]
    RateLimitError = None  # type: ignore[assignment,misc]
    NetworkError = None  # type: ignore[assignment,misc]
    APITimeoutError = None  # type: ignore[assignment,misc]
    AgentBusyError = None  # type: ignore[assignment,misc]


def _error_body(message: str, code: str | None = None, error_type: str = "api_error") -> dict:
    return {"error": {"message": message, "type": error_type, "code": code}}


def _status_for(exc: Exception) -> int:
    if AuthenticationError and isinstance(exc, AuthenticationError):
        return 401
    if RateLimitError and isinstance(exc, RateLimitError):
        return 429
    if NetworkError and isinstance(exc, NetworkError):
        return 502
    if APITimeoutError and isinstance(exc, APITimeoutError):
        return 504
    if AgentBusyError and isinstance(exc, AgentBusyError):
        return 409
    return 500


async def cursor_error_handler(request: Request, exc: Exception) -> JSONResponse:
    status = _status_for(exc)
    message = str(exc)
    code = getattr(exc, "code", None)
    return JSONResponse(status_code=status, content=_error_body(message, code))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return validation errors in OpenAI's error format instead of FastAPI's default.

    Without this, LangChain and LiteLLM silently break when they receive
    FastAPI's default {"detail": [...]} shape for 422 responses.
    """
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = " → ".join(str(l) for l in first.get("loc", []))
        message = f"{loc}: {first.get('msg', 'validation error')}" if loc else first.get("msg", "validation error")
    else:
        message = "Invalid request"

    return JSONResponse(
        status_code=422,
        content=_error_body(message, error_type="invalid_request_error"),
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_error_body(f"Internal server error: {exc}"),
    )
