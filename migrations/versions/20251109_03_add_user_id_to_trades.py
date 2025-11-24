"""add user reference to trades

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2025-11-09 01:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("trades", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_trades_user",
        "trades",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # populate existing rows via account linkage
    op.execute(
        """
        UPDATE trades t
        SET user_id = a.user_id
        FROM accounts a
        WHERE t.account_id = a.id
        """
    )
    op.alter_column("trades", "user_id", nullable=False)
    op.create_unique_constraint(
        "uq_trades_user_external",
        "trades",
        ["user_id", "external_id"],
    )
    op.create_index(
        "ix_trades_user_opened",
        "trades",
        ["user_id", "opened_at"],
    )


def downgrade():
    op.drop_index("ix_trades_user_opened", table_name="trades")
    op.drop_constraint("uq_trades_user_external", "trades", type_="unique")
    op.drop_constraint("fk_trades_user", "trades", type_="foreignkey")
    op.drop_column("trades", "user_id")

