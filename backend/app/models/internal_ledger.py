"""
app/models/internal_ledger.py
------------------------------
InternalLedger -- one row per internal transaction from the uploaded CSV.

amount is NUMERIC(19,4) -- never float. Parsed from CSV string to Decimal
by the Pydantic row schema before hitting the DB.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.reconciliation_batch import ReconciliationBatch


class LedgerStatus(str, enum.Enum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"


class InternalLedger(Base):
    __tablename__ = "internal_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    merchant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[LedgerStatus] = mapped_column(
        Enum(LedgerStatus), nullable=False, default=LedgerStatus.PENDING
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_batches.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # -- Relationships ----------------------------------------------------------
    batch: Mapped["ReconciliationBatch"] = relationship(
        "ReconciliationBatch", back_populates="ledger_entries"
    )
