"""
app/schemas/upload_schema.py
-----------------------------
Request/response schemas for the upload, status, and batch list endpoints.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.reconciliation_batch import BatchStatus


class UploadResponse(BaseModel):
    """Returned immediately (202 Accepted) after a successful file upload."""

    batch_id: uuid.UUID
    status: BatchStatus
    uploaded_at: datetime
    message: str = "Files received. Processing has started."


class BatchStatusResponse(BaseModel):
    """Returned by GET /status/{batch_id}."""

    batch_id: uuid.UUID
    status: BatchStatus
    uploaded_at: datetime
    error_message: str | None = None


class BatchListItem(BaseModel):
    """One entry in the batch history list returned by GET /api/v1/batches."""

    model_config = ConfigDict(from_attributes=True)

    batch_id: uuid.UUID
    status: BatchStatus
    uploaded_at: datetime
    error_message: str | None = None


class ExceptionRecord(BaseModel):
    """A single exception record (UNRECONCILED or UNDER_REVIEW) for the batch report."""

    transaction_id: str | None = None
    bank_reference_id: str | None = None
    status: str
    reason: str | None = None


class BatchReportResponse(BaseModel):
    """Response body for GET /api/v1/batches/{batch_id}/report."""

    batch_id: uuid.UUID
    uploaded_at: datetime
    completed_at: datetime | None = None
    match_rate: float
    match_rate_definition: str
    throughput: float | None = None
    processing_time_seconds: float | None = None
    exception_list: list[ExceptionRecord]
    anomaly_count: int
    anomaly_breakdown: dict[str, int]
