"""add user_settings table with trade_allocation

Revision ID: 20251109_06_user_settings
Revises: 20251109_05_password_reset
Create Date: 2025-11-09 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251109_06_user_settings"
down_revision = "20251109_05_password_reset"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "trade_allocation",
            sa.Float(),
            nullable=False,
            server_default=sa.text("10.0"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_settings_user"),
    )
    
    # Create settings for existing users with default trade_allocation
    op.execute("""
        INSERT INTO user_settings (user_id, trade_allocation, created_at, updated_at)
        SELECT id, 10.0, NOW(), NOW()
        FROM users
        WHERE id NOT IN (SELECT user_id FROM user_settings)
    """)


def downgrade():
    op.drop_table("user_settings")

