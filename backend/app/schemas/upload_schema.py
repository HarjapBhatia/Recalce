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
