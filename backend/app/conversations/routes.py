from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversations.service import get_conversation, list_conversations, list_messages
from app.core.errors import AppError
from app.db.session import get_db
from app.models.conversation import Conversation
from app.schemas.conversation import (
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    MessageItem,
    MessageListResponse,
)
from app.schemas.import_job import ImportErrorResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _error(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
    )


@router.get("", response_model=ConversationListResponse)
def get_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    search: str | None = Query(None),
    source: str | None = Query(None),
    range: str | None = Query(None, alias="range"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    sort: str = Query("newest"),
    db: Session = Depends(get_db),
) -> ConversationListResponse | JSONResponse:
    from datetime import datetime

    parsed_from = None
    parsed_to = None
    try:
        if date_from:
            parsed_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        if date_to:
            parsed_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
        items, total = list_conversations(
            db,
            page=page,
            page_size=page_size,
            search=search,
            source=source,
            range_key=range,
            date_from=parsed_from,
            date_to=parsed_to,
            sort=sort,
        )
    except AppError as exc:
        return _error(exc)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content=ImportErrorResponse(
                error="Invalid date range. Use ISO-8601 timestamps.",
                code="invalid_date",
            ).model_dump(),
        )

    return ConversationListResponse(
        items=[ConversationSummary.model_validate(row) for row in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> dict[str, list[str]]:
    rows = db.scalars(select(Conversation.source).distinct()).all()
    present = [row for row in rows if row]
    extras = [name for name in ("ChatGPT", "Claude", "Gemini", "Cursor") if name not in present]
    return {"items": present + extras, "available": present}


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation_detail(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationDetail | JSONResponse:
    try:
        row = get_conversation(db, conversation_id)
    except AppError as exc:
        return _error(exc)
    return ConversationDetail.model_validate(row)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
def get_conversation_messages(
    conversation_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
    around: str | None = Query(None, description="Message ID to page around"),
    db: Session = Depends(get_db),
) -> MessageListResponse | JSONResponse:
    try:
        conversation, items, total, resolved_page = list_messages(
            db,
            conversation_id,
            page=page,
            page_size=page_size,
            around_message_id=around,
        )
    except AppError as exc:
        return _error(exc)

    return MessageListResponse(
        items=[MessageItem.model_validate(row) for row in items],
        page=resolved_page,
        page_size=page_size,
        total=total,
        conversation=ConversationDetail.model_validate(conversation),
    )
