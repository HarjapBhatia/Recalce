"""
app/api/routes/superadmin.py

Super Admin global endpoints. All require SUPER_ADMIN role.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_super_admin
from app.db.session import get_db
from app.models.organization import Organization
from app.models.reconciliation_batch import ReconciliationBatch
from app.models.user import User, UserRole

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


class BatchTransferRequest(BaseModel):
    target_organization_id: uuid.UUID


@router.get("/overview")
def get_overview(db: Session = Depends(get_db), _=Depends(require_super_admin)):
    """Return global platform counts."""
    org_count = db.scalar(select(func.count(Organization.id)).where(Organization.is_active == True)) or 0
    admin_count = db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.is_active == True)) or 0
    analyst_count = db.scalar(select(func.count(User.id)).where(User.role == UserRole.ANALYST, User.is_active == True)) or 0
    batch_count = db.scalar(select(func.count(ReconciliationBatch.id))) or 0
    return {
        "organizations": org_count,
        "admins": admin_count,
        "analysts": analyst_count,
        "total_batches": batch_count,
    }


@router.get("/organizations")
def list_organizations(db: Session = Depends(get_db), _=Depends(require_super_admin)):
    """List all organizations with user counts."""
    orgs = db.execute(select(Organization).order_by(Organization.name)).scalars().all()
    result = []
    for org in orgs:
        admin_count = db.scalar(select(func.count(User.id)).where(User.organization_id == org.id, User.role == UserRole.ADMIN)) or 0
        analyst_count = db.scalar(select(func.count(User.id)).where(User.organization_id == org.id, User.role == UserRole.ANALYST)) or 0
        batch_count = db.scalar(select(func.count(ReconciliationBatch.id)).where(ReconciliationBatch.organization_id == org.id)) or 0
        result.append({
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "is_active": org.is_active,
            "admin_count": admin_count,
            "analyst_count": analyst_count,
            "batch_count": batch_count,
        })
    return result


@router.get("/batches")
def list_all_batches(db: Session = Depends(get_db), _=Depends(require_super_admin)):
    """List all batches across all organizations."""
    batches = db.execute(
        select(ReconciliationBatch).order_by(ReconciliationBatch.uploaded_at.desc())
    ).scalars().all()
    return [
        {
            "batch_id": str(b.id),
            "status": b.status.value,
            "uploaded_at": b.uploaded_at.isoformat(),
            "organization_id": str(b.organization_id) if b.organization_id else None,
            "is_org_public": b.is_org_public,
            "assigned_analyst_id": str(b.assigned_analyst_id) if b.assigned_analyst_id else None,
        }
        for b in batches
    ]


@router.patch("/batches/{batch_id}/transfer")
def transfer_batch(
    batch_id: uuid.UUID,
    body: BatchTransferRequest,
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Reassign a batch to a different organization."""
    batch = db.execute(
        select(ReconciliationBatch).where(ReconciliationBatch.id == batch_id)
    ).scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")
    org = db.execute(
        select(Organization).where(Organization.id == body.target_organization_id)
    ).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Target organization not found.")
    batch.organization_id = body.target_organization_id
    batch.assigned_analyst_id = None
    batch.is_org_public = True
    db.commit()
    return {"batch_id": str(batch.id), "organization_id": str(batch.organization_id)}
