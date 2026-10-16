"""
app/schemas/auth_schemas.py

Pydantic request/response schemas for all authentication endpoints.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from app.models.user import UserRole


class UserLoginRequest(BaseModel):
    email: str
    password: str


class UserSummaryResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    organization_id: uuid.UUID | None = None
    org_name: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSummaryResponse


class OrgRegisterRequest(BaseModel):
    org_name: str
    admin_name: str
    admin_email: str
    password: str


class AnalystRegisterRequest(BaseModel):
    org_id: uuid.UUID
    full_name: str
    email: str
    password: str
