"""add entitlement related fields

Revision ID: a1b2c3d4e5f6
Revises: 0a3e2ecfa319
Create Date: 2025-11-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "0a3e2ecfa319"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default="user",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "has_tier1",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_unique_constraint(
        "uq_users_stripe_customer_id", "users", ["stripe_customer_id"]
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "is_recurring",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Drop server defaults now that rows are populated
    op.alter_column("users", "role", server_default=None)
    op.alter_column("users", "has_tier1", server_default=None)
    op.alter_column("subscriptions", "updated_at", server_default=None)
    op.alter_column("subscriptions", "is_recurring", server_default=None)


def downgrade():
    op.alter_column("subscriptions", "is_recurring", server_default=sa.text("false"))
    op.alter_column("subscriptions", "updated_at", server_default=sa.text("now()"))
    op.alter_column("users", "has_tier1", server_default=sa.text("false"))
    op.alter_column("users", "role", server_default="user")
    op.drop_column("subscriptions", "is_recurring")
    op.drop_column("subscriptions", "updated_at")
    op.drop_constraint("uq_users_stripe_customer_id", "users", type_="unique")
    op.drop_column("users", "has_tier1")
    op.drop_column("users", "role")
    op.drop_column("users", "stripe_customer_id")

