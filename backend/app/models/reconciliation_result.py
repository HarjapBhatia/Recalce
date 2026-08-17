"""
app/models/reconciliation_result.py
-------------------------------------
ReconciliationResult -- one row per matched or unreconciled pair.

- For one-to-one matches: internal_txn_id and bank_txn_id are both set.
- For unreconciled internal records: bank_txn_id is NULL.
- For unreconciled bank records: internal_txn_id is NULL.
- group_id is reserved for future many-to-one support (currently unused).

BatchValidationError: one row per invalid CSV row during ingestion.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.bank_statement import BankStatement
    from app.models.internal_ledger import InternalLedger
    from app.models.reconciliation_batch import ReconciliationBatch


class MatchType(str, enum.Enum):
    EXACT = "EXACT"
    DATE_SHIFT = "DATE_SHIFT"
    FEE_ADJUSTED = "FEE_ADJUSTED"
    UNRECONCILED = "UNRECONCILED"


class ResultStatus(str, enum.Enum):
    MATCHED = "MATCHED"
    UNRECONCILED = "UNRECONCILED"
    UNDER_REVIEW = "UNDER_REVIEW"


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    internal_txn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("internal_ledger.id"), nullable=True
    )
    bank_txn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_statement.id"), nullable=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # reserved for many-to-one, unused in v1
    match_type: Mapped[MatchType] = mapped_column(Enum(MatchType), nullable=False)
    fee_deducted: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0")
    )
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anomaly_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ResultStatus] = mapped_column(Enum(ResultStatus), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_batches.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # -- Relationships ----------------------------------------------------------
    batch: Mapped["ReconciliationBatch"] = relationship(
        "ReconciliationBatch", back_populates="results"
    )
    # foreign_keys is required because this table has two FK columns pointing
    # at two different tables; SQLAlchemy cannot infer which FK to use otherwise.
    internal_txn: Mapped["InternalLedger | None"] = relationship(
        "InternalLedger", foreign_keys=[internal_txn_id]
    )
    bank_txn: Mapped["BankStatement | None"] = relationship(
        "BankStatement", foreign_keys=[bank_txn_id]
    )


class FileType(str, enum.Enum):
    INTERNAL_LEDGER = "INTERNAL_LEDGER"
    BANK_STATEMENT = "BANK_STATEMENT"


class BatchValidationError(Base):
    """Tracks per-row CSV validation failures -- does not crash the whole batch."""

    __tablename__ = "batch_validation_errors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_batches.id"), nullable=False, index=True
    )
    file_type: Mapped[FileType] = mapped_column(Enum(FileType), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)

    # -- Relationships ----------------------------------------------------------
    batch: Mapped["ReconciliationBatch"] = relationship(
        "ReconciliationBatch", back_populates="validation_errors"
    )
