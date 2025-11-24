"""Revision ID: 78adc69094db
Revises: 
Create Date: 2025-10-24 12:17:29.129343
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "78adc69094db"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # trades.external_id + constraints/indexes
    op.add_column("trades", sa.Column("external_id", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_trades_account_external", "trades", ["account_id", "external_id"])
    op.create_index("ix_trades_account_closed", "trades", ["account_id", "closed_at"])

    # equity_snapshots unique/index
    op.create_unique_constraint(
        "uq_equitysnapshots_account_taken", "equity_snapshots", ["account_id", "taken_at"]
    )
    op.create_index("ix_equitysnapshots_account_taken", "equity_snapshots", ["account_id", "taken_at"])

    # signals table
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("signal_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=True),
        sa.Column("entry", sa.Numeric(18, 6), nullable=True),
        sa.Column("sl", sa.Numeric(18, 6), nullable=True),
        sa.Column("tp", sa.Numeric(18, 6), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
    )

    # accounts unique per (user_id, account_id)
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_accounts_user_broker_account", ["user_id", "account_id"]
        )

def downgrade():
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_constraint("uq_accounts_user_broker_account", type_="unique")

    op.drop_table("signals")
    op.drop_index("ix_equitysnapshots_account_taken", table_name="equity_snapshots")
    op.drop_constraint("uq_equitysnapshots_account_taken", "equity_snapshots", type_="unique")
    op.drop_index("ix_trades_account_closed", table_name="trades")
    op.drop_constraint("uq_trades_account_external", "trades", type_="unique")
    op.drop_column("trades", "external_id")
