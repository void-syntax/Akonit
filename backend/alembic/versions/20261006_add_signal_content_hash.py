"""add signal content_hash column

Revision ID: d52e1b3a9f21
Revises: c41d9a2b7e10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d52e1b3a9f21"
down_revision: str | None = "c41d9a2b7e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_signals_content_hash", "signals", ["content_hash"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_signals_content_hash", table_name="signals")
    op.drop_column("signals", "content_hash")

