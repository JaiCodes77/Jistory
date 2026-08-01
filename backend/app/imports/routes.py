from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.imports.parse_service import ParseService
from app.imports.service import ImportService
from app.imports.validators import ImportValidationError
from app.schemas.import_job import ImportErrorResponse, ImportJobResponse
from app.schemas.parse import ParseJobResponse

router = APIRouter(prefix="/import", tags=["import"])


@router.post(
    "/chatgpt",
    response_model=ImportJobResponse,
    responses={
        400: {"model": ImportErrorResponse},
        413: {"model": ImportErrorResponse},
        503: {"model": ImportErrorResponse},
    },
)
async def import_chatgpt_export(
    file: UploadFile = File(..., description="ChatGPT export ZIP file"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportJobResponse | JSONResponse:
    """
    Upload and store a ChatGPT data export ZIP.

    Validates the archive, extracts it under data/imports/, and records an ImportJob.
    Does not parse conversations.
    """
    service = ImportService(db=db, settings=settings)

    try:
        return await service.import_chatgpt_zip(file)
    except ImportValidationError as exc:
        status_code = 413 if exc.code == "file_too_large" else 400
        return JSONResponse(
            status_code=status_code,
            content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content=ImportErrorResponse(
                error="Server unavailable or failed to process the upload. Please try again.",
                code="server_unavailable",
            ).model_dump(),
        )


@router.post(
    "/{import_id}/parse",
    response_model=ParseJobResponse,
    responses={
        400: {"model": ImportErrorResponse},
        404: {"model": ImportErrorResponse},
        503: {"model": ImportErrorResponse},
    },
)
def parse_import_job(
    import_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ParseJobResponse | JSONResponse:
    """
    Parse an uploaded ChatGPT export into normalized Conversation/Message rows.

    Idempotent: re-running replaces prior parse results for the same ImportJob.
    """
    service = ParseService(db=db, settings=settings)

    try:
        return service.parse_import_job(import_id)
    except ImportValidationError as exc:
        status_code = 404 if exc.code == "import_not_found" else 400
        return JSONResponse(
            status_code=status_code,
            content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content=ImportErrorResponse(
                error="Server unavailable or failed to parse the import. Please try again.",
                code="server_unavailable",
            ).model_dump(),
        )
