"""
app/api/routes/upload.py

POST /api/v1/upload

Accepts two CSV files (multipart), stores their raw bytes temporarily
in the ReconciliationBatch row, schedules the reconciliation pipeline
as a FastAPI BackgroundTask, and immediately returns 202 Accepted.
"""

import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.upload_schema import UploadResponse
from app.core.config import settings
from app.models.reconciliation_batch import ReconciliationBatch, BatchStatus
from app.services.pipeline_service import run_reconciliation_pipeline

router = APIRouter(tags=["upload"])


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED, response_model=UploadResponse)
async def upload_files(
    background_tasks: BackgroundTasks,
    internal_ledger: UploadFile = File(..., description="Internal ledger CSV"),
    bank_statement:  UploadFile = File(..., description="Bank statement CSV"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """
    Upload internal ledger and bank statement CSVs for reconciliation.

    Returns 202 immediately with a batch_id. Use GET /status/{batch_id} to poll.
    """

    async def validate_csv(file: UploadFile, label: str) -> bytes:
        if file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
            raise HTTPException(status_code=400, detail=f"{label} must be a CSV file.")

        content = await file.read()
        row_count = content.count(b'\n')
        if row_count > settings.MAX_ROWS_PER_UPLOAD:
            raise HTTPException(
                status_code=400,
                detail=f"{label} exceeds maximum allowed rows ({settings.MAX_ROWS_PER_UPLOAD})."
            )
        return content

    internal_bytes = await validate_csv(internal_ledger, "Internal ledger")
    bank_bytes = await validate_csv(bank_statement, "Bank statement")

    batch_id = uuid.uuid4()

    batch = ReconciliationBatch(
        id=batch_id,
        internal_file_content=internal_bytes,
        bank_file_content=bank_bytes,
        status=BatchStatus.PENDING,
    )
    db.add(batch)
    db.commit()

    # Schedule the pipeline to run in the background via FastAPI BackgroundTasks.
    # The pipeline reads the CSV bytes from the batch row, processes them,
    # and clears the bytes when done.
    background_tasks.add_task(run_reconciliation_pipeline, batch_id)

    # Refresh the batch to ensure we have the DB-generated uploaded_at timestamp
    db.refresh(batch)

    return UploadResponse(
        batch_id=batch.id,
        status=batch.status,
        uploaded_at=batch.uploaded_at,
        message="Upload accepted. Processing started."
    )
