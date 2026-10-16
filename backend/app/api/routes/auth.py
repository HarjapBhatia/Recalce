"""
app/api/routes/auth.py

Authentication endpoints:
  POST /api/v1/auth/login              Authenticate and receive a JWT.
  POST /api/v1/auth/register-org       Create a new organization with its first admin.
  POST /api/v1/auth/register-analyst   Add an analyst to an existing organization.
  GET  /api/v1/auth/me                 Return the authenticated user's profile.
  POST /api/v1/auth/seed-demo-users    Provision the standard demo fixture accounts.
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.auth_schemas import (
    AnalystRegisterRequest,
    OrgRegisterRequest,
    TokenResponse,
    UserLoginRequest,
    UserSummaryResponse,
)
from app.services.auth_service import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    """Convert an organization name to a lowercase URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _build_user_summary(user: User, db: Session) -> UserSummaryResponse:
    """Build the UserSummaryResponse, including the organization name if present."""
    org_name: str | None = None
    if user.organization_id:
        org = db.execute(select(Organization).where(Organization.id == user.organization_id)).scalar_one_or_none()
        org_name = org.name if org else None
    return UserSummaryResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=user.organization_id,
        org_name=org_name,
        is_active=user.is_active,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: UserLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate a user by email and password; return a signed JWT."""
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "org_id": str(user.organization_id) if user.organization_id else None,
    }
    access_token = create_access_token(token_data)
    return TokenResponse(access_token=access_token, user=_build_user_summary(user, db))


@router.post("/register-org", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_org(body: OrgRegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a new organization and its first administrator account."""
    # Check email uniqueness
    existing = db.execute(select(User).where(User.email == body.admin_email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    slug = _slugify(body.org_name)
    # Ensure slug uniqueness
    existing_org = db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()
    if existing_org:
        raise HTTPException(status_code=400, detail="An organization with this name already exists.")

    org = Organization(name=body.org_name, slug=slug)
    admin = User(
        email=body.admin_email,
        full_name=body.admin_name,
        hashed_password=hash_password(body.password),
        role=UserRole.ADMIN,
        organization=org,
    )
    db.add(org)
    db.add(admin)
    db.commit()
    db.refresh(admin)

    token_data = {
        "sub": str(admin.id),
        "email": admin.email,
        "role": admin.role.value,
        "org_id": str(admin.organization_id),
    }
    return TokenResponse(access_token=create_access_token(token_data), user=_build_user_summary(admin, db))


@router.post("/register-analyst", response_model=UserSummaryResponse, status_code=status.HTTP_201_CREATED)
def register_analyst(
    body: AnalystRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserSummaryResponse:
    """
    Add an analyst to an organization.
    Only an ADMIN of the same organization or a SUPER_ADMIN may do this.
    """
    if current_user.role == UserRole.ANALYST:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Analysts cannot register other users.")
    if current_user.role == UserRole.ADMIN and current_user.organization_id != body.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only add analysts to your own organization.")

    org = db.execute(select(Organization).where(Organization.id == body.org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    existing = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    analyst = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=UserRole.ANALYST,
        organization_id=body.org_id,
    )
    db.add(analyst)
    db.commit()
    db.refresh(analyst)
    return _build_user_summary(analyst, db)


@router.get("/me", response_model=UserSummaryResponse)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserSummaryResponse:
    """Return the authenticated user's profile."""
    return _build_user_summary(current_user, db)


@router.post("/seed-demo-users", status_code=status.HTTP_201_CREATED)
def seed_demo_users(db: Session = Depends(get_db)) -> dict:
    """
    Provision the standard multi-tenant demo fixture for development and evaluation.

    Creates:
      - 1 Super Admin
      - Organization 1: Apex Capital (2 admins, 3 analysts, no batches)
      - Organization 2: Meridian Clearing (1 admin, 2 analysts, no batches)

    Idempotent: skips creation of any accounts that already exist.
    """
    created: list[str] = []

    def ensure_org(name: str, slug: str) -> Organization:
        org = db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()
        if not org:
            org = Organization(name=name, slug=slug)
            db.add(org)
            db.flush()  # obtain org.id before creating users
            created.append(f"org:{slug}")
        return org

    def ensure_user(email: str, full_name: str, role: UserRole, org: Organization | None, password: str) -> User:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user:
            user = User(
                email=email,
                full_name=full_name,
                hashed_password=hash_password(password),
                role=role,
                organization=org,
            )
            db.add(user)
            created.append(f"user:{email}")
        return user

    # Super Admin (no organization)
    ensure_user("superadmin@recalce.internal", "Platform Admin", UserRole.SUPER_ADMIN, None, "Recalce@2026!")

    # Org 1: Apex Capital
    apex = ensure_org("Apex Capital", "apex-capital")
    ensure_user("admin1@apexcap.com", "Sarah Chen", UserRole.ADMIN, apex, "Apex@2026!")
    ensure_user("admin2@apexcap.com", "Marcus Obi", UserRole.ADMIN, apex, "Apex@2026!")
    ensure_user("analyst1@apexcap.com", "Priya Sharma", UserRole.ANALYST, apex, "Apex@2026!")
    ensure_user("analyst2@apexcap.com", "Tom Kwiatkowski", UserRole.ANALYST, apex, "Apex@2026!")
    ensure_user("analyst3@apexcap.com", "Lena Vogel", UserRole.ANALYST, apex, "Apex@2026!")

    # Org 2: Meridian Clearing
    meridian = ensure_org("Meridian Clearing", "meridian-clearing")
    ensure_user("admin@meridian.com", "James Okafor", UserRole.ADMIN, meridian, "Meridian@2026!")
    ensure_user("analyst4@meridian.com", "Fiona Walsh", UserRole.ANALYST, meridian, "Meridian@2026!")
    ensure_user("analyst5@meridian.com", "Raj Patel", UserRole.ANALYST, meridian, "Meridian@2026!")

    db.commit()
    return {"created": created, "message": f"{len(created)} records provisioned."}
