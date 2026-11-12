"""Approval contract. Agents may only *request*; decisions come from authenticated people,
and the payload executed must be byte-for-byte the payload approved (hash check)."""
import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Approval


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def request_approval(s: AsyncSession, org_id: UUID, *, agent_slug: str, run_id: UUID | None,
                           action_type: str, title: str, payload: dict,
                           idempotency_key: str) -> Approval:
    existing = await s.scalar(select(Approval).where(Approval.organization_id == org_id,
                                                     Approval.idempotency_key == idempotency_key))
    if existing:
        return existing
    a = Approval(organization_id=org_id, run_id=run_id, action_type=action_type, title=title,
                 payload=payload, payload_hash=payload_hash(payload),
                 idempotency_key=idempotency_key, requested_by_agent=agent_slug)
    s.add(a)
    await s.flush()
    return a


def verify_unchanged(a: Approval) -> bool:
    return payload_hash(a.payload) == a.payload_hash
