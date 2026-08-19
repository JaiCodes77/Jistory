import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationEdge(Base):
    """Undirected link between two conversations. source_id is always the lesser UUID."""

    __tablename__ = "conversation_edges"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", name="uq_conversation_edge_pair"),
        Index("ix_edges_source_id", "source_id"),
        Index("ix_edges_target_id", "target_id"),
        Index("ix_edges_weight", "weight"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GraphMeta(Base):
    """Singleton row recording the last full graph rebuild."""

    __tablename__ = "graph_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
