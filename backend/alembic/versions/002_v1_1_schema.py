"""Additive V1.1 schema helpers.

Revision ID: 002_v1_1
Revises: 001_v1
Create Date: 2026-08-16

Startup still uses SQLAlchemy create_all plus ensure_runtime_schema.
This revision documents those additive upgrades and never drops jistory.db.
"""

from alembic import op

from app.db.fts import ensure_fts
from app.db.session import ensure_runtime_schema

revision = "002_v1_1"
down_revision = "001_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ensure_runtime_schema(bind)
    ensure_fts(bind)


def downgrade() -> None:
    # Additive only. Do not drop columns or destroy the local database.
    return
