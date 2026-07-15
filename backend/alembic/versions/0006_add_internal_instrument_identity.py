from collections.abc import Sequence
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from alembic import op

revision: str = "0006_instrument_identity"
down_revision: str | None = "0005_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _instrument_id(symbol: str, asset_class: str, currency: str) -> str:
    identity = "|".join(
        (
            "pa-investing-instrument",
            "",
            symbol.upper(),
            asset_class,
            currency.upper(),
            "",
        )
    )
    return str(uuid5(NAMESPACE_URL, identity))


def _timestamp(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def upgrade() -> None:
    connection = op.get_bind()
    instruments = [
        dict(row._mapping)
        for row in connection.execute(
            sa.text(
                "SELECT symbol, name, asset_class, currency FROM instruments"
            )
        )
    ]
    positions = [
        dict(row._mapping)
        for row in connection.execute(
            sa.text(
                "SELECT id, account_id, symbol, quantity, average_cost, "
                "broker_average_cost, manual_average_cost, latest_price, "
                "cost_basis_status, broker_cost_basis_status FROM positions"
            )
        )
    ]
    prices = [
        dict(row._mapping)
        for row in connection.execute(
            sa.text(
                "SELECT id, symbol, price, observed_at, provider FROM prices"
            )
        )
    ]

    op.drop_table("prices")
    op.drop_table("positions")
    op.drop_table("instruments")
    _create_identity_tables()

    ids_by_symbol = {
        row["symbol"]: _instrument_id(
            row["symbol"],
            row["asset_class"],
            row["currency"],
        )
        for row in instruments
    }
    instrument_table = sa.table(
        "instruments",
        sa.column("instrument_id", sa.String),
        sa.column("symbol", sa.String),
        sa.column("name", sa.String),
        sa.column("asset_class", sa.String),
        sa.column("currency", sa.String),
        sa.column("venue", sa.String),
    )
    if instruments:
        op.bulk_insert(
            instrument_table,
            [
                {
                    "instrument_id": ids_by_symbol[row["symbol"]],
                    "symbol": row["symbol"].upper(),
                    "name": row["name"],
                    "asset_class": row["asset_class"],
                    "currency": row["currency"].upper(),
                    "venue": "",
                }
                for row in instruments
            ],
        )

    position_table = sa.table(
        "positions",
        sa.column("id", sa.Integer),
        sa.column("account_id", sa.String),
        sa.column("instrument_id", sa.String),
        sa.column("quantity", sa.Numeric),
        sa.column("average_cost", sa.Numeric),
        sa.column("broker_average_cost", sa.Numeric),
        sa.column("manual_average_cost", sa.Numeric),
        sa.column("latest_price", sa.Numeric),
        sa.column("cost_basis_status", sa.String),
        sa.column("broker_cost_basis_status", sa.String),
    )
    if positions:
        op.bulk_insert(
            position_table,
            [
                {
                    **{key: value for key, value in row.items() if key != "symbol"},
                    "instrument_id": ids_by_symbol[row["symbol"]],
                }
                for row in positions
            ],
        )

    price_table = sa.table(
        "prices",
        sa.column("id", sa.Integer),
        sa.column("instrument_id", sa.String),
        sa.column("price", sa.Numeric),
        sa.column("observed_at", sa.DateTime(timezone=True)),
        sa.column("provider", sa.String),
    )
    if prices:
        op.bulk_insert(
            price_table,
            [
                {
                    **{key: value for key, value in row.items() if key != "symbol"},
                    "instrument_id": ids_by_symbol[row["symbol"]],
                    "observed_at": _timestamp(row["observed_at"]),
                }
                for row in prices
            ],
        )


def downgrade() -> None:
    connection = op.get_bind()
    instruments = [
        dict(row._mapping)
        for row in connection.execute(
            sa.text(
                "SELECT instrument_id, symbol, name, asset_class, currency "
                "FROM instruments"
            )
        )
    ]
    symbols = [row["symbol"] for row in instruments]
    if len(symbols) != len(set(symbols)):
        raise RuntimeError(
            "cannot downgrade instrument identity while duplicate symbols exist"
        )
    positions = [
        dict(row._mapping)
        for row in connection.execute(sa.text("SELECT * FROM positions"))
    ]
    prices = [
        dict(row._mapping)
        for row in connection.execute(sa.text("SELECT * FROM prices"))
    ]
    symbols_by_id = {
        row["instrument_id"]: row["symbol"] for row in instruments
    }

    op.drop_table("instrument_identifiers")
    op.drop_table("prices")
    op.drop_table("positions")
    op.drop_index("ix_instruments_symbol", table_name="instruments")
    op.drop_table("instruments")
    _create_legacy_tables()

    legacy_instrument_table = sa.table(
        "instruments",
        sa.column("symbol", sa.String),
        sa.column("name", sa.String),
        sa.column("asset_class", sa.String),
        sa.column("currency", sa.String),
    )
    if instruments:
        op.bulk_insert(
            legacy_instrument_table,
            [
                {
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "asset_class": row["asset_class"],
                    "currency": row["currency"],
                }
                for row in instruments
            ],
        )

    legacy_position_table = sa.table(
        "positions",
        sa.column("id", sa.Integer),
        sa.column("account_id", sa.String),
        sa.column("symbol", sa.String),
        sa.column("quantity", sa.Numeric),
        sa.column("average_cost", sa.Numeric),
        sa.column("broker_average_cost", sa.Numeric),
        sa.column("manual_average_cost", sa.Numeric),
        sa.column("latest_price", sa.Numeric),
        sa.column("cost_basis_status", sa.String),
        sa.column("broker_cost_basis_status", sa.String),
    )
    if positions:
        op.bulk_insert(
            legacy_position_table,
            [
                {
                    **{
                        key: value
                        for key, value in row.items()
                        if key != "instrument_id"
                    },
                    "symbol": symbols_by_id[row["instrument_id"]],
                }
                for row in positions
            ],
        )

    legacy_price_table = sa.table(
        "prices",
        sa.column("id", sa.Integer),
        sa.column("symbol", sa.String),
        sa.column("price", sa.Numeric),
        sa.column("observed_at", sa.DateTime(timezone=True)),
        sa.column("provider", sa.String),
    )
    if prices:
        op.bulk_insert(
            legacy_price_table,
            [
                {
                    **{
                        key: value
                        for key, value in row.items()
                        if key != "instrument_id"
                    },
                    "symbol": symbols_by_id[row["instrument_id"]],
                    "observed_at": _timestamp(row["observed_at"]),
                }
                for row in prices
            ],
        )


def _create_identity_tables() -> None:
    op.create_table(
        "instruments",
        sa.Column("instrument_id", sa.String(length=128), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("venue", sa.String(length=64), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "symbol",
            "asset_class",
            "currency",
            "venue",
            name="uq_instrument_listing",
        ),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"])
    op.create_table(
        "instrument_identifiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_id",
            sa.String(length=128),
            sa.ForeignKey("instruments.instrument_id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("identifier_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.UniqueConstraint(
            "provider",
            "identifier_type",
            "value",
            name="uq_provider_instrument_identifier",
        ),
        sa.UniqueConstraint(
            "instrument_id",
            "provider",
            "identifier_type",
            name="uq_instrument_identifier_type",
        ),
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
            "instrument_id",
            sa.String(length=128),
            sa.ForeignKey("instruments.instrument_id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("average_cost", sa.Numeric(24, 8), nullable=False),
        sa.Column("broker_average_cost", sa.Numeric(24, 8), nullable=False),
        sa.Column("manual_average_cost", sa.Numeric(24, 8), nullable=True),
        sa.Column("latest_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("cost_basis_status", sa.String(length=32), nullable=False),
        sa.Column("broker_cost_basis_status", sa.String(length=32), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "instrument_id",
            name="uq_position_account_instrument",
        ),
    )
    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_id",
            sa.String(length=128),
            sa.ForeignKey("instruments.instrument_id"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "instrument_id",
            "observed_at",
            "provider",
            name="uq_price_instrument_time_provider",
        ),
    )


def _create_legacy_tables() -> None:
    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
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
        sa.Column("broker_average_cost", sa.Numeric(24, 8), nullable=False),
        sa.Column("manual_average_cost", sa.Numeric(24, 8), nullable=True),
        sa.Column("latest_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("cost_basis_status", sa.String(length=32), nullable=False),
        sa.Column("broker_cost_basis_status", sa.String(length=32), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "symbol",
            name="uq_position_account_symbol",
        ),
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
