from fastapi import APIRouter
from sqlalchemy import delete, select

from app.audit import record
from app.deps import CurrentTenant, Tenant
from app.errors import ApiError
from app.models import BusinessOffering, BusinessProfile, Industry
from app.schemas import BusinessProfileIn, BusinessProfileOut, IndustryOut, OfferingOut

router = APIRouter(prefix="/business-profile", tags=["business"])
EDIT_ROLES = {"owner", "admin"}


async def _out(t: Tenant, p: BusinessProfile) -> BusinessProfileOut:
    ind = await t.session.get(Industry, p.industry_id)
    parent = await t.session.get(Industry, ind.parent_id)
    offs = (await t.session.scalars(
        select(BusinessOffering).where(BusinessOffering.organization_id == t.org_id)
        .order_by(BusinessOffering.created_at)
    )).all()
    return BusinessProfileOut(
        company_name=p.company_name, website=p.website,
        industry=IndustryOut(id=ind.id, slug=ind.slug, name=ind.name),
        parent_industry=IndustryOut(id=parent.id, slug=parent.slug, name=parent.name),
        business_model=p.business_model, description=p.description,
        target_customers=p.target_customers, locations=p.locations, languages=p.languages,
        offerings=[OfferingOut(id=o.id, kind=o.kind, name=o.name, description=o.description)
                   for o in offs],
    )


@router.get("", response_model=BusinessProfileOut)
async def get_profile(t: Tenant = CurrentTenant) -> BusinessProfileOut:
    p = await t.session.scalar(select(BusinessProfile).where(BusinessProfile.organization_id == t.org_id))
    if p is None:
        raise ApiError(404, "NOT_ONBOARDED", "Business profile has not been created yet.")
    return await _out(t, p)


@router.put("", response_model=BusinessProfileOut)
async def put_profile(body: BusinessProfileIn, t: Tenant = CurrentTenant) -> BusinessProfileOut:
    if t.role not in EDIT_ROLES:
        raise ApiError(403, "FORBIDDEN", "Only owners and admins can edit the business profile.")
    ind = await t.session.get(Industry, body.industry_id)
    if ind is None or ind.parent_id is None:
        raise ApiError(422, "INVALID_INDUSTRY", "Choose an industry subcategory.")
    p = await t.session.scalar(select(BusinessProfile).where(BusinessProfile.organization_id == t.org_id))
    fields = body.model_dump(exclude={"offerings", "website"})
    website = str(body.website) if body.website else None
    if p is None:
        p = BusinessProfile(organization_id=t.org_id, website=website, **fields)
        t.session.add(p)
        action = "business_profile.created"
    else:
        for k, v in fields.items():
            setattr(p, k, v)
        p.website = website
        action = "business_profile.updated"
    await t.session.execute(delete(BusinessOffering).where(BusinessOffering.organization_id == t.org_id))
    for o in body.offerings:
        t.session.add(BusinessOffering(organization_id=t.org_id, **o.model_dump()))
    await t.session.flush()
    record(t.session, t.org_id, t.user_id, action, "business_profile", p.id)
    return await _out(t, p)
