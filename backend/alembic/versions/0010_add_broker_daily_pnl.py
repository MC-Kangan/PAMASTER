from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_broker_daily_pnl"
down_revision: str | None = "0009_historical_market_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_daily_pnl",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.String(length=64),
            sa.ForeignKey("accounts.account_id"),
            nullable=False,
        ),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("previous_close_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("previous_close_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("close_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("close_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("transaction_mtm", sa.Numeric(24, 8), nullable=False),
        sa.Column("prior_open_mtm", sa.Numeric(24, 8), nullable=False),
        sa.Column("commissions", sa.Numeric(24, 8), nullable=False),
        sa.Column("total", sa.Numeric(24, 8), nullable=False),
        sa.Column("is_total", sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "report_date",
            "provider",
            "symbol",
            "asset_class",
            name="uq_broker_daily_pnl_account_date_symbol",
        ),
    )
    op.create_index(
        "ix_broker_daily_pnl_account_id",
        "broker_daily_pnl",
        ["account_id"],
    )
    op.create_index(
        "ix_broker_daily_pnl_report_date",
        "broker_daily_pnl",
        ["report_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_broker_daily_pnl_report_date", table_name="broker_daily_pnl")
    op.drop_index("ix_broker_daily_pnl_account_id", table_name="broker_daily_pnl")
    op.drop_table("broker_daily_pnl")
