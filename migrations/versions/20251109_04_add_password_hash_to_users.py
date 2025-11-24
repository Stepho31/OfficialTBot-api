"""add password hash to users

Revision ID: 20251109_04_password_hash
Revises: c3d4e5f6a7b8
Create Date: 2025-11-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251109_04_password_hash"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_column("users", "password_hash")

