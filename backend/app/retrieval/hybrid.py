from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.fts import fts_available, sanitize_fts_query, sanitize_fts_query_or
from app.embeddings.factory import get_embedding_provider
from app.embeddings.store import top_similar_chunks
from app.models.chunk import MemoryChunk
from app.models.conversation import Conversation
from app.models.message import Message

RECENCY_HALF_LIFE_DAYS = 90.0
HYBRID_SEARCH_CANDIDATES = 100


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
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
) -> tuple[list[RetrievedChunk], int]:
    scoped = _normalize_ids(conversation_ids)
    if not fts_available(db):
        return _like_fallback(
            db,
            query,
            limit=limit,
            offset=offset,
            conversation_ids=scoped,
            date_from=date_from,
            date_to=date_to,
            source=source,
        )

    match = sanitize_fts_query(query)
    if not match:
        if scoped:
            return _messages_for_conversations(
                db,
                scoped,
                limit=limit,
                offset=offset,
                date_from=date_from,
                date_to=date_to,
                source=source,
            )
        return [], 0

    rows = _fts_select(
        db,
        match,
        limit=limit,
        offset=offset,
        conversation_ids=scoped,
        date_from=date_from,
        date_to=date_to,
        source=source,
    )
    active = match
    if not rows:
        match_or = sanitize_fts_query_or(query)
        if match_or and match_or != match:
            rows = _fts_select(
                db,
                match_or,
                limit=limit,
                offset=offset,
                conversation_ids=scoped,
                date_from=date_from,
                date_to=date_to,
                source=source,
            )
            active = match_or

    extra_sql, extra_params = _hit_filter_sql(
        scoped, date_from=date_from, date_to=date_to, source=source
    )
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
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
):
    extra_sql, extra_params = _hit_filter_sql(
        conversation_ids, date_from=date_from, date_to=date_to, source=source
    )
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
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
) -> tuple[list[RetrievedChunk], int]:
    scoped = _normalize_ids(conversation_ids)
    term = f"%{query.strip()}%"
    filters = [Message.content.ilike(term)]
    if scoped:
        filters.append(Message.conversation_id.in_(scoped))
    filters.extend(_message_time_filters(date_from, date_to))
    if source:
        filters.append(Conversation.source == source)
    total = int(
        db.scalar(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(*filters)
        )
        or 0
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
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
) -> list[RetrievedChunk]:
    scoped = _normalize_ids(conversation_ids)
    provider = get_embedding_provider(settings)
    query_vec = provider.embed_query(query)
    if not query_vec:
        return []

    scored = top_similar_chunks(
        db,
        query_vec,
        limit=max(limit, 1),
        conversation_ids=scoped or None,
        date_from=date_from,
        date_to=date_to,
        source=source,
    )
    if not scored:
        return []

    title_ids = {chunk.conversation_id for chunk in scored}
    titles = {
        row.id: row.title
        for row in db.scalars(select(Conversation).where(Conversation.id.in_(list(title_ids)))).all()
    }

    hits: list[RetrievedChunk] = []
    min_score = 0.0 if scoped else 0.22
    for chunk in scored[:limit]:
        if chunk.score < min_score:
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
                score=chunk.score,
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
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
) -> list[RetrievedChunk]:
    scoped = _normalize_ids(conversation_ids)
    top_n = limit or settings.retrieval_limit
    pool = max(top_n * 3, 12)
    fts_hits, _ = search_fts(
        db,
        query,
        limit=pool,
        offset=0,
        conversation_ids=scoped,
        date_from=date_from,
        date_to=date_to,
        source=source,
    )
    semantic_hits = search_semantic(
        db,
        query,
        settings,
        limit=pool,
        conversation_ids=scoped,
        date_from=date_from,
        date_to=date_to,
        source=source,
    )
    fused = reciprocal_rank_fusion(fts_hits, semantic_hits, limit=top_n)
    if scoped:
        allowed = set(scoped)
        fused = [hit for hit in fused if hit.conversation_id in allowed]
        if not fused:
            return fallback_conversation_chunks(
                db,
                scoped,
                limit=top_n,
                date_from=date_from,
                date_to=date_to,
                source=source,
            )
    return fused


def fallback_conversation_chunks(
    db: Session,
    conversation_ids: Sequence[str],
    *,
    limit: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
) -> list[RetrievedChunk]:
    """When a tagged chat has no query hits, still give Ask the tagged history."""
    scoped = _normalize_ids(conversation_ids)
    if not scoped:
        return []

    filters = [MemoryChunk.conversation_id.in_(scoped)]
    filters.extend(_chunk_time_filters(date_from, date_to))
    if source:
        filters.append(MemoryChunk.source == source)
    chunks = list(
        db.scalars(
            select(MemoryChunk)
            .where(*filters)
            .order_by(MemoryChunk.timestamp.desc(), MemoryChunk.id.desc())
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

    messages, _ = _messages_for_conversations(
        db,
        scoped,
        limit=min(16, max(limit, 8)),
        offset=0,
        date_from=date_from,
        date_to=date_to,
        source=source,
    )
    for hit in messages:
        hit.match_type = "tagged"
    return messages


def _messages_for_conversations(
    db: Session,
    conversation_ids: Sequence[str],
    *,
    limit: int,
    offset: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
) -> tuple[list[RetrievedChunk], int]:
    scoped = _normalize_ids(conversation_ids)
    if not scoped:
        return [], 0
    filters = [Message.conversation_id.in_(scoped)]
    filters.extend(_message_time_filters(date_from, date_to))
    if source:
        filters.append(Conversation.source == source)
    total = int(
        db.scalar(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(*filters)
        )
        or 0
    )
    stmt = (
        select(Message, Conversation)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(*filters)
        .order_by(Message.created_at.desc(), Message.sequence_number.desc())
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


def _hit_filter_sql(
    conversation_ids: Sequence[str] | None,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = None,
) -> tuple[str, dict[str, str]]:
    sql, params = _id_filter_sql(conversation_ids)
    if source and source.strip():
        sql += " AND source = :hit_source"
        params["hit_source"] = source.strip()
    start, end = _fts_date_bounds(date_from, date_to)
    if start:
        sql += " AND created_at >= :date_from"
        params["date_from"] = start
    if end:
        sql += " AND created_at <= :date_to"
        params["date_to"] = end
    return sql, params


def _fts_date_bounds(
    date_from: datetime | None, date_to: datetime | None
) -> tuple[str | None, str | None]:
    start = _as_fts_timestamp(date_from)
    end = _as_fts_timestamp(date_to)
    return start, end


def _as_fts_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%d %H:%M:%S")


def _message_time_filters(date_from: datetime | None, date_to: datetime | None) -> list:
    filters = []
    if date_from is not None:
        filters.append(Message.created_at >= date_from)
    if date_to is not None:
        filters.append(Message.created_at <= date_to)
    return filters


def _chunk_time_filters(date_from: datetime | None, date_to: datetime | None) -> list:
    filters = []
    if date_from is not None:
        filters.append(MemoryChunk.timestamp >= date_from)
    if date_to is not None:
        filters.append(MemoryChunk.timestamp <= date_to)
    return filters


def reciprocal_rank_fusion(
    keyword_hits: list[RetrievedChunk],
    semantic_hits: list[RetrievedChunk],
    *,
    limit: int,
    k: int = 60,
) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    meta: dict[str, RetrievedChunk] = {}
    now = datetime.now(timezone.utc)

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

    ordered = sorted(
        scores.items(),
        key=lambda item: item[1] * _recency_weight(meta[item[0]].timestamp, now),
        reverse=True,
    )
    results: list[RetrievedChunk] = []
    seen_messages: set[str] = set()
    for key, score in ordered:
        hit = meta[key]
        ids = set(hit.message_ids or [])
        if hit.message_id:
            ids.add(hit.message_id)
        if ids & seen_messages:
            continue
        seen_messages.update(ids)
        hit.score = score * _recency_weight(hit.timestamp, now)
        results.append(hit)
        if len(results) >= limit:
            break
    return results


def _recency_weight(value: datetime | None, now: datetime) -> float:
    if value is None:
        return 0.7
    timestamp = value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - timestamp.astimezone(timezone.utc)).total_seconds() / 86400.0)
    return 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)


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
