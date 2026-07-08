from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
    )
    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.String(length=64),
            sa.ForeignKey("accounts.account_id"),
            nullable=False,
        ),
        sa.Column(
            "symbol",
            sa.String(length=64),
            sa.ForeignKey("instruments.symbol"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("average_cost", sa.Numeric(24, 8), nullable=False),
        sa.Column("latest_price", sa.Numeric(24, 8), nullable=True),
        sa.UniqueConstraint("account_id", "symbol", name="uq_position_account_symbol"),
    )
    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "symbol",
            sa.String(length=64),
            sa.ForeignKey("instruments.symbol"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "symbol",
            "observed_at",
            "provider",
            name="uq_price_symbol_time_provider",
        ),
    )
    op.create_table(
        "signals",
        sa.Column("signal_id", sa.String(length=64), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("deterministic_recommendation", sa.String(length=1024), nullable=False),
        sa.Column("audit_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analytics_path", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("signals")
    op.drop_table("prices")
    op.drop_table("positions")
    op.drop_table("instruments")
    op.drop_table("accounts")
