from fastapi import APIRouter

from cursorpipe._config import settings
from cursorpipe_server.schemas import ModelCard, ModelList, ModelParamDef, ModelParamValueDef

router = APIRouter()


def _param_def(p) -> ModelParamDef:
    """Convert an SDK ModelParameterDefinition to our schema."""
    values = [
        ModelParamValueDef(
            value=getattr(v, "value", "") or "",
            display_name=getattr(v, "display_name", "") or "",
        )
        for v in (getattr(p, "values", None) or [])
    ]
    return ModelParamDef(
        id=getattr(p, "id", "") or "",
        display_name=getattr(p, "display_name", "") or "",
        values=values,
    )


@router.get("/v1/models", tags=["models"])
async def list_models() -> ModelList:
    """Return the list of models available via the Cursor account.

    Each model card includes a ``cursor_parameters`` field listing SDK-level
    parameters (e.g. ``thinking=low|high``). Standard OpenAI clients ignore
    this field.
    """
    try:
        from cursor_sdk import Cursor

        sdk_models = Cursor.models.list(api_key=settings.cursor_api_key or None)
        cards = [
            ModelCard(
                id=m.id,
                cursor_parameters=[
                    _param_def(p)
                    for p in (getattr(m, "parameters", None) or [])
                ],
            )
            for m in sdk_models
        ]
    except Exception:
        # Fall back to returning just the configured default model.
        cards = [ModelCard(id=settings.model)]

    return ModelList(data=cards)
