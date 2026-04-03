"""FastAPI application factory for cursorpipe-server.

Creates an OpenAI-compatible HTTP server backed by cursorpipe.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from pydantic_settings import BaseSettings

from cursorpipe import CursorClient, CursorPipeConfig
from cursorpipe._errors import (
    AgentCrashError,
    AgentNotFoundError,
    AgentTimeoutError,
    AuthenticationError,
    CursorPipeError,
    RateLimitError,
    SessionError,
)
from cursorpipe_server.routes import router
from cursorpipe_server.schemas import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Server-specific configuration
# ------------------------------------------------------------------


class ServerConfig(BaseSettings):
    """Settings for cursorpipe-server (loaded from env / .env)."""

    model_config = {"env_prefix": "CURSORPIPE_", "env_file": ".env", "extra": "ignore"}

    host: str = Field(default="0.0.0.0", description="Bind address.")
    port: int = Field(default=8080, description="Bind port.")
    pool_size: int = Field(
        default=5,
        description="Number of ACP sessions to pre-create at startup.",
    )
    bearer_token: str = Field(
        default="",
        description=(
            "Optional bearer token for incoming requests. "
            "When set, clients must send Authorization: Bearer <token>."
        ),
    )


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: create & warm the client. Shutdown: close it."""
    server_cfg: ServerConfig = app.state.server_config
    client = CursorClient(CursorPipeConfig())
    await client.warmup(pool_size=server_cfg.pool_size)
    app.state.client = client
    logger.info(
        "cursorpipe-server ready on %s:%s (pool_size=%s)",
        server_cfg.host,
        server_cfg.port,
        server_cfg.pool_size,
    )
    yield
    await client.close()
    logger.info("cursorpipe-server shut down")


# ------------------------------------------------------------------
# App factory
# ------------------------------------------------------------------


def create_app(server_config: ServerConfig | None = None) -> FastAPI:
    """Build and return a configured FastAPI application."""
    cfg = server_config or ServerConfig()

    app = FastAPI(
        title="cursorpipe-server",
        description="OpenAI-compatible API backed by Cursor Agent CLI",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.server_config = cfg

    # Bearer-token auth middleware
    if cfg.bearer_token:

        @app.middleware("http")
        async def _auth_middleware(request: Request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            auth = request.headers.get("Authorization", "")
            expected = f"Bearer {cfg.bearer_token}"
            if auth != expected:
                return JSONResponse(
                    status_code=401,
                    content=ErrorResponse(
                        error=ErrorDetail(
                            message="Invalid or missing bearer token", type="auth_error"
                        )
                    ).model_dump(),
                )
            return await call_next(request)

    # Exception handlers for cursorpipe errors
    @app.exception_handler(AuthenticationError)
    async def _auth_error(_req: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=401,
            content=ErrorResponse(
                error=ErrorDetail(message=str(exc), type="authentication_error", code="auth_failed")
            ).model_dump(),
        )

    @app.exception_handler(RateLimitError)
    async def _rate_limit(_req: Request, exc: RateLimitError):
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                error=ErrorDetail(message=str(exc), type="rate_limit_error", code="rate_limited")
            ).model_dump(),
        )

    @app.exception_handler(AgentTimeoutError)
    async def _timeout(_req: Request, exc: AgentTimeoutError):
        return JSONResponse(
            status_code=504,
            content=ErrorResponse(
                error=ErrorDetail(message=str(exc), type="timeout_error", code="timeout")
            ).model_dump(),
        )

    @app.exception_handler(AgentNotFoundError)
    async def _not_found(_req: Request, exc: AgentNotFoundError):
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error=ErrorDetail(
                    message=str(exc), type="service_unavailable", code="agent_not_found"
                )
            ).model_dump(),
        )

    @app.exception_handler(AgentCrashError)
    async def _crash(_req: Request, exc: AgentCrashError):
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(message=str(exc), type="server_error", code="agent_crash")
            ).model_dump(),
        )

    @app.exception_handler(SessionError)
    async def _session_err(_req: Request, exc: SessionError):
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(message=str(exc), type="server_error", code="session_error")
            ).model_dump(),
        )

    @app.exception_handler(CursorPipeError)
    async def _generic(_req: Request, exc: CursorPipeError):
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(message=str(exc), type="server_error")
            ).model_dump(),
        )

    app.include_router(router)
    return app
