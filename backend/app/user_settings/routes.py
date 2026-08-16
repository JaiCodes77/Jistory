from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.dashboard import UserSettingsPublic, UserSettingsUpdate
from app.schemas.import_job import ImportErrorResponse
from app.user_settings.store import public_settings, save_overrides

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsPublic)
def get_settings_public(settings: Settings = Depends(get_settings)) -> UserSettingsPublic:
    return UserSettingsPublic.model_validate(public_settings(settings))


@router.patch("", response_model=UserSettingsPublic)
def update_settings(
    payload: UserSettingsUpdate,
    settings: Settings = Depends(get_settings),
) -> UserSettingsPublic | JSONResponse:
    updates = payload.model_dump(exclude_unset=True)
    if "embedding_provider" in updates and updates["embedding_provider"] not in {
        None,
        "local",
        "gemini",
    }:
        return JSONResponse(
            status_code=400,
            content=ImportErrorResponse(
                error="Embedding provider must be local or gemini.",
                code="invalid_provider",
            ).model_dump(),
        )
    try:
        save_overrides(updates, settings)
    except OSError:
        raise AppError(
            "Could not save settings on disk.",
            code="settings_write_failed",
            status_code=500,
        )
    return UserSettingsPublic.model_validate(public_settings(settings))
