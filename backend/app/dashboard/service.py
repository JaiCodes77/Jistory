from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.graph.service import graph_counts
from app.graph.topics import STOPWORDS, TOKEN_RE
from app.models.conversation import Conversation
from app.models.import_job import ImportJob
from app.models.message import Message
from app.schemas.dashboard import (
    DashboardResponse,
    LatestImport,
    RecentConversation,
    SourceCount,
    TimeBucket,
    TopicCount,
)


def get_dashboard(db: Session) -> DashboardResponse:
    total_conversations = int(db.scalar(select(func.count()).select_from(Conversation)) or 0)
    total_messages = int(db.scalar(select(func.count()).select_from(Message)) or 0)

    source_rows = db.execute(
        select(Conversation.source, func.count()).group_by(Conversation.source)
    ).all()
    sources = [SourceCount(name=name, count=int(count)) for name, count in source_rows]

    latest_job = db.scalar(select(ImportJob).order_by(ImportJob.imported_at.desc()).limit(1))
    latest_import = None
    if latest_job is not None:
        latest_import = LatestImport(
            id=latest_job.id,
            source=latest_job.source,
            filename=latest_job.original_filename,
            imported_at=latest_job.imported_at,
            status=latest_job.status,
            conversations=latest_job.conversations_imported,
        )

    recent_rows = db.scalars(
        select(Conversation)
        .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
        .limit(8)
    ).all()
    recent = [
        RecentConversation(
            id=row.id,
            title=row.title,
            source=row.source,
            updated_at=row.updated_at or row.created_at,
            message_count=row.message_count,
        )
        for row in recent_rows
    ]

    time_buckets = _conversations_over_time(db)
    topics = _frequent_topics(db)
    graph_edges, graph_connected = graph_counts(db)

    return DashboardResponse(
        total_conversations=total_conversations,
        total_messages=total_messages,
        sources=sources,
        latest_import=latest_import,
        conversations_over_time=time_buckets,
        recent_conversations=recent,
        frequent_topics=topics,
        graph_edges=graph_edges,
        graph_connected=graph_connected,
    )


def _conversations_over_time(db: Session, *, window_days: int = 90) -> list[TimeBucket]:
    """Daily counts, padded so a single busy day does not become one full-width bar."""
    rows = db.execute(
        select(
            func.coalesce(
                Conversation.created_at,
                Conversation.first_message_at,
                Conversation.last_message_at,
            )
        )
    ).all()
    counts: Counter[str] = Counter()
    for (value,) in rows:
        day = _as_utc_date(value)
        if day is None:
            continue
        counts[day.isoformat()] += 1
    if not counts:
        return []

    today = datetime.now(timezone.utc).date()
    oldest = min(date.fromisoformat(key) for key in counts)
    start = max(oldest, today - timedelta(days=window_days - 1))
    min_span = min(29, window_days - 1)
    if (today - start).days < min_span:
        start = today - timedelta(days=min_span)

    buckets: list[TimeBucket] = []
    cursor = start
    while cursor <= today:
        key = cursor.isoformat()
        buckets.append(TimeBucket(date=key, count=counts.get(key, 0)))
        cursor += timedelta(days=1)
    return buckets


def _as_utc_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.date()
    return value


def _frequent_topics(db: Session) -> list[TopicCount]:
    titles = db.scalars(select(Conversation.title).where(Conversation.title.is_not(None))).all()
    counter: Counter[str] = Counter()
    for title in titles:
        for token in TOKEN_RE.findall(title or ""):
            lowered = token.lower()
            if lowered in STOPWORDS:
                continue
            counter[token] += 1
    return [TopicCount(term=term, count=count) for term, count in counter.most_common(8)]
