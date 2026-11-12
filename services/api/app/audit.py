from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def record(session: AsyncSession, org_id: UUID, actor_id: UUID | None, action: str,
           resource_type: str | None = None, resource_id: UUID | None = None,
           details: dict | None = None, actor_type: str = "user") -> None:
    session.add(AuditLog(organization_id=org_id, actor_type=actor_type, actor_id=actor_id,
                         action=action, resource_type=resource_type, resource_id=resource_id,
                         details=details or {}))
