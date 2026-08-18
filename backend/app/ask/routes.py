import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.ask.service import (
    ask,
    ask_stream,
    delete_ask_session,
    get_ask_session,
    list_ask_sessions,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.import_job import ImportErrorResponse
from app.schemas.search import (
    AskRequest,
    AskResponse,
    AskSessionDeleteResponse,
    AskSessionDetail,
    AskSessionListResponse,
)

router = APIRouter(prefix="/ask", tags=["ask"])


def _error(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
    )


@router.post("", response_model=AskResponse)
def ask_jistory(
    payload: AskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AskResponse | JSONResponse:
    try:
        return ask(
            db,
            settings,
            message=payload.message,
            conversation_id=payload.conversation_id,
            tagged_conversation_ids=payload.tagged_conversation_ids,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except AppError as exc:
        return _error(exc)


@router.post("/stream", response_model=None)
def ask_jistory_stream(
    payload: AskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse | JSONResponse:
    try:
        events = ask_stream(
            db,
            settings,
            message=payload.message,
            conversation_id=payload.conversation_id,
            tagged_conversation_ids=payload.tagged_conversation_ids,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        first = next(events)
    except AppError as exc:
        return _error(exc)
    except StopIteration:
        return JSONResponse(
            status_code=502,
            content=ImportErrorResponse(
                error="Jistory could not generate an answer. Please try again.",
                code="llm_unavailable",
            ).model_dump(),
        )

    def body():
        yield _sse(first)
        try:
            for event in events:
                yield _sse(event)
        except AppError as exc:
            yield _sse({"type": "error", "error": exc.message, "code": exc.code})

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.get("/sessions", response_model=AskSessionListResponse)
def get_ask_sessions(db: Session = Depends(get_db)) -> AskSessionListResponse:
    return list_ask_sessions(db)


@router.get("/sessions/{session_id}", response_model=AskSessionDetail)
def get_ask_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
) -> AskSessionDetail | JSONResponse:
    try:
        return get_ask_session(db, session_id)
    except AppError as exc:
        return _error(exc)


@router.delete("/sessions/{session_id}", response_model=AskSessionDeleteResponse)
def forget_ask_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> AskSessionDeleteResponse | JSONResponse:
    try:
        deleted_id = delete_ask_session(db, session_id)
    except AppError as exc:
        return _error(exc)
    return AskSessionDeleteResponse(success=True, id=deleted_id)
