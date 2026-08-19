"""Persist parsed conversations into SQLite with source-level idempotency."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.imports.chatgpt.parser import iter_conversation_batches
from app.imports.parsers.base import ParsedConversation
from app.models.chunk import MemoryChunk
from app.models.conversation import Conversation
from app.models.graph import ConversationEdge
from app.models.message import Message

logger = logging.getLogger("jistory.persistence")

MESSAGE_FLUSH_SIZE = 500
CONVERSATION_BATCH_SIZE = 100


def delete_import_conversations(db: Session, import_job_id: str) -> int:
    """Remove previously stored conversations that still belong to this import job."""
    existing_ids = db.scalars(
        select(Conversation.id).where(Conversation.import_job_id == import_job_id)
    ).all()
    if not existing_ids:
        return 0

    _delete_conversation_ids(db, list(existing_ids))
    logger.info("Cleared %d existing conversation(s) for import %s", len(existing_ids), import_job_id)
    return len(existing_ids)


def delete_conversation_ids(db: Session, conversation_ids: list[str]) -> int:
    """Delete conversations plus messages, embedding chunks, and graph edges. FTS rows follow via triggers."""
    unique: list[str] = []
    seen: set[str] = set()
    for raw in conversation_ids:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    if not unique:
        return 0
    existing_ids = list(
        db.scalars(select(Conversation.id).where(Conversation.id.in_(unique))).all()
    )
    if not existing_ids:
        return 0
    _delete_conversation_ids(db, existing_ids)
    return len(existing_ids)


def _delete_conversation_ids(db: Session, conversation_ids: list[str]) -> None:
    db.execute(
        update(Message)
        .where(Message.conversation_id.in_(conversation_ids))
        .values(parent_message_id=None)
    )
    db.execute(delete(MemoryChunk).where(MemoryChunk.conversation_id.in_(conversation_ids)))
    db.execute(
        delete(ConversationEdge).where(
            or_(
                ConversationEdge.source_id.in_(conversation_ids),
                ConversationEdge.target_id.in_(conversation_ids),
            )
        )
    )
    db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
    db.flush()


def persist_conversations(
    db: Session,
    *,
    import_job_id: str,
    source: str,
    conversations: list[ParsedConversation],
) -> tuple[int, int]:
    """
    Persist parsed conversations/messages in batches.

    Conversations are unique on (source, external_id) so importing the same
    export twice updates existing rows instead of duplicating them.

    Returns (conversations_saved, messages_saved).
    """
    conversations_saved = 0
    messages_saved = 0
    pending_messages: list[Message] = []

    for batch in iter_conversation_batches(conversations, CONVERSATION_BATCH_SIZE):
        external_ids = [parsed.external_id for parsed in batch]
        existing_rows = db.scalars(
            select(Conversation).where(
                Conversation.source == source,
                Conversation.external_id.in_(external_ids),
            )
        ).all()
        existing_by_external = {row.external_id: row for row in existing_rows}

        reuse_ids = [row.id for row in existing_rows]
        if reuse_ids:
            db.execute(
                update(Message)
                .where(Message.conversation_id.in_(reuse_ids))
                .values(parent_message_id=None)
            )
            db.execute(delete(MemoryChunk).where(MemoryChunk.conversation_id.in_(reuse_ids)))
            db.execute(
                delete(ConversationEdge).where(
                    or_(
                        ConversationEdge.source_id.in_(reuse_ids),
                        ConversationEdge.target_id.in_(reuse_ids),
                    )
                )
            )
            db.execute(delete(Message).where(Message.conversation_id.in_(reuse_ids)))
            db.flush()

        for parsed in batch:
            existing = existing_by_external.get(parsed.external_id)
            conversation_id = existing.id if existing else str(uuid.uuid4())

            if existing:
                existing.import_job_id = import_job_id
                existing.title = parsed.title
                existing.created_at = parsed.created_at
                existing.updated_at = parsed.updated_at
                existing.message_count = parsed.message_count
                existing.first_message_at = parsed.first_message_at
                existing.last_message_at = parsed.last_message_at
            else:
                db.add(
                    Conversation(
                        id=conversation_id,
                        external_id=parsed.external_id,
                        import_job_id=import_job_id,
                        title=parsed.title,
                        source=source,
                        created_at=parsed.created_at,
                        updated_at=parsed.updated_at,
                        message_count=parsed.message_count,
                        first_message_at=parsed.first_message_at,
                        last_message_at=parsed.last_message_at,
                    )
                )

            db.flush()
            conversations_saved += 1
            external_to_internal: dict[str, str] = {}
            for parsed_msg in parsed.messages:
                external_to_internal[parsed_msg.external_id] = str(uuid.uuid4())

            for parsed_msg in parsed.messages:
                parent_id = None
                if parsed_msg.parent_external_id:
                    parent_id = external_to_internal.get(parsed_msg.parent_external_id)
                pending_messages.append(
                    Message(
                        id=external_to_internal[parsed_msg.external_id],
                        conversation_id=conversation_id,
                        external_id=parsed_msg.external_id,
                        parent_message_id=None if not parent_id else parent_id,
                        role=parsed_msg.role,
                        content=parsed_msg.content or "",
                        created_at=parsed_msg.created_at,
                        sequence_number=parsed_msg.sequence_number,
                    )
                )

            messages_saved += len(parsed.messages)

            if len(pending_messages) >= MESSAGE_FLUSH_SIZE:
                db.add_all(pending_messages)
                db.flush()
                pending_messages.clear()

        db.flush()

    if pending_messages:
        db.add_all(pending_messages)
        db.flush()

    logger.info(
        "Persisted conversations=%d messages=%d",
        conversations_saved,
        messages_saved,
    )
    return conversations_saved, messages_saved
