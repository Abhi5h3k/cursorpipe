"""Session management endpoints.

GET    /v1/sessions          → list all active stateful sessions
GET    /v1/sessions/{id}     → get a specific session's info
DELETE /v1/sessions/{id}     → close and evict a session
POST   /v1/sessions          → explicitly create a new session

All endpoints require the same bearer token auth as /v1/chat/completions.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from cursorpipe._config import settings
from cursorpipe_server.schemas import CreateSessionRequest, SessionInfo, SessionList

router = APIRouter()


@router.get("/v1/sessions", tags=["sessions"])
async def list_sessions(request: Request) -> SessionList:
    """List all active stateful sessions."""
    store = request.app.state.session_store
    entries = store.list_all()
    return SessionList(
        data=[
            SessionInfo(
                id=e.session_id,
                model=e.model,
                created_at=e.created_at.isoformat(),
                last_used_at=e.last_used_at.isoformat(),
            )
            for e in entries
        ]
    )


@router.get("/v1/sessions/{session_id}", tags=["sessions"])
async def get_session(session_id: str, request: Request) -> SessionInfo:
    """Get info about a specific session."""
    store = request.app.state.session_store
    entry = await store.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return SessionInfo(
        id=entry.session_id,
        model=entry.model,
        created_at=entry.created_at.isoformat(),
        last_used_at=entry.last_used_at.isoformat(),
    )


@router.delete("/v1/sessions/{session_id}", tags=["sessions"])
async def delete_session(session_id: str, request: Request):
    """Close and evict a session."""
    store = request.app.state.session_store
    deleted = await store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"deleted": True, "id": session_id}


@router.post("/v1/sessions", tags=["sessions"], status_code=201)
async def create_session(body: CreateSessionRequest, request: Request) -> SessionInfo:
    """Explicitly create a new stateful session and return its ID."""
    cursor_client = request.app.state.cursor_client
    store = request.app.state.session_store
    model = body.model or settings.model

    entry = await store.create_new(model, cursor_client, body.cursor_params or None)
    return SessionInfo(
        id=entry.session_id,
        model=entry.model,
        created_at=entry.created_at.isoformat(),
        last_used_at=entry.last_used_at.isoformat(),
    )
