import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.agents.registry import AGENTS
from app.agents.runtime import execute_run
from app.ai.gateway import get_model
from app.ai.search import get_search
from app.audit import record
from app.config import get_settings
from app.db import SessionLocal, set_tenant
from app.deps import CurrentTenant, Tenant
from app.errors import ApiError
from app.models import Agent, AgentRun, AgentRunStep, BusinessProfile

router = APIRouter(tags=["agents"])
RUN_ROLES = {"owner", "admin", "approver", "member"}
_tasks: set[asyncio.Task] = set()


class Readiness(BaseModel):
    ai_provider: str | None
    web_search: str | None


class AgentOut(BaseModel):
    slug: str
    code: str
    name: str
    level: int
    department: str
    description: str
    risk: str
    version: str
    can_run: bool
    blocked_reason: str | None
    last_run: "RunOut | None" = None


class StepOut(BaseModel):
    seq: int
    name: str
    kind: str
    status: str
    summary: str | None
    started_at: datetime
    finished_at: datetime | None


class RunOut(BaseModel):
    id: UUID
    agent_slug: str
    status: str
    model: str | None
    input_tokens: int
    output_tokens: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: dict | None = None


class RunDetail(RunOut):
    output: dict[str, Any] | None
    steps: list[StepOut]


AgentOut.model_rebuild()


def readiness() -> Readiness:
    m, s = get_model(), get_search()
    return Readiness(ai_provider=m.name if m else None, web_search=s.name if s else None)


def _run_out(r: AgentRun) -> RunOut:
    err = {"message": r.error["message"]} if r.error else None
    return RunOut(id=r.id, agent_slug=r.agent_slug, status=r.status, model=r.model,
                  input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                  created_at=r.created_at, started_at=r.started_at, finished_at=r.finished_at,
                  error=err)


@router.get("/agents/readiness", response_model=Readiness)
async def get_readiness(t: Tenant = CurrentTenant) -> Readiness:
    return readiness()


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(t: Tenant = CurrentTenant) -> list[AgentOut]:
    ready = readiness()
    out = []
    for a in (await t.session.scalars(select(Agent).where(Agent.enabled).order_by(Agent.code))).all():
        last = await t.session.scalar(select(AgentRun).where(AgentRun.agent_slug == a.slug)
                                      .order_by(AgentRun.created_at.desc()).limit(1))
        blocked = None if a.slug in AGENTS else "Not released yet."
        if blocked is None and not ready.ai_provider:
            blocked = "Needs an AI provider connection."
        out.append(AgentOut(slug=a.slug, code=a.code, name=a.name, level=a.level,
                            department=a.department, description=a.description, risk=a.risk,
                            version=a.version, can_run=blocked is None, blocked_reason=blocked,
                            last_run=_run_out(last) if last else None))
    return out


@router.post("/agents/{slug}/runs", response_model=RunOut, status_code=202)
async def start_run(slug: str, t: Tenant = CurrentTenant) -> RunOut:
    if t.role not in RUN_ROLES:
        raise ApiError(403, "FORBIDDEN", "Your role cannot run agents.")
    agent = await t.session.get(Agent, slug)
    if agent is None or not agent.enabled or slug not in AGENTS:
        raise ApiError(404, "AGENT_NOT_FOUND", "That agent is not available.")
    if get_model() is None:
        raise ApiError(412, "AI_NOT_CONNECTED", "Connect an AI provider before running agents.")
    if await t.session.scalar(select(BusinessProfile.id)
                              .where(BusinessProfile.organization_id == t.org_id)) is None:
        raise ApiError(412, "PROFILE_REQUIRED", "Complete your business profile first.")
    busy = await t.session.scalar(select(AgentRun.id).where(
        AgentRun.agent_slug == slug, AgentRun.status.in_(("queued", "running"))))
    if busy:
        raise ApiError(409, "RUN_IN_PROGRESS", "This agent is already working. Wait for it to finish.")
    # Committed in its own transaction so the worker can see it immediately.
    async with SessionLocal() as s, s.begin():
        await set_tenant(s, t.org_id, t.user_id)
        run = AgentRun(organization_id=t.org_id, agent_slug=slug, agent_version=agent.version,
                       input={}, created_by=t.user_id)
        s.add(run)
        await s.flush()
        await s.refresh(run)
        record(s, t.org_id, t.user_id, "agent_run.requested", "agent_run", run.id, {"agent": slug})
    job = execute_run(run.id, t.org_id, t.user_id, AGENTS[slug])
    if get_settings().run_agents_inline:
        await job
        run = await t.session.scalar(select(AgentRun).where(AgentRun.id == run.id)
                                     .execution_options(populate_existing=True))
    else:  # in-process worker for now; moves to Celery with the queue release
        task = asyncio.create_task(job)
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    return _run_out(run)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(limit: int = Query(20, ge=1, le=100), t: Tenant = CurrentTenant) -> list[RunOut]:
    rows = (await t.session.scalars(select(AgentRun).order_by(AgentRun.created_at.desc())
                                    .limit(limit))).all()
    return [_run_out(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: UUID, t: Tenant = CurrentTenant) -> RunDetail:
    r = await t.session.scalar(select(AgentRun).where(AgentRun.id == run_id))
    if r is None:
        raise ApiError(404, "RUN_NOT_FOUND", "Run not found.")
    steps = (await t.session.scalars(select(AgentRunStep).where(AgentRunStep.run_id == run_id)
                                     .order_by(AgentRunStep.seq))).all()
    return RunDetail(**_run_out(r).model_dump(), output=r.output,
                     steps=[StepOut(seq=s.seq, name=s.name, kind=s.kind, status=s.status,
                                    summary=s.summary, started_at=s.started_at,
                                    finished_at=s.finished_at) for s in steps])
