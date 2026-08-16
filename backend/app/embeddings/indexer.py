from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.embeddings.chunker import chunk_messages
from app.embeddings.factory import get_embedding_provider
from app.embeddings.store import replace_chunks
from app.models.conversation import Conversation

logger = logging.getLogger("jistory.embeddings")


def index_import_job(db: Session, import_job_id: str) -> int:
    conversations = list(
        db.scalars(
            select(Conversation)
            .where(Conversation.import_job_id == import_job_id)
            .options(selectinload(Conversation.messages))
        ).all()
    )
    return index_conversation_rows(db, conversations)


def index_conversation_rows(db: Session, conversations: list[Conversation]) -> int:
    if not conversations:
        return 0

    settings = get_settings()
    provider = get_embedding_provider(settings)
    drafts = []
    ids: list[str] = []
    for conversation in conversations:
        ids.append(conversation.id)
        ordered = sorted(conversation.messages, key=lambda m: m.sequence_number)
        drafts.extend(
            chunk_messages(
                conversation_id=conversation.id,
                source=conversation.source,
                messages=ordered,
            )
        )

    try:
        count = replace_chunks(
            db,
            drafts=drafts,
            provider=provider,
            conversation_ids=ids,
        )
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
