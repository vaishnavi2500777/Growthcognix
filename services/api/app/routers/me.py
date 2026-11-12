from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentTenant, Tenant
from app.models import BusinessProfile, Organization, User
from app.schemas import MeOut, OrgOut

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeOut)
async def me(t: Tenant = CurrentTenant) -> MeOut:
    user = await t.session.get(User, t.user_id)
    org = await t.session.get(Organization, t.org_id)
    onboarded = await t.session.scalar(
        select(BusinessProfile.id).where(BusinessProfile.organization_id == t.org_id)
    )
    return MeOut(id=user.id, email=user.email, full_name=user.full_name, role=t.role,
                 organization=OrgOut.model_validate(org, from_attributes=True),
                 onboarded=onboarded is not None)
