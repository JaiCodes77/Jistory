from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.graph.builder import (
    META_ID,
    ConversationNode,
    ensure_graph_built,
    load_conversation_nodes,
    load_display_nodes,
    rebuild_conversation_edges,
    score_pair,
)
from app.graph.topics import extract_terms
from app.models.conversation import Conversation
from app.models.graph import ConversationEdge, GraphMeta
from app.schemas.graph import (
    GraphEdge,
    GraphNode,
    GraphRebuildResponse,
    GraphResponse,
    RelatedConversation,
    RelatedResponse,
)


def get_graph(
    db: Session,
    *,
    source: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_weight: float = 0.0,
    include_isolated: bool = True,
) -> GraphResponse:
    ensure_graph_built(db)
    db.commit()

    nodes = load_display_nodes(db)
    filtered = [
        node
        for node in nodes
        if _matches_filters(node, source=source, date_from=date_from, date_to=date_to)
    ]
    allowed = {node.id for node in filtered}

    stmt = select(ConversationEdge)
    if min_weight > 0:
        stmt = stmt.where(ConversationEdge.weight >= min_weight)
    edge_rows = list(db.scalars(stmt).all())
    edges = [
        GraphEdge(
            source_id=row.source_id,
            target_id=row.target_id,
            weight=row.weight,
            reason=row.reason,
        )
        for row in edge_rows
        if row.source_id in allowed and row.target_id in allowed
    ]

    linked: set[str] = set()
    for edge in edges:
        linked.add(edge.source_id)
        linked.add(edge.target_id)

    if not include_isolated:
        filtered = [node for node in filtered if node.id in linked]

    isolated = sum(1 for node in filtered if node.id not in linked)
    degree: dict[str, int] = {node.id: 0 for node in filtered}
    for edge in edges:
        degree[edge.source_id] = degree.get(edge.source_id, 0) + 1
        degree[edge.target_id] = degree.get(edge.target_id, 0) + 1
    meta = db.get(GraphMeta, META_ID)
    truncated = int(db.scalar(select(func.count()).select_from(Conversation)) or 0) > len(nodes)

    return GraphResponse(
        nodes=[_to_graph_node(node, degree=degree.get(node.id, 0)) for node in filtered],
        edges=edges,
        built_at=meta.built_at if meta else None,
        truncated=truncated,
        isolated=isolated,
    )


def rebuild_graph(db: Session) -> GraphRebuildResponse:
    node_count, edge_count = rebuild_conversation_edges(db)
    db.commit()
    meta = db.get(GraphMeta, META_ID)
    return GraphRebuildResponse(
        nodes=node_count,
        edges=edge_count,
        built_at=meta.built_at if meta else None,
    )


def list_related(db: Session, conversation_id: str, *, limit: int = 8) -> RelatedResponse:
    row = db.get(Conversation, conversation_id)
    if row is None:
        raise AppError("Conversation not found.", code="not_found", status_code=404)

    ensure_graph_built(db)
    db.commit()

    edge_rows = list(
        db.scalars(
            select(ConversationEdge)
            .where(
                or_(
                    ConversationEdge.source_id == conversation_id,
                    ConversationEdge.target_id == conversation_id,
                )
            )
            .order_by(ConversationEdge.weight.desc())
            .limit(limit)
        ).all()
    )
    if not edge_rows:
        return RelatedResponse(items=_related_from_scoring(db, conversation_id, limit=limit))

    neighbor_ids = [
        edge.target_id if edge.source_id == conversation_id else edge.source_id
        for edge in edge_rows
    ]
    lookup = {node.id: node for node in load_display_nodes(db, ids=neighbor_ids)}

    items: list[RelatedConversation] = []
    for edge in edge_rows:
        other_id = edge.target_id if edge.source_id == conversation_id else edge.source_id
        node = lookup.get(other_id)
        if node is None:
            continue
        items.append(
            RelatedConversation(
                id=node.id,
                title=node.title,
                source=node.source,
                message_count=node.message_count,
                last_message_at=node.last_message_at or node.updated_at or node.created_at,
                snippet=node.snippet,
                weight=edge.weight,
                reason=edge.reason,
            )
        )
    return RelatedResponse(items=items)


def _related_from_scoring(
    db: Session, conversation_id: str, *, limit: int
) -> list[RelatedConversation]:
    """Score a conversation that has no stored edges (for example outside the 600-node cap)."""
    display_ids = {node.id for node in load_display_nodes(db)}
    if conversation_id in display_ids:
        return []

    focus_nodes = load_conversation_nodes(db, ids=[conversation_id])
    if not focus_nodes:
        return []
    focus = focus_nodes[0]
    others = [node for node in load_conversation_nodes(db) if node.id != conversation_id]
    ranked: list[tuple[ConversationNode, float, str]] = []
    for other in others:
        scored = score_pair(focus, other)
        if scored is None:
            continue
        ranked.append((other, scored.weight, scored.reason))
    ranked.sort(key=lambda item: item[1], reverse=True)

    items: list[RelatedConversation] = []
    for node, weight, reason in ranked[:limit]:
        items.append(
            RelatedConversation(
                id=node.id,
                title=node.title,
                source=node.source,
                message_count=node.message_count,
                last_message_at=node.last_message_at or node.updated_at or node.created_at,
                snippet=node.snippet,
                weight=weight,
                reason=reason,
            )
        )
    return items


def graph_counts(db: Session) -> tuple[int, int]:
    rows = db.execute(select(ConversationEdge.source_id, ConversationEdge.target_id)).all()
    if not rows:
        return 0, 0
    linked: set[str] = set()
    for source_id, target_id in rows:
        linked.add(source_id)
        linked.add(target_id)
    return len(rows), len(linked)


def _matches_filters(
    node: ConversationNode,
    *,
    source: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> bool:
    if source and node.source != source.strip():
        return False
    when = _as_utc(node.when)
    start = _as_utc(date_from)
    end = _as_utc(date_to)
    if start is not None and (when is None or when < start):
        return False
    if end is not None and (when is None or when > end):
        return False
    return True


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _to_graph_node(node: ConversationNode, *, degree: int = 0) -> GraphNode:
    topics = list(extract_terms(node.title).values())[:4]
    return GraphNode(
        id=node.id,
        title=node.title,
        source=node.source,
        message_count=node.message_count,
        created_at=node.created_at,
        last_message_at=node.last_message_at or node.updated_at or node.created_at,
        snippet=node.snippet,
        degree=degree,
        topics=topics,
    )
