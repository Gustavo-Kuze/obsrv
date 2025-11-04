"""
Alembic migration environment configuration.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.src.core.config import settings
from backend.src.core.database import Base

# Import all models to ensure they're registered with Base.metadata
# Import classes directly to ensure they're registered with SQLAlchemy
from backend.src.models.api_key import APIKey  # noqa: F401
from backend.src.models.client import Client  # noqa: F401
from backend.src.models.crawl_log import CrawlExecutionLog  # noqa: F401
from backend.src.models.product import Product  # noqa: F401
from backend.src.models.product_history import ProductHistoryRecord  # noqa: F401
from backend.src.models.webhook_log import WebhookDeliveryLog  # noqa: F401
from backend.src.models.website import MonitoredWebsite  # noqa: F401

# Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata

# Override sqlalchemy.url from environment variable
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)





def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=None,
        compare_type=False,
        compare_server_default=False,
    )

    with context.begin_transaction():
        context.run_migrations()





def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Use sync engine to avoid asyncpg sslmode issues
    from backend.src.core.database import sync_engine

    with sync_engine.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
