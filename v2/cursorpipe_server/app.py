"""FastAPI application factory.

Lifespan
--------
1. Validate CURSOR_API_KEY — fail fast with a clear message if missing.
2. Launch the cursor-sdk async bridge (one per process, shared across requests).
3. Attach the SessionStore and start its TTL cleanup task.
4. On shutdown: stop cleanup, close all stateful agents, close the bridge.

Auth
----
If CURSORPIPE_BEARER_TOKEN is set, every request to /v1/* must carry:
    Authorization: Bearer <token>
The /health endpoint is always public.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from cursor_sdk import AsyncClient
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cursorpipe._config import settings
from cursorpipe._session_store import SessionStore
from cursorpipe_server.errors import (
    cursor_error_handler,
    generic_error_handler,
    validation_error_handler,
)
from cursorpipe_server.middleware import RequestLoggingMiddleware
from cursorpipe_server.routes.completions import router as completions_router
from cursorpipe_server.routes.health import router as health_router
from cursorpipe_server.routes.models import router as models_router
from cursorpipe_server.routes.sessions import router as sessions_router

logger = logging.getLogger(__name__)

try:
    from cursor_sdk import CursorAgentError
except ImportError:
    CursorAgentError = Exception  # type: ignore[misc,assignment]


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast: clear error before any network call if the API key is absent.
    if not settings.cursor_api_key:
        raise RuntimeError(
            "CURSOR_API_KEY is not set. "
            "Generate one at https://cursor.com/settings → API Keys "
            "and add it to your .env file or environment."
        )

    # cursor_client is set to None so /health returns 503 until bridge is ready.
    app.state.cursor_client = None

    async with await AsyncClient.launch_bridge(workspace=settings.workspace) as client:
        app.state.cursor_client = client

        store = SessionStore()
        store.start_cleanup()
        app.state.session_store = store

        logger.info(
            "cursorpipe-server v2 (SDK-based) ready on %s:%s",
            settings.host,
            settings.port,
        )

        yield

        await store.stop_cleanup()
    # bridge is closed automatically when the context manager exits


# ── Auth dependency ───────────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Validates the bearer token when CURSORPIPE_BEARER_TOKEN is configured."""
    expected = settings.bearer_token
    if not expected:
        return  # auth disabled

    if credentials is None or credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Factory ───────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="cursorpipe",
        version="2.0.0",
        description="OpenAI-compatible API server powered by the Cursor SDK",
        lifespan=lifespan,
    )

    # CORS — allows browser-based clients (Open WebUI, LobeChat, Chatbot UI).
    # CURSORPIPE_CORS_ORIGINS controls which origins are permitted; default "*".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list(),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Cursor-Session-ID", "X-Request-ID"],
    )

    # Request ID + structured access logging.
    app.add_middleware(RequestLoggingMiddleware)

    # Public routes (no auth)
    app.include_router(health_router)

    # Protected routes
    auth_dep = [Depends(require_auth)]
    app.include_router(completions_router, dependencies=auth_dep)
    app.include_router(models_router, dependencies=auth_dep)
    app.include_router(sessions_router, dependencies=auth_dep)

    # Error handlers — registered in order from most-specific to least.
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(CursorAgentError, cursor_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_error_handler)  # type: ignore[arg-type]

    return app


app = create_app()
