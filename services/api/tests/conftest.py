"""Tests run against a real PostgreSQL + pgvector database (no mocks for the data layer).

Env:
  TEST_ADMIN_URL      superuser/owner URL used to (re)create the test database
  TEST_DB_NAME        defaults to growthcognix_test
The runtime role gc_app (NOSUPERUSER NOBYPASSRLS) must exist; see infrastructure/db/init.sql.
"""
import os
import subprocess
import sys

import psycopg
import pytest

ADMIN = os.environ.get("TEST_ADMIN_URL", "postgresql://app:app@localhost:5432/postgres")
DB = os.environ.get("TEST_DB_NAME", "growthcognix_test")
HOST = ADMIN.split("@", 1)[1].rsplit("/", 1)[0]
OWNER = ADMIN.split("//", 1)[1].split("@", 1)[0]

os.environ["DATABASE_URL"] = f"postgresql+asyncpg://gc_app:gc_app@{HOST}/{DB}"
os.environ["MIGRATION_DATABASE_URL"] = f"postgresql+psycopg://{OWNER}@{HOST}/{DB}"
os.environ["JWT_SECRET"] = "test-secret-0123456789abcdef0123456789"


def pytest_sessionstart(session):
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{DB}"')
    here = os.path.dirname(os.path.dirname(__file__))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=here, check=True)


@pytest.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def app_db():
    """Raw connection as the runtime role, for RLS assertions."""
    with psycopg.connect(f"postgresql://gc_app:gc_app@{HOST}/{DB}") as c:
        yield c
