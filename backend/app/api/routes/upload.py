"""
app/api/routes/upload.py
-------------------------
POST /api/v1/upload

Accepts two CSV files (multipart), uploads them to B2,
creates a ReconciliationBatch row, queues the Celery task chain,
and immediately returns 202 Accepted.
"""

import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from celery import chain

from app.db.session import get_db
from app.schemas.upload_schema import UploadResponse
from app.core.config import settings
from app.models.reconciliation_batch import ReconciliationBatch, BatchStatus
from app.services import b2_service
from app.tasks.ingest import ingest
from app.tasks.match import match
from app.tasks.ml_triage import ml_triage

router = APIRouter(tags=["upload"])


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED, response_model=UploadResponse)
async def upload_files(
    internal_ledger: UploadFile = File(..., description="Internal ledger CSV"),
    bank_statement:  UploadFile = File(..., description="Bank statement CSV"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """
    Upload internal ledger and bank statement CSVs for reconciliation.

    Returns 202 immediately with a batch_id. Use GET /status/{batch_id} to poll.
    """
    def validate_csv(file: UploadFile, label: str) -> bytes:
        if file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
            raise HTTPException(status_code=400, detail=f"{label} must be a CSV file.")
        
        content = file.file.read()
        row_count = content.count(b'\n')
        if row_count > settings.MAX_ROWS_PER_UPLOAD:
            raise HTTPException(
                status_code=400, 
                detail=f"{label} exceeds maximum allowed rows ({settings.MAX_ROWS_PER_UPLOAD})."
            )
        return content

    internal_bytes = validate_csv(internal_ledger, "Internal ledger")
    bank_bytes = validate_csv(bank_statement, "Bank statement")
    
    batch_id = uuid.uuid4()
    internal_key = f"{batch_id}/internal.csv"
    bank_key = f"{batch_id}/bank.csv"

    try:
        b2_service.upload_file(internal_bytes, internal_key)
        b2_service.upload_file(bank_bytes, bank_key)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload files to B2: {str(e)}")

    batch = ReconciliationBatch(
        id=batch_id,
        internal_file_key=internal_key,
        bank_file_key=bank_key,
        status=BatchStatus.PENDING
    )
    db.add(batch)
    db.commit()
    
    # Dispatch Celery task chain
    chain(
        ingest.s(str(batch_id)),
        match.s(),
        ml_triage.s()
    ).apply_async()

    # Refresh the batch to ensure we have the DB-generated uploaded_at timestamp
    db.refresh(batch)

    return UploadResponse(
        batch_id=batch.id,
        status=batch.status,
        uploaded_at=batch.uploaded_at,
        message="Upload accepted. Processing started."
    )
