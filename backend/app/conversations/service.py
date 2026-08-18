from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.imports.chatgpt.persistence import delete_conversation_ids
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


def forget_conversation(db: Session, conversation_id: str) -> str:
    row = get_conversation(db, conversation_id)
    deleted_id = row.id
    delete_conversation_ids(db, [deleted_id])
    db.commit()
    return deleted_id


def list_messages(
    db: Session,
    conversation_id: str,
    *,
    page: int,
    page_size: int,
    around_message_id: str | None = None,
    before_sequence: int | None = None,
    after_sequence: int | None = None,
) -> tuple[Conversation, list[Message], int, int, bool, bool]:
    conversation = get_conversation(db, conversation_id)
    total = conversation.message_count
    base = select(Message).where(Message.conversation_id == conversation_id)

    if around_message_id:
        target = db.get(Message, around_message_id)
        if target is None or target.conversation_id != conversation_id:
            raise AppError("Message not found in this conversation.", code="not_found", status_code=404)
        seq = target.sequence_number
        before = list(
            db.scalars(
                base.where(Message.sequence_number <= seq)
                .order_by(Message.sequence_number.desc())
                .limit(page_size // 2 + 1)
            ).all()
        )
        after = list(
            db.scalars(
                base.where(Message.sequence_number > seq)
                .order_by(Message.sequence_number.asc())
                .limit(max(0, page_size - len(before)))
            ).all()
        )
        items = list(reversed(before)) + after
        if len(items) < page_size:
            extra = list(
                db.scalars(
                    base.where(Message.sequence_number < items[0].sequence_number)
                    .order_by(Message.sequence_number.desc())
                    .limit(page_size - len(items))
                ).all()
            ) if items else []
            items = list(reversed(extra)) + items
        page = (seq // page_size) + 1 if page_size else 1
    elif before_sequence is not None:
        items = list(
            reversed(
                list(
                    db.scalars(
                        base.where(Message.sequence_number < before_sequence)
                        .order_by(Message.sequence_number.desc())
                        .limit(page_size)
                    ).all()
                )
            )
        )
    elif after_sequence is not None:
        items = list(
            db.scalars(
                base.where(Message.sequence_number > after_sequence)
                .order_by(Message.sequence_number.asc())
                .limit(page_size)
            ).all()
        )
    else:
        items = list(
            db.scalars(
                base.order_by(Message.sequence_number.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )

    has_before = False
    has_after = False
    if items:
        has_before = (
            db.scalar(
                select(Message.id)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sequence_number < items[0].sequence_number,
                )
                .limit(1)
            )
            is not None
        )
        has_after = (
            db.scalar(
                select(Message.id)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sequence_number > items[-1].sequence_number,
                )
                .limit(1)
            )
            is not None
        )
    elif total > 0:
        has_before = page > 1
        has_after = True

    return conversation, items, total, page, has_before, has_after
