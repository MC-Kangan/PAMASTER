from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_quotes_fx_reporting"
down_revision: str | None = "0006_instrument_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_data_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_id",
            sa.String(length=128),
            sa.ForeignKey("instruments.instrument_id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_symbol", sa.String(length=128), nullable=False),
        sa.Column("provider_exchange", sa.String(length=128), nullable=True),
        sa.Column("expected_currency", sa.String(length=8), nullable=False),
        sa.Column(
            "price_multiplier",
            sa.Numeric(24, 12),
            nullable=False,
            server_default="1",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint(
            "instrument_id",
            "provider",
            name="uq_instrument_market_data_provider",
        ),
    )
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("quote_currency", sa.String(length=8), nullable=False),
        sa.Column("rate", sa.Numeric(24, 12), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "base_currency",
            "quote_currency",
            "observed_at",
            "provider",
            name="uq_fx_pair_time_provider",
        ),
    )
    op.add_column(
        "positions",
        sa.Column("latest_price_observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "positions",
        sa.Column("latest_price_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "positions",
        sa.Column("latest_price_quality", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "prices",
        sa.Column("quote_currency", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "prices",
        sa.Column("provider_symbol", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "prices",
        sa.Column("provider_exchange", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "prices",
        sa.Column(
            "quality",
            sa.String(length=32),
            nullable=False,
            server_default="delayed",
        ),
    )
    op.add_column(
        "portfolio_snapshots",
        sa.Column("position_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "portfolio_snapshots",
        sa.Column(
            "valued_position_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "portfolio_snapshots",
        sa.Column(
            "reporting_coverage",
            sa.Numeric(12, 8),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("portfolio_snapshots", "reporting_coverage")
    op.drop_column("portfolio_snapshots", "valued_position_count")
    op.drop_column("portfolio_snapshots", "position_count")
    op.drop_column("prices", "quality")
    op.drop_column("prices", "provider_exchange")
    op.drop_column("prices", "provider_symbol")
    op.drop_column("prices", "quote_currency")
    op.drop_column("positions", "latest_price_quality")
    op.drop_column("positions", "latest_price_provider")
    op.drop_column("positions", "latest_price_observed_at")
    op.drop_table("fx_rates")
    op.drop_table("market_data_mappings")
