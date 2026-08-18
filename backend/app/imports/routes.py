from fastapi import APIRouter, Body, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.embeddings.runtime import get_embedding_status
from app.imports.cursor.service import CursorImportService
from app.imports.parse_service import ParseService
from app.imports.service import ImportService
from app.imports.share_service import ShareImportService
from app.imports.validators import ImportValidationError
from app.models.import_job import ImportJob
from app.schemas.import_job import (
    CursorImportRequest,
    ImportDeleteResponse,
    ImportErrorResponse,
    ImportJobResponse,
    ShareImportRequest,
)
from app.schemas.parse import ParseJobResponse

router = APIRouter(prefix="/import", tags=["import"])


def import_job_response(job: ImportJob) -> ImportJobResponse:
    embedding = get_embedding_status()
    return ImportJobResponse(
        success=True,
        importId=job.id,
        source=job.source,
        folder=job.folder_path,
        status=job.status,
        filename=job.original_filename,
        fileSize=job.file_size,
        importedAt=job.imported_at,
        notes=job.notes,
        conversations=job.conversations_imported,
        messages=job.messages_imported,
        skipped=job.conversations_skipped,
        chunks_indexed=job.chunks_indexed,
        index_error=job.index_error,
        embedding_status=embedding["status"],
        embedding_status_detail=embedding["detail"],
    )


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
    "/chatgpt/share",
    response_model=ParseJobResponse,
    responses={
        400: {"model": ImportErrorResponse},
        404: {"model": ImportErrorResponse},
        503: {"model": ImportErrorResponse},
    },
)
def import_chatgpt_share(
    payload: ShareImportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ParseJobResponse | JSONResponse:
    """Fetch a public ChatGPT share page and store that conversation locally."""
    return _import_share(payload.url, db=db, settings=settings, claude=False)


@router.post(
    "/claude",
    response_model=ImportJobResponse,
    responses={
        400: {"model": ImportErrorResponse},
        413: {"model": ImportErrorResponse},
        503: {"model": ImportErrorResponse},
    },
)
async def import_claude_export(
    file: UploadFile = File(..., description="Claude data export ZIP file"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportJobResponse | JSONResponse:
    """
    Upload and store a Claude data export ZIP.

    Validates the archive, extracts it under data/imports/, and records an ImportJob.
    Does not parse conversations.
    """
    service = ImportService(db=db, settings=settings)

    try:
        return await service.import_claude_zip(file)
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
    "/claude/share",
    response_model=ParseJobResponse,
    responses={
        400: {"model": ImportErrorResponse},
        404: {"model": ImportErrorResponse},
        503: {"model": ImportErrorResponse},
    },
)
def import_claude_share(
    payload: ShareImportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ParseJobResponse | JSONResponse:
    """Fetch a public Claude share page and store that conversation locally."""
    return _import_share(payload.url, db=db, settings=settings, claude=True)


@router.post(
    "/cursor",
    response_model=ParseJobResponse,
    responses={
        400: {"model": ImportErrorResponse},
        404: {"model": ImportErrorResponse},
        503: {"model": ImportErrorResponse},
    },
)
def import_cursor(
    payload: CursorImportRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ParseJobResponse | JSONResponse:
    """Import Cursor chats from an explicit local path or the saved Settings path."""
    service = CursorImportService(db=db, settings=settings)
    try:
        return service.import_from_path(payload.path if payload else None)
    except ImportValidationError as exc:
        return _validation_error_response(exc)
    except Exception:
        return JSONResponse(
            status_code=503,
            content=ImportErrorResponse(
                error="Server unavailable or failed to import Cursor data. Please try again.",
                code="server_unavailable",
            ).model_dump(),
        )


@router.post(
    "/cursor/upload",
    response_model=ParseJobResponse,
    responses={
        400: {"model": ImportErrorResponse},
        413: {"model": ImportErrorResponse},
        503: {"model": ImportErrorResponse},
    },
)
async def import_cursor_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ParseJobResponse | JSONResponse:
    """Import a user-selected state.vscdb or transcript file. Never scans $HOME."""
    service = CursorImportService(db=db, settings=settings)
    try:
        return await service.import_upload(file)
    except ImportValidationError as exc:
        return _validation_error_response(exc)
    except Exception:
        return JSONResponse(
            status_code=503,
            content=ImportErrorResponse(
                error="Server unavailable or failed to import the Cursor file. Please try again.",
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
    Parse an uploaded export into normalized Conversation/Message rows.

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


@router.get(
    "/{import_id}",
    response_model=ImportJobResponse,
    responses={404: {"model": ImportErrorResponse}},
)
def get_import_job(
    import_id: str,
    db: Session = Depends(get_db),
) -> ImportJobResponse | JSONResponse:
    job = db.get(ImportJob, import_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content=ImportErrorResponse(
                error="Import job was not found.",
                code="import_not_found",
            ).model_dump(),
        )
    return import_job_response(job)


@router.delete(
    "/{import_id}",
    response_model=ImportDeleteResponse,
    responses={404: {"model": ImportErrorResponse}},
)
def delete_import_job(
    import_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportDeleteResponse | JSONResponse:
    service = ImportService(db=db, settings=settings)
    try:
        return service.forget_import_job(import_id)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
        )


@router.post(
    "/{import_id}/reindex",
    response_model=ImportJobResponse,
    responses={
        400: {"model": ImportErrorResponse},
        404: {"model": ImportErrorResponse},
    },
)
def reindex_import_job(
    import_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportJobResponse | JSONResponse:
    """Rebuild embeddings for an import that already parsed. Used after index_error."""
    service = ImportService(db=db, settings=settings)
    try:
        job = service.reindex_import_job(import_id)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
        )
    return import_job_response(job)


def _validation_error_response(exc: ImportValidationError) -> JSONResponse:
    if exc.code == "file_too_large":
        status_code = 413
    elif exc.code in {"share_not_found", "import_not_found"}:
        status_code = 404
    else:
        status_code = 400
    return JSONResponse(
        status_code=status_code,
        content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
    )


def _import_share(
    url: str,
    *,
    db: Session,
    settings: Settings,
    claude: bool,
) -> ParseJobResponse | JSONResponse:
    service = ShareImportService(db=db, settings=settings)
    try:
        if claude:
            return service.import_claude_share_url(url)
        return service.import_share_url(url)
    except ImportValidationError as exc:
        status_code = 404 if exc.code in {"share_not_found", "import_not_found"} else 400
        return JSONResponse(
            status_code=status_code,
            content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content=ImportErrorResponse(
                error="Server unavailable or failed to import the share link. Please try again.",
                code="server_unavailable",
            ).model_dump(),
        )
