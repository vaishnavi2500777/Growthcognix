from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    organization_name: str = Field(min_length=2, max_length=255)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrgOut(BaseModel):
    id: UUID
    name: str
    slug: str
    country_code: str
    timezone: str


class MeOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    organization: OrgOut
    onboarded: bool


class IndustryOut(BaseModel):
    id: UUID
    slug: str
    name: str
    subcategories: list["IndustryOut"] = []


class OfferingIn(BaseModel):
    kind: Literal["product", "service"]
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class OfferingOut(OfferingIn):
    id: UUID


class BusinessProfileIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    website: HttpUrl | None = None
    industry_id: UUID
    business_model: Literal["b2b", "b2c", "both"]
    description: str = Field(min_length=20, max_length=4000)
    target_customers: str = Field(min_length=5, max_length=2000)
    locations: list[str] = Field(default_factory=list, max_length=50)
    languages: list[str] = Field(default_factory=list, max_length=20)
    offerings: list[OfferingIn] = Field(min_length=1, max_length=100)

    @field_validator("locations", "languages")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]


class BusinessProfileOut(BaseModel):
    company_name: str
    website: str | None
    industry: IndustryOut
    parent_industry: IndustryOut
    business_model: str
    description: str
    target_customers: str
    locations: list[str]
    languages: list[str]
    offerings: list[OfferingOut]
