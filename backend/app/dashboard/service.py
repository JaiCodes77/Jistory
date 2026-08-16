from __future__ import annotations

import re
from collections import Counter
from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "of",
        "to",
        "for",
        "in",
        "on",
        "with",
        "about",
        "from",
        "how",
        "what",
        "why",
        "is",
        "it",
        "my",
        "we",
        "you",
        "your",
        "vs",
        "or",
        "into",
        "using",
        "use",
        "new",
        "untitled",
        "conversation",
        "chat",
    }
)
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{2,}")


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

    return DashboardResponse(
        total_conversations=total_conversations,
        total_messages=total_messages,
        sources=sources,
        latest_import=latest_import,
        conversations_over_time=time_buckets,
        recent_conversations=recent,
        frequent_topics=topics,
    )


def _conversations_over_time(db: Session) -> list[TimeBucket]:
    rows = db.scalars(select(Conversation.created_at)).all()
    counts: Counter[str] = Counter()
    for value in rows:
        if value is None:
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        counts[value.date().isoformat()] += 1
    return [
        TimeBucket(date=day, count=count)
        for day, count in sorted(counts.items())[-90:]
    ]


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
