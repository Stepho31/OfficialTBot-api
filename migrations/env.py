from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context
import os
import sys

# Ensure Alembic treats THIS folder as the project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import Base
from app.settings import settings

# --- Alembic Config ---
config = context.config

# Load logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Database URL (sync version for Alembic) ---
sync_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")

# Create sync engine for migrations
sync_engine = create_engine(sync_db_url, poolclass=pool.NullPool)

# Metadata used for autogenerate
target_metadata = Base.metadata


# --- Offline Mode ---
def run_migrations_offline():
    """Run migrations without DB connection."""
    context.configure(
        url=sync_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# --- Online Mode ---
def run_migrations_online():
    """Run migrations with DB connection."""
    with sync_engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# --- Execution Entry Point ---
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
