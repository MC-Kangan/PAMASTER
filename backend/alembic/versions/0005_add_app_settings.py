from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_app_settings"
down_revision: str | None = "0004_manual_cost_basis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=1024), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
