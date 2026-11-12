from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def set_tenant(session: AsyncSession, org_id: UUID | None, user_id: UUID | None) -> None:
    """Bind the verified tenant to the current transaction. RLS policies read these."""
    await session.execute(
        text("SELECT set_config('app.org_id', :o, true), set_config('app.user_id', :u, true)"),
        {"o": str(org_id) if org_id else "", "u": str(user_id) if user_id else ""},
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
