"""Store encrypted per-user Telegram bot credentials.

Revision ID: c930ba8f41d2
Revises: a71c2e9d4b60
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c930ba8f41d2"
down_revision: str | None = "a71c2e9d4b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("telegram_bot_token_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "telegram_bot_token_encrypted")
