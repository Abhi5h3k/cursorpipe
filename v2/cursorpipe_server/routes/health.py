from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health", tags=["ops"])
async def health(request: Request) -> JSONResponse:
    """Health check. Returns 503 if the SDK bridge is not running."""
    bridge_ok = (
        hasattr(request.app.state, "cursor_client")
        and request.app.state.cursor_client is not None
    )
    status_str = "ok" if bridge_ok else "degraded"
    bridge_str = "connected" if bridge_ok else "unavailable"
    http_status = 200 if bridge_ok else 503
    return JSONResponse(
        {"status": status_str, "bridge": bridge_str},
        status_code=http_status,
    )
