import os

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings

url = os.environ.get("MIGRATION_DATABASE_URL") or get_settings().migration_database_url


def run() -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run()
