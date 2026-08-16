from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.conversation import Conversation
from app.models.message import Message

RANGE_DELTAS = {
    "today": timedelta(days=1),
    "last_7_days": timedelta(days=7),
    "last_30_days": timedelta(days=30),
    "last_3_months": timedelta(days=90),
}

SORT_MAP = {
    "newest": Conversation.created_at.desc(),
    "oldest": Conversation.created_at.asc(),
    "most_messages": Conversation.message_count.desc(),
    "recently_updated": Conversation.updated_at.desc(),
}


def _range_start(range_key: str | None) -> datetime | None:
    if not range_key or range_key == "custom":
        return None
    delta = RANGE_DELTAS.get(range_key)
    if not delta:
        return None
    now = datetime.now(timezone.utc)
    if range_key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now - delta


def list_conversations(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None = None,
    source: str | None = None,
    range_key: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "newest",
) -> tuple[list[Conversation], int]:
    stmt = select(Conversation)
    count_stmt = select(func.count()).select_from(Conversation)

    if source:
        stmt = stmt.where(Conversation.source == source)
        count_stmt = count_stmt.where(Conversation.source == source)

    start = date_from or _range_start(range_key)
    if start is not None:
        stmt = stmt.where(
            func.coalesce(Conversation.updated_at, Conversation.created_at, Conversation.last_message_at)
            >= start
        )
        count_stmt = count_stmt.where(
            func.coalesce(Conversation.updated_at, Conversation.created_at, Conversation.last_message_at)
            >= start
        )
    if date_to is not None:
        stmt = stmt.where(
            func.coalesce(Conversation.updated_at, Conversation.created_at, Conversation.last_message_at)
            <= date_to
        )
        count_stmt = count_stmt.where(
            func.coalesce(Conversation.updated_at, Conversation.created_at, Conversation.last_message_at)
            <= date_to
        )

    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(Conversation.title.ilike(term), Conversation.external_id.ilike(term))
        )
        count_stmt = count_stmt.where(
            or_(Conversation.title.ilike(term), Conversation.external_id.ilike(term))
        )

    order = SORT_MAP.get(sort, Conversation.created_at.desc())
    stmt = stmt.order_by(order, Conversation.id.desc())

    total = int(db.scalar(count_stmt) or 0)
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def get_conversation(db: Session, conversation_id: str) -> Conversation:
    row = db.get(Conversation, conversation_id)
    if row is None:
        raise AppError("Conversation not found.", code="not_found", status_code=404)
    return row


def list_messages(
    db: Session,
    conversation_id: str,
    *,
    page: int,
    page_size: int,
    around_message_id: str | None = None,
) -> tuple[Conversation, list[Message], int, int]:
    conversation = get_conversation(db, conversation_id)
    total = conversation.message_count

    if around_message_id:
        target = db.get(Message, around_message_id)
        if target is None or target.conversation_id != conversation_id:
            raise AppError("Message not found in this conversation.", code="not_found", status_code=404)
        page = (target.sequence_number // page_size) + 1

    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence_number.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(stmt).all())
    return conversation, items, total, page
