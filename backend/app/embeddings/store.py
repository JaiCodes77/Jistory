from __future__ import annotations

import array
import heapq
import json
import logging
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

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


@dataclass(frozen=True)
class ScoredChunk:
    score: float
    conversation_id: str
    source: str
    timestamp: datetime | None
    text: str
    message_ids: str


def top_similar_chunks(
    db: Session,
    query_vec: list[float],
    *,
    limit: int,
    conversation_ids: Sequence[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
) -> list[ScoredChunk]:
    """Score embeddings in a bounded heap so the full vector table is not held in RAM."""
    if limit <= 0 or not query_vec:
        return []

    stmt = (
        select(
            MemoryChunk.conversation_id,
            MemoryChunk.source,
            MemoryChunk.timestamp,
            MemoryChunk.text,
            MemoryChunk.message_ids,
            MemoryChunk.embedding,
        )
        .where(MemoryChunk.embedding.is_not(None))
        .execution_options(yield_per=64)
    )
    if conversation_ids:
        stmt = stmt.where(MemoryChunk.conversation_id.in_(list(conversation_ids)))
    if date_from is not None:
        stmt = stmt.where(MemoryChunk.timestamp >= date_from)
    if date_to is not None:
        stmt = stmt.where(MemoryChunk.timestamp <= date_to)
    if source and source.strip():
        stmt = stmt.where(MemoryChunk.source == source.strip())

    heap: list[tuple[float, int, ScoredChunk]] = []
    seq = 0
    for row in db.execute(stmt):
        blob = row.embedding
        if not blob:
            continue
        score = cosine(query_vec, unpack_embedding(blob))
        seq += 1
        item = ScoredChunk(
            score=score,
            conversation_id=row.conversation_id,
            source=row.source,
            timestamp=row.timestamp,
            text=row.text,
            message_ids=row.message_ids,
        )
        if len(heap) < limit:
            heapq.heappush(heap, (score, seq, item))
        elif score > heap[0][0]:
            heapq.heapreplace(heap, (score, seq, item))

    ranked = sorted(heap, key=lambda entry: entry[0], reverse=True)
    return [entry[2] for entry in ranked]
