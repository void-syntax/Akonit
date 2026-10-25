"""Add model tables and columns missing from the original migrations.

Revision ID: e81a0c6d3f42
Revises: d52e1b3a9f21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e81a0c6d3f42"
down_revision: str | None = "d52e1b3a9f21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("matched_at", sa.DateTime(timezone=True)))
    op.add_column("signals", sa.Column("ai_priority", sa.String(length=20)))
    op.add_column("signals", sa.Column("ai_priority_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("signals", sa.Column("ai_category", sa.String(length=40)))
    op.add_column("signals", sa.Column("ai_should_notify", sa.Float(), nullable=False, server_default="0"))
    op.add_column("signals", sa.Column("ai_noise_probability", sa.Float(), nullable=False, server_default="0"))
    op.add_column("signals", sa.Column("ai_trending_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("signals", sa.Column("ai_classified_at", sa.DateTime(timezone=True)))
    op.add_column(
        "user_profiles",
        sa.Column("telegram_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "intelligence_briefings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("core_thesis", sa.Text(), nullable=False),
        sa.Column("alpha_potential", sa.Text(), nullable=False),
        sa.Column("monetization_strategy", sa.Text(), nullable=False),
        sa.Column("risk_analysis", sa.Text(), nullable=False),
        sa.Column("sources_synthesized", sa.JSON(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id"),
    )
    op.create_index(
        "ix_intelligence_briefings_signal_id",
        "intelligence_briefings",
        ["signal_id"],
        unique=True,
    )

    op.create_table(
        "failed_signals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_retry_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_failed_signals_source", "failed_signals", ["source"])


def downgrade() -> None:
    op.drop_index("ix_failed_signals_source", table_name="failed_signals")
    op.drop_table("failed_signals")
    op.drop_index(
        "ix_intelligence_briefings_signal_id", table_name="intelligence_briefings"
    )
    op.drop_table("intelligence_briefings")
    op.drop_column("user_profiles", "telegram_alerts_enabled")
    op.drop_column("signals", "matched_at")
    op.drop_column("signals", "ai_classified_at")
    op.drop_column("signals", "ai_trending_score")
    op.drop_column("signals", "ai_noise_probability")
    op.drop_column("signals", "ai_should_notify")
    op.drop_column("signals", "ai_category")
    op.drop_column("signals", "ai_priority_score")
    op.drop_column("signals", "ai_priority")
