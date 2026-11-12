from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agents.approvals import verify_unchanged
from app.audit import record
from app.deps import CurrentTenant, Tenant
from app.errors import ApiError
from app.models import Approval

router = APIRouter(prefix="/approvals", tags=["approvals"])
DECIDE_ROLES = {"owner", "admin", "approver"}


class ApprovalOut(BaseModel):
    id: UUID
    action_type: str
    title: str
    payload: dict
    risk: str
    status: str
    requested_by_agent: str | None
    run_id: UUID | None
    decided_by: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)


def _out(a: Approval) -> ApprovalOut:
    return ApprovalOut(**{k: getattr(a, k) for k in ApprovalOut.model_fields})


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(status: str | None = Query(None), t: Tenant = CurrentTenant):
    q = select(Approval).order_by(Approval.created_at.desc()).limit(100)
    if status:
        q = q.where(Approval.status == status)
    return [_out(a) for a in (await t.session.scalars(q)).all()]


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
async def decide(approval_id: UUID, body: DecisionIn, t: Tenant = CurrentTenant):
    if t.role not in DECIDE_ROLES:
        raise ApiError(403, "FORBIDDEN", "Only owners, admins and approvers can decide.")
    a = await t.session.scalar(select(Approval).where(Approval.id == approval_id).with_for_update())
    if a is None:
        raise ApiError(404, "APPROVAL_NOT_FOUND", "Approval not found.")
    if a.status != "pending":
        raise ApiError(409, "ALREADY_DECIDED", f"This request was already {a.status}.")
    if not verify_unchanged(a):
        raise ApiError(409, "PAYLOAD_CHANGED", "This request changed after it was created.")
    a.status, a.decided_by, a.decision_note = body.decision, t.user_id, body.note
    a.decided_at = func.now()
    record(t.session, t.org_id, t.user_id, f"approval.{body.decision}", "approval", a.id,
           {"action_type": a.action_type, "payload_hash": a.payload_hash})
    await t.session.flush()
    await t.session.refresh(a)
    return _out(a)
