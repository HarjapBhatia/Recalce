"""
app/api/routes/status.py
-------------------------
GET /api/v1/status/{batch_id}  -- poll the status of a reconciliation batch.
GET /api/v1/batches            -- list all previous batches for the history view.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.reconciliation_batch import ReconciliationBatch
from app.schemas.upload_schema import BatchStatusResponse, BatchListItem

router = APIRouter(tags=["status"])


@router.get("/status/{batch_id}", response_model=BatchStatusResponse)
def get_status(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> BatchStatusResponse:
    """
    Poll the current status of a reconciliation batch.

    Returns 404 if the batch_id does not exist.
    """
    batch = db.execute(
        select(ReconciliationBatch).where(ReconciliationBatch.id == batch_id)
    ).scalar_one_or_none()

    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch {batch_id} not found.",
        )

    return BatchStatusResponse(
        batch_id=batch.id,
        status=batch.status,
        uploaded_at=batch.uploaded_at,
        error_message=batch.error_message,
    )


@router.get("/batches", response_model=list[BatchListItem])
def list_batches(db: Session = Depends(get_db)) -> list[BatchListItem]:
    """
    List all reconciliation batches, most recent first.

    Used by the frontend history view to show past upload runs.
    """
    batches = db.execute(
        select(ReconciliationBatch).order_by(
            ReconciliationBatch.uploaded_at.desc()
        )
    ).scalars().all()

    return [
        BatchListItem(
            batch_id=b.id,
            status=b.status,
            uploaded_at=b.uploaded_at,
            error_message=b.error_message,
        )
        for b in batches
    ]
