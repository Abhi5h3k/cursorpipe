from fastapi import APIRouter
from fastapi.responses import JSONResponse

from cursorpipe._config import settings
from cursorpipe_server.schemas import ModelCard, ModelList

router = APIRouter()


@router.get("/v1/models", tags=["models"])
async def list_models() -> ModelList:
    """Return the list of models available via the Cursor account."""
    try:
        from cursor_sdk import Cursor

        sdk_models = Cursor.models.list(api_key=settings.cursor_api_key or None)
        cards = [ModelCard(id=m.id) for m in sdk_models]
    except Exception:
        # Fall back to returning just the configured default model.
        cards = [ModelCard(id=settings.model)]

    return ModelList(data=cards)
