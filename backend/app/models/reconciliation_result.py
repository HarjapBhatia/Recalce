"""
app/models/reconciliation_result.py
-------------------------------------
ReconciliationResult -- one row per matched or unreconciled pair.

- For one-to-one matches: internal_txn_id and bank_txn_id are both set.
- For unreconciled internal records: bank_txn_id is NULL.
- For unreconciled bank records: internal_txn_id is NULL.
- group_id links a result row to a ReconciliationGroup for N:1 matches.

BatchValidationError: one row per invalid CSV row during ingestion.

ReconciliationGroup: parent record for a many-to-one bank deposit match.
ReconciliationGroupMember: one row per internal transaction in a N:1 group.
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
    MANY_TO_ONE = "MANY_TO_ONE"
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
    )  # FK to reconciliation_groups.id for N:1 group matches
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


class ReconciliationGroup(Base):
    """
    ReconciliationGroup -- parent record for a many-to-one bank deposit match.

    One row per bank deposit that was resolved by the subset-sum pass. The bank
    deposit (bank_txn_id) maps to 2-6 internal transactions (member_count), which
    are stored in ReconciliationGroupMember. When multiple candidate subsets all
    sum to the target, status is set to UNDER_REVIEW and the competing
    combinations are serialised to review_metadata as JSON.

    fee_deducted is the difference between total_internal_amount and
    bank_deposit_amount, analogous to the same field on ReconciliationResult.
    """

    __tablename__ = "reconciliation_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_batches.id"), nullable=False, index=True
    )
    bank_txn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_statement.id"), nullable=False, index=True
    )
    match_type: Mapped[MatchType] = mapped_column(
        Enum(MatchType), nullable=False, default=MatchType.MANY_TO_ONE
    )
    total_internal_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False
    )
    bank_deposit_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False
    )
    fee_deducted: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0")
    )
    status: Mapped[ResultStatus] = mapped_column(
        Enum(ResultStatus), nullable=False, default=ResultStatus.MATCHED
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON-serialised list of competing combination sets when status=UNDER_REVIEW.
    # Each element is a list of transaction_id strings. Null when unambiguous.
    review_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # -- Relationships ----------------------------------------------------------
    batch: Mapped["ReconciliationBatch"] = relationship(
        "ReconciliationBatch", back_populates="groups"
    )
    bank_txn: Mapped["BankStatement"] = relationship(
        "BankStatement", foreign_keys=[bank_txn_id]
    )
    members: Mapped[list["ReconciliationGroupMember"]] = relationship(
        "ReconciliationGroupMember", back_populates="group", cascade="all, delete-orphan"
    )


class ReconciliationGroupMember(Base):
    """
    ReconciliationGroupMember -- one row per internal transaction in a N:1 group.

    Joins a ReconciliationGroup (the bank deposit) to each internal ledger
    transaction that was included in the matched subset. The full member list
    for a group can be fetched via the `members` relationship on
    ReconciliationGroup.
    """

    __tablename__ = "reconciliation_group_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_groups.id"), nullable=False, index=True
    )
    internal_txn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("internal_ledger.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # -- Relationships ----------------------------------------------------------
    group: Mapped["ReconciliationGroup"] = relationship(
        "ReconciliationGroup", back_populates="members"
    )
    internal_txn: Mapped["InternalLedger"] = relationship(
        "InternalLedger", foreign_keys=[internal_txn_id]
    )
