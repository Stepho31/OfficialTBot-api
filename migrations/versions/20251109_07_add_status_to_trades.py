"""add status field to trades table

Revision ID: 20251109_07_status_trades
Revises: 20251109_06_user_settings
Create Date: 2025-11-09 02:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251109_07_status_trades"
down_revision = "20251109_06_user_settings"
branch_labels = None
depends_on = None


def upgrade():
    # Add status column to trades table
    op.add_column("trades", sa.Column("status", sa.String(32), nullable=True))
    
    # Populate status based on closed_at: OPEN if closed_at is NULL, CLOSED otherwise
    op.execute("""
        UPDATE trades
        SET status = CASE
            WHEN closed_at IS NULL THEN 'OPEN'
            ELSE 'CLOSED'
        END
    """)


def downgrade():
    op.drop_column("trades", "status")

