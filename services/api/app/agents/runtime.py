"""Agent runtime: every run and every step is persisted before and after it executes,
inside the tenant's RLS context, so the history users see is the real execution record."""
import traceback
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update

from app.audit import record
from app.db import SessionLocal, set_tenant
from app.models import AgentRun, AgentRunStep


class StepSkipped(Exception):
    """Raise inside a step to record it as skipped, with the reason shown to the user."""


class RunContext:
    def __init__(self, run_id: UUID, org_id: UUID, user_id: UUID | None):
        self.run_id, self.org_id, self.user_id = run_id, org_id, user_id
        self.seq = 0
        self.tokens = [0, 0]
        self.model: str | None = None

    async def step(self, name: str, kind: str, fn: Callable[[], Awaitable[tuple[Any, str, dict]]]):
        """Run fn() as a recorded step. fn returns (value, summary, detail)."""
        self.seq += 1
        async with SessionLocal() as s, s.begin():
            await set_tenant(s, self.org_id, self.user_id)
            st = AgentRunStep(organization_id=self.org_id, run_id=self.run_id, seq=self.seq,
                              name=name, kind=kind, status="running")
            s.add(st)
        status, value, summary, detail, tok = "succeeded", None, None, {}, (0, 0)
        try:
            value, summary, detail = await fn()
            tok = detail.pop("_tokens", (0, 0))
        except StepSkipped as e:
            status, summary = "skipped", str(e)
        except Exception as e:
            status, summary, detail = "failed", str(e)[:500], {"error": type(e).__name__}
            await self._close_step(st.id, status, summary, detail, tok)
            raise
        await self._close_step(st.id, status, summary, detail, tok)
        self.tokens[0] += tok[0]
        self.tokens[1] += tok[1]
        return value

    async def _close_step(self, step_id, status, summary, detail, tok):
        async with SessionLocal() as s, s.begin():
            await set_tenant(s, self.org_id, self.user_id)
            await s.execute(update(AgentRunStep).where(AgentRunStep.id == step_id).values(
                status=status, summary=summary, detail=detail, finished_at=func.now(),
                input_tokens=tok[0], output_tokens=tok[1]))


AgentFn = Callable[[RunContext, dict], Awaitable[dict]]


async def execute_run(run_id: UUID, org_id: UUID, user_id: UUID | None, agent: AgentFn) -> None:
    ctx = RunContext(run_id, org_id, user_id)
    async with SessionLocal() as s, s.begin():
        await set_tenant(s, org_id, user_id)
        run = await s.scalar(select(AgentRun).where(AgentRun.id == run_id))
        run.status, run.started_at = "running", func.now()
        inp = dict(run.input)
    status, output, error = "succeeded", None, None
    try:
        output = await agent(ctx, inp)
    except Exception as e:  # noqa: BLE001 - recorded on the run, never swallowed
        status = "failed"
        error = {"type": type(e).__name__, "message": str(e)[:500],
                 "trace": traceback.format_exc(limit=3)[-1500:]}
    async with SessionLocal() as s, s.begin():
        await set_tenant(s, org_id, user_id)
        await s.execute(update(AgentRun).where(AgentRun.id == run_id).values(
            status=status, output=output, error=error, finished_at=func.now(), model=ctx.model,
            input_tokens=ctx.tokens[0], output_tokens=ctx.tokens[1]))
        record(s, org_id, None, f"agent_run.{status}", "agent_run", run_id,
               {"tokens": ctx.tokens}, actor_type="agent")
