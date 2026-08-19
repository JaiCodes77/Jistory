"""Additive V2 memory graph tables.

Revision ID: 003_v2_graph
Revises: 002_v1_1
Create Date: 2026-08-19

Startup still uses SQLAlchemy create_all plus ensure_runtime_schema.
This revision documents conversation_edges / graph_meta and never drops jistory.db.
"""

from alembic import op

from app.db.base import Base
from app.db.session import ensure_runtime_schema
import app.models  # noqa: F401

revision = "003_v2_graph"
down_revision = "002_v1_1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    ensure_runtime_schema(bind)


def downgrade() -> None:
    # Additive only. Do not drop columns or destroy the local database.
    return
