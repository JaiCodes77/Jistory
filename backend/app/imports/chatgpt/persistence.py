"""Persist parsed ChatGPT conversations into SQLite."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.imports.chatgpt.parser import ParsedConversation, iter_conversation_batches
from app.models.conversation import Conversation
from app.models.message import Message

logger = logging.getLogger("jistory.persistence")

MESSAGE_FLUSH_SIZE = 500
CONVERSATION_BATCH_SIZE = 100


def delete_import_conversations(db: Session, import_job_id: str) -> int:
    """Remove previously stored conversations for an import job (idempotent re-parse)."""
    existing_ids = db.scalars(
        select(Conversation.id).where(Conversation.import_job_id == import_job_id)
    ).all()
    if not existing_ids:
        return 0

    # Clear self-referential parents, then delete messages, then conversations.
    db.execute(
        update(Message)
        .where(Message.conversation_id.in_(existing_ids))
        .values(parent_message_id=None)
    )
    db.execute(delete(Message).where(Message.conversation_id.in_(existing_ids)))
    result = db.execute(
        delete(Conversation).where(Conversation.import_job_id == import_job_id)
    )
    db.flush()
    deleted = result.rowcount or len(existing_ids)
    logger.info("Cleared %d existing conversation(s) for import %s", deleted, import_job_id)
    return deleted


def persist_conversations(
    db: Session,
    *,
    import_job_id: str,
    source: str,
    conversations: list[ParsedConversation],
) -> tuple[int, int]:
    """
    Persist parsed conversations/messages in batches.

    Returns (conversations_saved, messages_saved).
    """
    conversations_saved = 0
    messages_saved = 0

    # (message_id, parent_message_id) updates applied after base rows exist.
    parent_links: list[tuple[str, str]] = []
    pending_messages: list[Message] = []

    for batch in iter_conversation_batches(conversations, CONVERSATION_BATCH_SIZE):
        for parsed in batch:
            conversation_id = str(uuid.uuid4())
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
            conversations_saved += 1

            external_to_internal: dict[str, str] = {}

            for parsed_msg in parsed.messages:
                message_id = str(uuid.uuid4())
                external_to_internal[parsed_msg.external_id] = message_id
                pending_messages.append(
                    Message(
                        id=message_id,
                        conversation_id=conversation_id,
                        external_id=parsed_msg.external_id,
                        parent_message_id=None,
                        role=parsed_msg.role,
                        content=parsed_msg.content or "",
                        created_at=parsed_msg.created_at,
                        sequence_number=parsed_msg.sequence_number,
                    )
                )

            for parsed_msg in parsed.messages:
                parent_ext = parsed_msg.parent_external_id
                if not parent_ext:
                    continue
                parent_id = external_to_internal.get(parent_ext)
                child_id = external_to_internal.get(parsed_msg.external_id)
                if parent_id and child_id:
                    parent_links.append((child_id, parent_id))

            messages_saved += len(parsed.messages)

            if len(pending_messages) >= MESSAGE_FLUSH_SIZE:
                db.add_all(pending_messages)
                db.flush()
                pending_messages.clear()

        db.flush()

    if pending_messages:
        db.add_all(pending_messages)
        db.flush()

    # Apply parent links in chunks after all message rows exist.
    for i in range(0, len(parent_links), MESSAGE_FLUSH_SIZE):
        chunk = parent_links[i : i + MESSAGE_FLUSH_SIZE]
        for child_id, parent_id in chunk:
            db.execute(
                update(Message)
                .where(Message.id == child_id)
                .values(parent_message_id=parent_id)
            )
        db.flush()

    logger.info(
        "Persisted conversations=%d messages=%d",
        conversations_saved,
        messages_saved,
    )
    return conversations_saved, messages_saved
