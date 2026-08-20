"""
app/schemas/result_schemas.py
-----------------------------
Pydantic response schemas for the reconciliation results endpoint.

These schemas define the shape of the GET /api/v1/results/{batch_id}
response body. The top-level ResultsResponse wraps a summary of match
counts, the full list of result rows (with joined transaction details
from both sides), and any CSV validation errors recorded during ingestion.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.reconciliation_result import MatchType, ResultStatus, FileType
from app.models.reconciliation_batch import BatchStatus


class ResultSummary(BaseModel):
    """Aggregate counts for a completed reconciliation batch."""

    total_internal: int
    total_bank: int
    exact_matches: int
    date_shift_matches: int
    fee_adjusted_matches: int
    many_to_one_matches: int
    under_review_groups: int
    unreconciled_internal: int
    unreconciled_bank: int
    anomalies_flagged: int


class ResultItem(BaseModel):
    """
    One reconciliation result row with joined transaction details.

    Internal-side fields are None for unreconciled bank-only records.
    Bank-side fields are None for unreconciled internal-only records.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_type: MatchType
    status: ResultStatus
    fee_deducted: Decimal
    is_anomaly: bool
    anomaly_reason: str | None = None

    # Internal ledger side (None when the result is a bank-only unreconciled record)
    internal_transaction_id: str | None = None
    internal_amount: Decimal | None = None
    internal_timestamp: datetime | None = None
    merchant_id: str | None = None

    # Bank statement side (None when the result is an internal-only unreconciled record)
    bank_reference_id: str | None = None
    deposit_amount: Decimal | None = None
    settlement_date: date | None = None

    # Group fields for Many-to-One matches
    group_id: uuid.UUID | None = None
    member_count: int | None = None
    review_metadata: str | None = None

    # Computed convenience flag: True when this row represents the bank-side of a
    # Many-to-One group (no internal_transaction_id but group_id is set). The
    # frontend uses this to render "Group (N items)" in the Reference column
    # instead of a raw bank reference string.
    @property
    def is_group(self) -> bool:
        return self.group_id is not None and self.internal_transaction_id is None


class ValidationErrorItem(BaseModel):
    """One row-level CSV validation failure recorded during ingestion."""

    model_config = ConfigDict(from_attributes=True)

    file_type: FileType
    row_number: int
    error_message: str


class ResultsResponse(BaseModel):
    """Full response body for GET /api/v1/results/{batch_id}."""

    batch_id: uuid.UUID
    status: BatchStatus
    summary: ResultSummary
    results: list[ResultItem]
    validation_errors: list[ValidationErrorItem]
    page: int = 1
    total_pages: int = 1
    total_items: int = 0
    tab_counts: dict[str, int] = {}

