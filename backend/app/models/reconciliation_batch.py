"""
app/models/reconciliation_batch.py

ReconciliationBatch - one row per upload run.

Every upload creates a batch with a stable ID. The frontend polls
GET /status/{batch_id} against this table.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, deferred

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.bank_statement import BankStatement
    from app.models.internal_ledger import InternalLedger
    from app.models.reconciliation_result import BatchValidationError, ReconciliationGroup, ReconciliationResult
    from app.models.organization import Organization
    from app.models.user import User


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
    # Note: internal_file_key / bank_file_key (B2 object keys) were removed
    # when cloud storage was dropped in favour of temporary DB column storage.
    # Temporary storage for uploaded CSV file contents.
    # Deferred so regular queries never load the blob data.
    # Cleared to NULL immediately after pipeline processing completes.
    internal_file_content = deferred(mapped_column(LargeBinary, nullable=True))
    bank_file_content = deferred(mapped_column(LargeBinary, nullable=True))
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus), nullable=False, default=BatchStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships 
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
    groups: Mapped[list["ReconciliationGroup"]] = relationship(
        "ReconciliationGroup", back_populates="batch", cascade="all, delete-orphan"
    )

    # Multi-tenant ownership and assignment (added in Stage 1 RBAC)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_analyst_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_org_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships for multi-tenant fields
    organization: Mapped["Organization | None"] = relationship(
        "Organization",
        back_populates="batches",
        foreign_keys=[organization_id],
    )
    created_by: Mapped["User | None"] = relationship(
        "User",
        back_populates="created_batches",
        foreign_keys=[created_by_user_id],
    )
    assigned_analyst: Mapped["User | None"] = relationship(
        "User",
        back_populates="assigned_batches",
        foreign_keys=[assigned_analyst_id],
    )

