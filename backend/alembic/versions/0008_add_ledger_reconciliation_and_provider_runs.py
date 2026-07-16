from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_operational_foundation"
down_revision: str | None = "0007_quotes_fx_reporting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("transaction_id", sa.String(length=160), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(length=64),
            sa.ForeignKey("accounts.account_id"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.String(length=128),
            sa.ForeignKey("instruments.instrument_id"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("unit_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("gross_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("fees", sa.Numeric(24, 8), nullable=False),
        sa.Column("taxes", sa.Numeric(24, 8), nullable=False),
        sa.Column("net_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_table(
        "broker_reconciliations",
        sa.Column("reconciliation_id", sa.String(length=160), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(length=64),
            sa.ForeignKey("accounts.account_id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("broker_nav", sa.Numeric(24, 8), nullable=False),
        sa.Column("calculated_nav", sa.Numeric(24, 8), nullable=False),
        sa.Column("nav_difference", sa.Numeric(24, 8), nullable=False),
        sa.Column("broker_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("calculated_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("cash_difference", sa.Numeric(24, 8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_index(
        "ix_broker_reconciliations_account_id",
        "broker_reconciliations",
        ["account_id"],
    )
    op.create_table(
        "provider_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
    )
    op.create_index("ix_provider_runs_provider", "provider_runs", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_provider_runs_provider", table_name="provider_runs")
    op.drop_table("provider_runs")
    op.drop_index(
        "ix_broker_reconciliations_account_id",
        table_name="broker_reconciliations",
    )
    op.drop_table("broker_reconciliations")
    op.drop_index("ix_transactions_account_id", table_name="transactions")
    op.drop_table("transactions")
