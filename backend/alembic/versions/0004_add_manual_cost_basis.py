from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_manual_cost_basis"
down_revision: str | None = "334aec2ec9cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "positions",
        sa.Column(
            "broker_average_cost",
            sa.Numeric(24, 8),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "positions",
        sa.Column("manual_average_cost", sa.Numeric(24, 8), nullable=True),
    )
    op.add_column(
        "positions",
        sa.Column(
            "broker_cost_basis_status",
            sa.String(length=32),
            nullable=False,
            server_default="unavailable",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE positions "
            "SET broker_average_cost = average_cost, "
            "broker_cost_basis_status = cost_basis_status"
        )
    )


def downgrade() -> None:
    op.drop_column("positions", "broker_cost_basis_status")
    op.drop_column("positions", "manual_average_cost")
    op.drop_column("positions", "broker_average_cost")
