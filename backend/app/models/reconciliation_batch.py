"""
app/models/reconciliation_batch.py
------------------------------------
ReconciliationBatch -- one row per upload run.

Every upload creates a batch with a stable ID. The frontend polls
GET /status/{batch_id} against this table.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.bank_statement import BankStatement
    from app.models.internal_ledger import InternalLedger
    from app.models.reconciliation_result import BatchValidationError, ReconciliationResult


class BatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    MATCHING = "MATCHING"
    ML_TRIAGE = "ML_TRIAGE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ReconciliationBatch(Base):
    __tablename__ = "reconciliation_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    internal_file_key: Mapped[str] = mapped_column(String, nullable=False) # B2 key
    bank_file_key: Mapped[str] = mapped_column(String, nullable=False) # B2 key
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus), nullable=False, default=BatchStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    # -- Relationships ----------------------------------------------------------
    # One batch owns many ledger entries, bank entries, results, and errors.
    # cascade="all, delete-orphan" removes children when the batch is deleted.
    ledger_entries: Mapped[list["InternalLedger"]] = relationship(
        "InternalLedger", back_populates="batch", cascade="all, delete-orphan"
    )
    bank_entries: Mapped[list["BankStatement"]] = relationship(
        "BankStatement", back_populates="batch", cascade="all, delete-orphan"
    )
    results: Mapped[list["ReconciliationResult"]] = relationship(
        "ReconciliationResult", back_populates="batch", cascade="all, delete-orphan"
    )
    validation_errors: Mapped[list["BatchValidationError"]] = relationship(
        "BatchValidationError", back_populates="batch", cascade="all, delete-orphan"
    )
