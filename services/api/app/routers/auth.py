import secrets
import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit import record
from app.db import SessionLocal, set_tenant
from app.errors import ApiError
from app.industry_taxonomy import slugify
from app.models import Organization, OrganizationMember, User
from app.schemas import LoginIn, RegisterIn, TokenOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Constant-time-ish defence against user enumeration on login.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn) -> TokenOut:
    email = body.email.lower()
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    async with SessionLocal() as session:
        try:
            async with session.begin():
                await set_tenant(session, org_id, user_id)
                session.add(User(id=user_id, email=email, full_name=body.full_name.strip(),
                                 password_hash=hash_password(body.password)))
                slug = f"{slugify(body.organization_name)[:100]}-{secrets.token_hex(3)}"
                session.add(Organization(id=org_id, name=body.organization_name.strip(), slug=slug))
                await session.flush()
                session.add(OrganizationMember(organization_id=org_id, user_id=user_id, role="owner"))
                record(session, org_id, user_id, "organization.created", "organization", org_id)
        except IntegrityError:
            raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.")
    return TokenOut(access_token=create_access_token(user_id, org_id))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn) -> TokenOut:
    async with SessionLocal() as session, session.begin():
        user = await session.scalar(select(User).where(User.email == body.email.lower()))
        if user is None:
            verify_password(_DUMMY_HASH, body.password)
            raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
        if not verify_password(user.password_hash, body.password):
            raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
        await set_tenant(session, None, user.id)
        member = await session.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
            .order_by(OrganizationMember.created_at).limit(1)
        )
        if member is None:
            raise ApiError(403, "NO_ORGANIZATION", "This account has no organisation.")
        await set_tenant(session, member.organization_id, user.id)
        record(session, member.organization_id, user.id, "user.signed_in")
        return TokenOut(access_token=create_access_token(user.id, member.organization_id))
