"""add password reset token fields to users

Revision ID: 20251109_05_password_reset
Revises: 20251109_04_password_hash
Create Date: 2025-11-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251109_05_password_reset"
down_revision = "20251109_04_password_hash"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("password_reset_token", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_reset_expires", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("users", "password_reset_expires")
    op.drop_column("users", "password_reset_token")

