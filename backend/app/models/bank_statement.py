"""
app/models/bank_statement.py
-----------------------------
BankStatement -- one row per bank-side record from the uploaded CSV.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.reconciliation_batch import ReconciliationBatch


class BankStatus(str, enum.Enum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"


class BankStatement(Base):
    __tablename__ = "bank_statement"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bank_reference_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[BankStatus] = mapped_column(
        Enum(BankStatus), nullable=False, default=BankStatus.PENDING
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_batches.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # -- Relationships ----------------------------------------------------------
    batch: Mapped["ReconciliationBatch"] = relationship(
        "ReconciliationBatch", back_populates="bank_entries"
    )
