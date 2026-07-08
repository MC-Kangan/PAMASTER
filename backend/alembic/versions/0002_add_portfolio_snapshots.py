from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_add_portfolio_snapshots"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("audit_id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
    )
    op.create_table(
        "portfolio_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("nav", sa.Numeric(24, 8), nullable=False),
        sa.Column("gross_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("net_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(24, 8), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_snapshots")
    op.drop_table("audit_events")
