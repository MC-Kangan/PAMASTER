from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_broker_daily_nav"
down_revision: str | None = "0010_broker_daily_pnl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_daily_nav",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.String(length=64),
            sa.ForeignKey("accounts.account_id"),
            nullable=False,
        ),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("starting_value", sa.Numeric(24, 8), nullable=False),
        sa.Column("ending_value", sa.Numeric(24, 8), nullable=False),
        sa.Column("mtm", sa.Numeric(24, 8), nullable=False),
        sa.Column("realized", sa.Numeric(24, 8), nullable=False),
        sa.Column("change_in_unrealized", sa.Numeric(24, 8), nullable=False),
        sa.Column("deposits_withdrawals", sa.Numeric(24, 8), nullable=False),
        sa.Column("commissions", sa.Numeric(24, 8), nullable=False),
        sa.Column("dividends", sa.Numeric(24, 8), nullable=False),
        sa.Column("interest", sa.Numeric(24, 8), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "report_date",
            "provider",
            name="uq_broker_daily_nav_account_date_provider",
        ),
    )
    op.create_index(
        "ix_broker_daily_nav_account_id",
        "broker_daily_nav",
        ["account_id"],
    )
    op.create_index(
        "ix_broker_daily_nav_report_date",
        "broker_daily_nav",
        ["report_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_broker_daily_nav_report_date", table_name="broker_daily_nav")
    op.drop_index("ix_broker_daily_nav_account_id", table_name="broker_daily_nav")
    op.drop_table("broker_daily_nav")
