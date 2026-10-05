"""add signal momentum, tagging and expiry columns

These four columns exist on the Signal model but were never added to a
migration. SQLite hid the problem, because its tables are created straight from
the models, while Postgres is migrated by Alembic - so a fresh Postgres install
failed at runtime with "no such column: signals.expires_at" once per collected
event, with nothing in the logs pointing at the schema.

Adds the columns that make the engine work:

* velocity / density_count - smoothed momentum and burst detection, so status
  does not flip on a single noisy sample
* tags_updated_at - when tag matching last ran for this signal
* expires_at - the retention clock; cleanup deletes anything past it that has not
  been saved

Revision ID: c41d9a2b7e10
Revises: 789f7337b7bf
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c41d9a2b7e10"
down_revision: str | None = "789f7337b7bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("velocity", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "signals",
        sa.Column("density_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "signals",
        sa.Column("tags_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # expires_at is the retention cut-off, so cleanup filters on it every pass.
    op.create_index(
        "ix_signals_expires_at", "signals", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_signals_expires_at", table_name="signals")
    op.drop_column("signals", "expires_at")
    op.drop_column("signals", "tags_updated_at")
    op.drop_column("signals", "density_count")
    op.drop_column("signals", "velocity")