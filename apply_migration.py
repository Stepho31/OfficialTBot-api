#!/usr/bin/env python3
"""Script to apply Alembic migrations programmatically."""
import os
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from alembic import command
    from alembic.config import Config
    from app.settings import settings
    
    # Set up Alembic configuration
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    
    # Use DATABASE_URL from settings or environment
    db_url = settings.DATABASE_URL if hasattr(settings, 'DATABASE_URL') and settings.DATABASE_URL else os.environ.get("DATABASE_URL")
    if db_url:
        alembic_cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    
    print("Applying Alembic migrations...")
    print(f"Database URL: {db_url[:20]}..." if db_url and len(db_url) > 20 else f"Database URL: {db_url}")
    
    # Run upgrade to head
    command.upgrade(alembic_cfg, "head")
    print("✅ Migrations applied successfully!")
    
except ImportError as e:
    print(f"❌ Error: {e}")
    print("Please install alembic: pip install alembic")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error applying migrations: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

