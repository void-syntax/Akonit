"""Store content simhash separately from external id fingerprints.

Revision ID: a71c2e9d4b60
Revises: e81a0c6d3f42
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a71c2e9d4b60"
down_revision: str | None = "e81a0c6d3f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_events", sa.Column("text_hash", sa.String(length=16)))
    op.create_index("ix_source_events_text_hash", "source_events", ["text_hash"])


def downgrade() -> None:
    op.drop_index("ix_source_events_text_hash", table_name="source_events")
    op.drop_column("source_events", "text_hash")
