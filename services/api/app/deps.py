from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, set_tenant
from app.errors import ApiError
from app.models import OrganizationMember
from app.security import decode_access_token


@dataclass
class Tenant:
    user_id: UUID
    org_id: UUID
    role: str
    session: AsyncSession


async def tenant_session(authorization: str | None = Header(default=None)) -> AsyncIterator[Tenant]:
    """Verify the token, re-check membership in the DB, then bind RLS context."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")
    try:
        claims = decode_access_token(authorization.split(" ", 1)[1])
        user_id, org_id = UUID(claims["sub"]), UUID(claims["org"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise ApiError(401, "UNAUTHENTICATED", "Your session has expired. Sign in again.")
    async with SessionLocal() as session, session.begin():
        await set_tenant(session, org_id, user_id)
        member = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
        if member is None:
            raise ApiError(403, "FORBIDDEN", "You are not a member of this organisation.")
        yield Tenant(user_id, org_id, member.role, session)


# scope="function": commit before the response is sent
CurrentTenant = Depends(tenant_session, scope="function")
