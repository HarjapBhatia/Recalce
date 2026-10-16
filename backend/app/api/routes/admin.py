"""
app/api/routes/admin.py

Org Admin endpoints. All require ADMIN or SUPER_ADMIN role.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.organization import Organization
from app.models.reconciliation_batch import ReconciliationBatch
from app.models.user import User, UserRole
from app.services.auth_service import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


class AnalystCreateRequest(BaseModel):
    full_name: str
    email: str
    password: str


class BatchAssignmentRequest(BaseModel):
    assigned_analyst_id: Optional[uuid.UUID] = None
    is_org_public: bool = True


@router.get("/analysts")
def list_analysts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all users (admins + analysts) in the caller's organization."""
    users = db.execute(
        select(User)
        .where(User.organization_id == current_user.organization_id)
        .order_by(User.role, User.full_name)
    ).scalars().all()
    return [
        {
            "id": str(u.id),
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role.value,
            "is_active": u.is_active,
        }
        for u in users
    ]


@router.post("/analysts", status_code=status.HTTP_201_CREATED)
def create_analyst(
    body: AnalystCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Provision a new analyst in the caller's organization."""
    existing = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use.")
    analyst = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=UserRole.ANALYST,
        organization_id=current_user.organization_id,
    )
    db.add(analyst)
    db.commit()
    db.refresh(analyst)
    return {"id": str(analyst.id), "email": analyst.email, "full_name": analyst.full_name}


@router.delete("/analysts/{analyst_id}", status_code=status.HTTP_200_OK)
def delete_analyst(
    analyst_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Remove an analyst from the caller's organization."""
    if analyst_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself.")

    user = db.execute(
        select(User).where(
            User.id == analyst_id,
            User.organization_id == current_user.organization_id,
        )
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Analyst not found in your organization.")

    if user.role != UserRole.ANALYST:
        raise HTTPException(status_code=400, detail="Can only remove analyst accounts.")

    # Unassign analyst from any assigned batches
    batches = db.execute(
        select(ReconciliationBatch).where(ReconciliationBatch.assigned_analyst_id == analyst_id)
    ).scalars().all()
    for b in batches:
        b.assigned_analyst_id = None

    db.delete(user)
    db.commit()
    return {"message": f"Analyst {user.full_name} removed successfully."}


@router.get("/batches")
def list_org_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all batches owned by the caller's organization."""
    batches = db.execute(
        select(ReconciliationBatch)
        .where(ReconciliationBatch.organization_id == current_user.organization_id)
        .order_by(ReconciliationBatch.uploaded_at.desc())
    ).scalars().all()
    return [
        {
            "batch_id": str(b.id),
            "status": b.status.value,
            "uploaded_at": b.uploaded_at.isoformat(),
            "is_org_public": b.is_org_public,
            "assigned_analyst_id": str(b.assigned_analyst_id) if b.assigned_analyst_id else None,
            "created_by_user_id": str(b.created_by_user_id) if b.created_by_user_id else None,
        }
        for b in batches
    ]


@router.patch("/batches/{batch_id}/assignment")
def update_batch_assignment(
    batch_id: uuid.UUID,
    body: BatchAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Toggle org-public status or assign an analyst to a batch."""
    batch = db.execute(
        select(ReconciliationBatch).where(ReconciliationBatch.id == batch_id)
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    if batch.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    if body.assigned_analyst_id:
        analyst = db.execute(
            select(User).where(
                User.id == body.assigned_analyst_id,
                User.organization_id == current_user.organization_id,
                User.role == UserRole.ANALYST,
            )
        ).scalar_one_or_none()
        if not analyst:
            raise HTTPException(status_code=404, detail="Analyst not found in your organization.")
    batch.assigned_analyst_id = body.assigned_analyst_id
    batch.is_org_public = body.is_org_public
    db.commit()
    return {"batch_id": str(batch.id), "is_org_public": batch.is_org_public, "assigned_analyst_id": str(batch.assigned_analyst_id) if batch.assigned_analyst_id else None}
