from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_historical_market_data"
down_revision: str | None = "0008_operational_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "historical_series",
        sa.Column("series_key", sa.String(length=512), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.String(length=128),
            sa.ForeignKey("instruments.instrument_id"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("display_symbol", sa.String(length=64), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("exchange", sa.String(length=128), nullable=True),
        sa.Column("provider_identity_json", sa.JSON(), nullable=False),
        sa.Column("active_dataset_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "historical_datasets",
        sa.Column("dataset_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "series_key",
            sa.String(length=512),
            sa.ForeignKey("historical_series.series_key"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_symbol", sa.String(length=128), nullable=False),
        sa.Column("provider_exchange", sa.String(length=128), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adjustment_mode", sa.String(length=32), nullable=False),
        sa.Column("unadjusted_mode", sa.String(length=32), nullable=True),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_historical_datasets_series_key",
        "historical_datasets",
        ["series_key"],
    )
    op.create_table(
        "historical_daily_bars",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "dataset_id",
            sa.String(length=64),
            sa.ForeignKey("historical_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("adjustment_mode", sa.String(length=32), nullable=False),
        sa.Column("open", sa.Numeric(24, 10), nullable=False),
        sa.Column("high", sa.Numeric(24, 10), nullable=False),
        sa.Column("low", sa.Numeric(24, 10), nullable=False),
        sa.Column("close", sa.Numeric(24, 10), nullable=False),
        sa.Column("volume", sa.Numeric(30, 8), nullable=True),
        sa.Column("dividend", sa.Numeric(24, 10), nullable=False),
        sa.Column("split_ratio", sa.Numeric(24, 10), nullable=False),
        sa.UniqueConstraint(
            "dataset_id",
            "trading_date",
            "adjustment_mode",
            name="uq_historical_bar_dataset_date_mode",
        ),
    )
    op.create_index(
        "ix_historical_daily_bars_dataset_id",
        "historical_daily_bars",
        ["dataset_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_historical_daily_bars_dataset_id",
        table_name="historical_daily_bars",
    )
    op.drop_table("historical_daily_bars")
    op.drop_index(
        "ix_historical_datasets_series_key",
        table_name="historical_datasets",
    )
    op.drop_table("historical_datasets")
    op.drop_table("historical_series")
