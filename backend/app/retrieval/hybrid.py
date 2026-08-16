from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.fts import fts_available, sanitize_fts_query, sanitize_fts_query_or
from app.embeddings.factory import get_embedding_provider
from app.embeddings.store import cosine, load_embedded_chunks, unpack_embedding
from app.models.chunk import MemoryChunk
from app.models.conversation import Conversation
from app.models.message import Message


@dataclass
class RetrievedChunk:
    conversation_id: str
    message_id: str
    message_ids: list[str]
    conversation_title: str | None
    source: str
    timestamp: datetime | None
    snippet: str
    text: str
    score: float
    match_type: str


def _strip_highlight(snippet: str) -> str:
    return snippet.replace("«", "").replace("»", "")


def search_fts(
    db: Session,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
    conversation_ids: Sequence[str] | None = None,
) -> tuple[list[RetrievedChunk], int]:
    scoped = _normalize_ids(conversation_ids)
    if not fts_available(db):
        return _like_fallback(db, query, limit=limit, offset=offset, conversation_ids=scoped)

    match = sanitize_fts_query(query)
    if not match:
        if scoped:
            return _messages_for_conversations(db, scoped, limit=limit, offset=offset)
        return [], 0

    rows = _fts_select(db, match, limit=limit, offset=offset, conversation_ids=scoped)
    active = match
    if not rows:
        match_or = sanitize_fts_query_or(query)
        if match_or and match_or != match:
            rows = _fts_select(db, match_or, limit=limit, offset=offset, conversation_ids=scoped)
            active = match_or

    extra_sql, extra_params = _id_filter_sql(scoped)
    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH :q{extra_sql}"),
        {"q": active, **extra_params},
    ).scalar()
    total = int(count_row or 0)

    hits: list[RetrievedChunk] = []
    for row in rows:
        snippet = row[3] or ""
        hits.append(
            RetrievedChunk(
                conversation_id=row[0],
                message_id=row[1],
                message_ids=[row[1]],
                conversation_title=row[2],
                snippet=_strip_highlight(snippet),
                source=row[4],
                timestamp=_parse_ts(row[5]),
                text=snippet,
                score=float(row[6] or 0),
                match_type="keyword",
            )
        )
    return hits, total


def _fts_select(
    db: Session,
    match: str,
    *,
    limit: int,
    offset: int,
    conversation_ids: Sequence[str] | None = None,
):
    extra_sql, extra_params = _id_filter_sql(conversation_ids)
    return db.execute(
        text(
            f"""
            SELECT
                conversation_id,
                message_id,
                title,
                snippet(messages_fts, 0, '«', '»', '…', 18),
                source,
                created_at,
                bm25(messages_fts)
            FROM messages_fts
            WHERE messages_fts MATCH :q{extra_sql}
            ORDER BY bm25(messages_fts)
            LIMIT :limit OFFSET :offset
            """
        ),
        {"q": match, "limit": limit, "offset": offset, **extra_params},
    ).fetchall()


def _like_fallback(
    db: Session,
    query: str,
    *,
    limit: int,
    offset: int,
    conversation_ids: Sequence[str] | None = None,
) -> tuple[list[RetrievedChunk], int]:
    scoped = _normalize_ids(conversation_ids)
    term = f"%{query.strip()}%"
    filters = [Message.content.ilike(term)]
    if scoped:
        filters.append(Message.conversation_id.in_(scoped))
    total = int(
        db.scalar(select(func.count()).select_from(Message).where(*filters)) or 0
    )
    stmt = (
        select(Message, Conversation)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(*filters)
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    hits: list[RetrievedChunk] = []
    for message, conversation in db.execute(stmt).all():
        snippet = (message.content or "")[:240]
        hits.append(
            RetrievedChunk(
                conversation_id=conversation.id,
                message_id=message.id,
                message_ids=[message.id],
                conversation_title=conversation.title,
                snippet=snippet,
                source=conversation.source,
                timestamp=message.created_at,
                text=message.content or "",
                score=0.0,
                match_type="keyword",
            )
        )
    return hits, total


def search_semantic(
    db: Session,
    query: str,
    settings: Settings,
    *,
    limit: int = 20,
    conversation_ids: Sequence[str] | None = None,
) -> list[RetrievedChunk]:
    scoped = _normalize_ids(conversation_ids)
    chunks = load_embedded_chunks(db, conversation_ids=scoped)
    if not chunks:
        return []

    provider = get_embedding_provider(settings)
    query_vec = provider.embed_query(query)
    if not query_vec:
        return []

    scored: list[tuple[float, MemoryChunk]] = []
    for chunk in chunks:
        if not chunk.embedding:
            continue
        vec = unpack_embedding(chunk.embedding)
        scored.append((cosine(query_vec, vec), chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    title_ids = {chunk.conversation_id for _, chunk in scored[: limit * 3]}
    titles = {
        row.id: row.title
        for row in db.scalars(select(Conversation).where(Conversation.id.in_(list(title_ids)))).all()
    }

    hits: list[RetrievedChunk] = []
    min_score = 0.0 if scoped else 0.22
    for score, chunk in scored[:limit]:
        if score < min_score:
            continue
        ids = _message_ids(chunk.message_ids)
        snippet = (chunk.text or "").replace("\n", " ")
        if len(snippet) > 280:
            snippet = snippet[:277] + "…"
        hits.append(
            RetrievedChunk(
                conversation_id=chunk.conversation_id,
                message_id=ids[0] if ids else "",
                message_ids=ids,
                conversation_title=titles.get(chunk.conversation_id),
                snippet=snippet,
                source=chunk.source,
                timestamp=chunk.timestamp,
                text=chunk.text,
                score=score,
                match_type="semantic",
            )
        )
    return hits


def hybrid_retrieve(
    db: Session,
    query: str,
    settings: Settings,
    *,
    limit: int | None = None,
    conversation_ids: Sequence[str] | None = None,
) -> list[RetrievedChunk]:
    scoped = _normalize_ids(conversation_ids)
    top_n = limit or settings.retrieval_limit
    pool = max(top_n * 3, 12)
    fts_hits, _ = search_fts(db, query, limit=pool, offset=0, conversation_ids=scoped)
    semantic_hits = search_semantic(
        db, query, settings, limit=pool, conversation_ids=scoped
    )
    fused = reciprocal_rank_fusion(fts_hits, semantic_hits, limit=top_n)
    if scoped:
        allowed = set(scoped)
        fused = [hit for hit in fused if hit.conversation_id in allowed]
        if not fused:
            return fallback_conversation_chunks(db, scoped, limit=top_n)
    return fused


def fallback_conversation_chunks(
    db: Session,
    conversation_ids: Sequence[str],
    *,
    limit: int,
) -> list[RetrievedChunk]:
    """When a tagged chat has no query hits, still give Ask the tagged history."""
    scoped = _normalize_ids(conversation_ids)
    if not scoped:
        return []

    chunks = list(
        db.scalars(
            select(MemoryChunk)
            .where(MemoryChunk.conversation_id.in_(scoped))
            .order_by(MemoryChunk.timestamp.asc())
            .limit(min(16, max(limit, 8)))
        ).all()
    )
    if chunks:
        titles = {
            row.id: row.title
            for row in db.scalars(
                select(Conversation).where(Conversation.id.in_(list({c.conversation_id for c in chunks})))
            ).all()
        }
        hits: list[RetrievedChunk] = []
        for chunk in chunks:
            ids = _message_ids(chunk.message_ids)
            snippet = (chunk.text or "").replace("\n", " ")
            if len(snippet) > 280:
                snippet = snippet[:277] + "…"
            hits.append(
                RetrievedChunk(
                    conversation_id=chunk.conversation_id,
                    message_id=ids[0] if ids else "",
                    message_ids=ids,
                    conversation_title=titles.get(chunk.conversation_id),
                    snippet=snippet,
                    source=chunk.source,
                    timestamp=chunk.timestamp,
                    text=chunk.text,
                    score=0.0,
                    match_type="tagged",
                )
            )
        return hits

    messages, _ = _messages_for_conversations(db, scoped, limit=min(16, max(limit, 8)), offset=0)
    for hit in messages:
        hit.match_type = "tagged"
    return messages


def _messages_for_conversations(
    db: Session,
    conversation_ids: Sequence[str],
    *,
    limit: int,
    offset: int,
) -> tuple[list[RetrievedChunk], int]:
    scoped = _normalize_ids(conversation_ids)
    if not scoped:
        return [], 0
    total = int(
        db.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id.in_(scoped))
        )
        or 0
    )
    stmt = (
        select(Message, Conversation)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.conversation_id.in_(scoped))
        .order_by(Message.sequence_number.asc(), Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    hits: list[RetrievedChunk] = []
    for message, conversation in db.execute(stmt).all():
        snippet = (message.content or "")[:240]
        hits.append(
            RetrievedChunk(
                conversation_id=conversation.id,
                message_id=message.id,
                message_ids=[message.id],
                conversation_title=conversation.title,
                snippet=snippet,
                source=conversation.source,
                timestamp=message.created_at,
                text=message.content or "",
                score=0.0,
                match_type="keyword",
            )
        )
    return hits, total


def _normalize_ids(conversation_ids: Sequence[str] | None) -> list[str]:
    if not conversation_ids:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in conversation_ids:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _id_filter_sql(conversation_ids: Sequence[str] | None) -> tuple[str, dict[str, str]]:
    scoped = _normalize_ids(conversation_ids)
    if not scoped:
        return "", {}
    params = {f"cid{index}": value for index, value in enumerate(scoped)}
    placeholders = ", ".join(f":cid{index}" for index in range(len(scoped)))
    return f" AND conversation_id IN ({placeholders})", params


def reciprocal_rank_fusion(
    keyword_hits: list[RetrievedChunk],
    semantic_hits: list[RetrievedChunk],
    *,
    limit: int,
    k: int = 60,
) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    meta: dict[str, RetrievedChunk] = {}

    def add(hits: list[RetrievedChunk], weight: float) -> None:
        for rank, hit in enumerate(hits):
            key = hit.message_id or f"{hit.conversation_id}:{rank}"
            scores[key] = scores.get(key, 0.0) + weight / (k + rank + 1)
            stored = meta.get(key)
            if stored is None:
                meta[key] = hit
            elif hit.match_type != stored.match_type:
                stored.match_type = "hybrid"

    add(keyword_hits, 1.0)
    add(semantic_hits, 1.0)

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    results: list[RetrievedChunk] = []
    seen: set[str] = set()
    for key, score in ordered:
        hit = meta[key]
        dedupe = f"{hit.conversation_id}:{hit.message_id}"
        if dedupe in seen:
            continue
        seen.add(dedupe)
        hit.score = score
        results.append(hit)
        if len(results) >= limit:
            break
    return results


def _message_ids(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(item) for item in data]
    except json.JSONDecodeError:
        return []
    return []


def _parse_ts(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text_value = str(value)
    try:
        return datetime.fromisoformat(text_value.replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None
