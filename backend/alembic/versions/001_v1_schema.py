"""Initial Jistory V1 schema.

Revision ID: 001_v1
Revises:
Create Date: 2026-08-16
"""

from alembic import op
from sqlalchemy import inspect

from app.db.base import Base
from app.db.fts import ensure_fts
import app.models  # noqa: F401

revision = "001_v1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    ensure_fts(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in reversed(Base.metadata.sorted_tables):
        if inspector.has_table(table.name):
            table.drop(bind)
    op.execute("DROP TABLE IF EXISTS messages_fts")
