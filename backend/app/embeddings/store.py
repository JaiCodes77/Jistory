from __future__ import annotations

import array
import json
import logging
import math
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.embeddings.base import EmbeddingProvider
from app.embeddings.chunker import ChunkDraft
from app.models.chunk import MemoryChunk

logger = logging.getLogger("jistory.embeddings")

BATCH_SIZE = 32


def pack_embedding(vector: list[float]) -> bytes:
    return array.array("f", vector).tobytes()


def unpack_embedding(data: bytes) -> list[float]:
    arr = array.array("f")
    arr.frombytes(data)
    return arr.tolist()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0:
        return 0.0
    return dot / denom


def replace_chunks(
    db: Session,
    *,
    drafts: list[ChunkDraft],
    provider: EmbeddingProvider,
    conversation_ids: list[str],
) -> int:
    if conversation_ids:
        db.execute(delete(MemoryChunk).where(MemoryChunk.conversation_id.in_(conversation_ids)))
        db.flush()

    if not drafts:
        return 0

    stored = 0
    for i in range(0, len(drafts), BATCH_SIZE):
        batch = drafts[i : i + BATCH_SIZE]
        vectors = provider.embed_documents([d.text for d in batch])
        rows: list[MemoryChunk] = []
        for draft, vector in zip(batch, vectors, strict=False):
            rows.append(
                MemoryChunk(
                    id=str(uuid.uuid4()),
                    conversation_id=draft.conversation_id,
                    source=draft.source,
                    timestamp=draft.timestamp,
                    text=draft.text,
                    message_ids=json.dumps(draft.message_ids),
                    embedding=pack_embedding(vector) if vector else None,
                    embedding_model=provider.model_name,
                )
            )
        db.add_all(rows)
        db.flush()
        stored += len(rows)

    logger.info("Stored %d memory chunks", stored)
    return stored


def load_embedded_chunks(db: Session) -> list[MemoryChunk]:
    return list(
        db.scalars(select(MemoryChunk).where(MemoryChunk.embedding.is_not(None))).all()
    )
