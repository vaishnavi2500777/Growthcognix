from fastapi import APIRouter
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Industry
from app.schemas import IndustryOut

router = APIRouter(tags=["industries"])


@router.get("/industries", response_model=list[IndustryOut])
async def list_industries() -> list[IndustryOut]:
    async with SessionLocal() as session:
        rows = (await session.scalars(select(Industry).order_by(Industry.sort_order))).all()
    groups = {r.id: IndustryOut(id=r.id, slug=r.slug, name=r.name) for r in rows if not r.parent_id}
    for r in rows:
        if r.parent_id:
            groups[r.parent_id].subcategories.append(IndustryOut(id=r.id, slug=r.slug, name=r.name))
    return list(groups.values())
