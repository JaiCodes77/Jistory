from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.embeddings.store import cosine, unpack_embedding
from app.graph.topics import extract_terms, shared_display
from app.models.chunk import MemoryChunk
from app.models.conversation import Conversation
from app.models.graph import ConversationEdge, GraphMeta

logger = logging.getLogger("jistory.graph")

SIMILARITY_THRESHOLD = 0.58
SIMILARITY_WITH_TOPIC = 0.40
MAX_NEIGHBORS = 10
MAX_CONVERSATIONS = 600
TEMPORAL_DAYS = 3
SNIPPET_CHARS = 180
META_ID = 1


@dataclass
class ConversationNode:
    id: str
    title: str | None
    source: str
    message_count: int
    created_at: datetime | None
    updated_at: datetime | None
    last_message_at: datetime | None
    snippet: str = ""
    embedding: list[float] | None = None
    title_terms: dict[str, str] = field(default_factory=dict)
    body_terms: dict[str, str] = field(default_factory=dict)

    @property
    def when(self) -> datetime | None:
        return self.last_message_at or self.updated_at or self.created_at


def rebuild_conversation_edges(db: Session) -> tuple[int, int]:
    """Replace stored edges from current conversations and embeddings."""
    nodes = load_conversation_nodes(db)
    candidates = score_pairs(nodes)
    edges = prune_neighbors(candidates)
    db.execute(delete(ConversationEdge))
    now = datetime.now(timezone.utc)
    rows = [
        ConversationEdge(
            id=str(uuid.uuid4()),
            source_id=edge.source_id,
            target_id=edge.target_id,
            weight=edge.weight,
            reason=edge.reason,
            created_at=now,
        )
        for edge in edges
    ]
    if rows:
        db.add_all(rows)
    _upsert_meta(db, conversation_count=len(nodes), edge_count=len(rows), built_at=now)
    db.flush()
    logger.info("Rebuilt memory graph nodes=%s edges=%s", len(nodes), len(rows))
    return len(nodes), len(rows)


def invalidate_graph(db: Session) -> None:
    """Clear built_at so the next graph read rebuilds."""
    meta = db.get(GraphMeta, META_ID)
    if meta is None:
        meta = GraphMeta(id=META_ID, conversation_count=0, edge_count=0)
        db.add(meta)
    meta.built_at = None
    db.flush()


def ensure_graph_built(db: Session) -> None:
    """Rebuild once if this database has never computed a graph (v1.2 → v2)."""
    meta = db.get(GraphMeta, META_ID)
    if meta is not None and meta.built_at is not None:
        return
    conversation_count = int(db.scalar(select(func.count()).select_from(Conversation)) or 0)
    if conversation_count < 2:
        _upsert_meta(
            db,
            conversation_count=conversation_count,
            edge_count=0,
            built_at=datetime.now(timezone.utc),
        )
        db.flush()
        return
    rebuild_conversation_edges(db)


def load_conversation_rows(db: Session, *, ids: list[str] | None = None) -> list[Conversation]:
    stmt = select(Conversation)
    if ids:
        stmt = stmt.where(Conversation.id.in_(ids))
    else:
        stmt = stmt.order_by(
            func.coalesce(
                Conversation.updated_at,
                Conversation.created_at,
                Conversation.last_message_at,
            ).desc()
        ).limit(MAX_CONVERSATIONS)
    return list(db.scalars(stmt).all())


def load_display_nodes(db: Session, *, ids: list[str] | None = None) -> list[ConversationNode]:
    rows = load_conversation_rows(db, ids=ids)
    if not rows:
        return []
    texts = _chunk_texts(db, [row.id for row in rows])
    nodes: list[ConversationNode] = []
    for row in rows:
        body_parts = texts.get(row.id) or []
        snippet_source = " ".join(body_parts[:2]) if body_parts else (row.title or "")
        nodes.append(
            ConversationNode(
                id=row.id,
                title=row.title,
                source=row.source,
                message_count=row.message_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
                last_message_at=row.last_message_at,
                snippet=_snippet(snippet_source),
            )
        )
    return nodes


def load_conversation_nodes(db: Session, *, ids: list[str] | None = None) -> list[ConversationNode]:
    rows = load_conversation_rows(db, ids=ids)
    if not rows:
        return []

    ids = [row.id for row in rows]
    chunk_rows = db.execute(
        select(MemoryChunk.conversation_id, MemoryChunk.text, MemoryChunk.embedding).where(
            MemoryChunk.conversation_id.in_(ids)
        )
    ).all()

    texts: dict[str, list[str]] = {cid: [] for cid in ids}
    vectors: dict[str, list[list[float]]] = {cid: [] for cid in ids}
    for conversation_id, text, blob in chunk_rows:
        if text:
            texts.setdefault(conversation_id, []).append(text)
        if blob:
            vectors.setdefault(conversation_id, []).append(unpack_embedding(blob))

    nodes: list[ConversationNode] = []
    for row in rows:
        body_parts = texts.get(row.id) or []
        snippet_source = " ".join(body_parts[:2]) if body_parts else (row.title or "")
        nodes.append(
            ConversationNode(
                id=row.id,
                title=row.title,
                source=row.source,
                message_count=row.message_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
                last_message_at=row.last_message_at,
                snippet=_snippet(snippet_source),
                embedding=_mean_unit(vectors.get(row.id) or []),
                title_terms=extract_terms(row.title),
                body_terms=extract_terms(" ".join(body_parts[:4])),
            )
        )
    return nodes


def _chunk_texts(db: Session, ids: list[str]) -> dict[str, list[str]]:
    if not ids:
        return {}
    rows = db.execute(
        select(MemoryChunk.conversation_id, MemoryChunk.text).where(
            MemoryChunk.conversation_id.in_(ids)
        )
    ).all()
    texts: dict[str, list[str]] = {cid: [] for cid in ids}
    for conversation_id, text in rows:
        if text:
            texts.setdefault(conversation_id, []).append(text)
    return texts


@dataclass(frozen=True)
class ScoredEdge:
    source_id: str
    target_id: str
    weight: float
    reason: str


def score_pairs(nodes: list[ConversationNode]) -> list[ScoredEdge]:
    edges: list[ScoredEdge] = []
    for i, left in enumerate(nodes):
        for right in nodes[i + 1 :]:
            scored = score_pair(left, right)
            if scored is not None:
                edges.append(scored)
    return edges


def score_pair(left: ConversationNode, right: ConversationNode) -> ScoredEdge | None:
    sim = 0.0
    if left.embedding and right.embedding:
        sim = cosine(left.embedding, right.embedding)

    shared_title = shared_display(left.title_terms, right.title_terms)
    shared_body = [
        term
        for term in shared_display(left.body_terms, right.body_terms, limit=4)
        if term.lower() not in {item.lower() for item in shared_title}
    ]
    topic_labels = (shared_title + shared_body)[:2]

    days = _day_gap(left.when, right.when)
    temporal = days is not None and days <= TEMPORAL_DAYS

    keep = bool(shared_title) or sim >= SIMILARITY_THRESHOLD
    if not keep and topic_labels and sim >= SIMILARITY_WITH_TOPIC:
        keep = True
    if not keep:
        return None

    topic_boost = 0.20 * min(2, len(shared_title)) + 0.08 * min(2, len(shared_body))
    temporal_boost = 0.05 if temporal else 0.0
    weight = min(1.0, max(0.0, 0.72 * sim + topic_boost + temporal_boost))
    if shared_title:
        weight = max(weight, 0.42)

    parts: list[str] = []
    if shared_title:
        parts.append("shared topic: " + ", ".join(shared_title[:2]))
    if sim >= SIMILARITY_THRESHOLD:
        parts.append("similar content")
    if temporal:
        parts.append("close in time")
    reason = " · ".join(parts) if parts else "similar content"

    source_id, target_id = _ordered(left.id, right.id)
    return ScoredEdge(source_id=source_id, target_id=target_id, weight=round(weight, 4), reason=reason)


def prune_neighbors(edges: list[ScoredEdge], *, limit: int = MAX_NEIGHBORS) -> list[ScoredEdge]:
    if not edges:
        return []
    by_node: dict[str, list[ScoredEdge]] = {}
    for edge in edges:
        by_node.setdefault(edge.source_id, []).append(edge)
        by_node.setdefault(edge.target_id, []).append(edge)

    kept: set[tuple[str, str]] = set()
    for node_edges in by_node.values():
        ranked = sorted(node_edges, key=lambda item: item.weight, reverse=True)[:limit]
        for edge in ranked:
            kept.add((edge.source_id, edge.target_id))

    return [edge for edge in edges if (edge.source_id, edge.target_id) in kept]


def _upsert_meta(
    db: Session,
    *,
    conversation_count: int,
    edge_count: int,
    built_at: datetime,
) -> None:
    meta = db.get(GraphMeta, META_ID)
    if meta is None:
        meta = GraphMeta(id=META_ID)
        db.add(meta)
    meta.built_at = built_at
    meta.conversation_count = conversation_count
    meta.edge_count = edge_count


def _mean_unit(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    dim = len(vectors[0])
    acc = [0.0] * dim
    count = 0
    for vector in vectors:
        if len(vector) != dim:
            continue
        for i, value in enumerate(vector):
            acc[i] += value
        count += 1
    if count == 0:
        return None
    mean = [value / count for value in acc]
    norm = math.sqrt(sum(value * value for value in mean)) or 1.0
    return [value / norm for value in mean]


def _snippet(text: str) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= SNIPPET_CHARS:
        return compact
    return compact[: SNIPPET_CHARS - 1].rstrip() + "…"


def _day_gap(left: datetime | None, right: datetime | None) -> int | None:
    if left is None or right is None:
        return None
    if left.tzinfo is None:
        left = left.replace(tzinfo=timezone.utc)
    if right.tzinfo is None:
        right = right.replace(tzinfo=timezone.utc)
    return abs((left.date() - right.date()).days)


def _ordered(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)
