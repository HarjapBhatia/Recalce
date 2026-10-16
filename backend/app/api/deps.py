"""
app/api/deps.py

Reusable FastAPI dependency functions for authentication and authorization.

Usage:
    @router.get("/protected")
    def endpoint(current_user: User = Depends(get_current_user)):
        ...
"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.reconciliation_batch import ReconciliationBatch
from app.services.auth_service import decode_access_token

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Decode the Bearer token and return the corresponding active User."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.execute(select(User).where(User.id == uuid.UUID(user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Raise 403 if the current user is not a SUPER_ADMIN."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required.")
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Raise 403 if the current user is not an ADMIN or SUPER_ADMIN."""
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user


def require_batch_access(
    batch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReconciliationBatch:
    """
    Load the batch and verify the current user has permission to access it.

    Super Admin: unrestricted access.
    Admin: access to all batches within their organization.
    Analyst: access to org-public batches or batches assigned directly to them.
    """
    batch = db.execute(
        select(ReconciliationBatch).where(ReconciliationBatch.id == batch_id)
    ).scalar_one_or_none()

    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch {batch_id} not found.")

    if current_user.role == UserRole.SUPER_ADMIN:
        return batch

    if batch.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    if current_user.role == UserRole.ADMIN:
        return batch

    # Analyst: must be org-public or explicitly assigned
    if batch.is_org_public or batch.assigned_analyst_id == current_user.id:
        return batch

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
