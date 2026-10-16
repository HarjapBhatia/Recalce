"""
app/api/routes/status.py

GET /api/v1/status/{batch_id}       poll the status of a reconciliation batch.
GET /api/v1/batches                 list all previous batches for the history view.
"""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.reconciliation_batch import ReconciliationBatch, BatchStatus
from app.models.reconciliation_result import (
    ReconciliationResult,
    ResultStatus,
)
from app.models.internal_ledger import InternalLedger
from app.models.bank_statement import BankStatement
from app.schemas.upload_schema import (
    BatchStatusResponse,
    BatchListItem,
    BatchReportResponse,
    ExceptionRecord,
)
from app.api.deps import get_current_user, require_batch_access
from app.models.user import User, UserRole

router = APIRouter(tags=["status"])

'''
- scalar_one_or_none() returns an object if exactly one row is returned
- one_or_none() returns the object if one row is returned
- scalar_one() returns the object if exactly one row is returned, raises an error if zero or more than one rows are returned
- scalars() returns a list of objects, one for each row returned
- scalar() returns the first column of the first row, or None if no rows are returned
'''

@router.get("/status/{batch_id}", response_model=BatchStatusResponse)
def get_status(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    batch: ReconciliationBatch = Depends(require_batch_access),
) -> BatchStatusResponse:
    """
    Poll the current status of a reconciliation batch.
    Returns 404 if the batch_id does not exist.
    """
    return BatchStatusResponse(
        batch_id=batch.id,
        status=batch.status,
        uploaded_at=batch.uploaded_at,
        error_message=batch.error_message,
    )


@router.get("/batches", response_model=list[BatchListItem])
def list_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BatchListItem]:
    """
    List all reconciliation batches, most recent first.
    Used by the frontend history view to show past upload runs.
    """
    stmt = select(ReconciliationBatch).order_by(ReconciliationBatch.uploaded_at.desc())
    
    if current_user.role == UserRole.SUPER_ADMIN:
        pass
    elif current_user.role == UserRole.ADMIN:
        stmt = stmt.where(ReconciliationBatch.organization_id == current_user.organization_id)
    else:  # ANALYST
        from sqlalchemy import or_
        stmt = stmt.where(
            ReconciliationBatch.organization_id == current_user.organization_id,
            or_(
                ReconciliationBatch.is_org_public == True,
                ReconciliationBatch.assigned_analyst_id == current_user.id,
            ),
        )

    batches = db.execute(stmt).scalars().all()

    return [
        BatchListItem(
            batch_id=b.id,
            status=b.status,
            uploaded_at=b.uploaded_at,
            error_message=b.error_message,
        )
        for b in batches
    ]


@router.get("/batches/{batch_id}/report", response_model=BatchReportResponse)
def get_batch_report(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    batch: ReconciliationBatch = Depends(require_batch_access),
) -> BatchReportResponse:
    """
    Return the batch report artifact for a completed reconciliation run.
    Includes:
    - match_rate: matched / (total_internal + total_bank)
      Under-review records are NOT counted as matched. they appear in the
      exception_list with status UNDER_REVIEW.
    - throughput: total_records / processing_time_seconds (None if timestamps
      were not recorded, e.g. for batches run before this feature was deployed)
    - exception_list: every UNRECONCILED or UNDER_REVIEW result with its reason
    - anomaly_count and anomaly_breakdown grouped by anomaly_reason text
    """

    if batch.status != BatchStatus.COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Batch is not complete. Current status: {batch.status.value}",
        )

    # Row counts (denominator for match rate and throughput)
    total_internal: int = db.execute(
        select(func.count())
        .select_from(InternalLedger)
        .where(InternalLedger.batch_id == batch_id)
    ).scalar_one()

    total_bank: int = db.execute(
        select(func.count())
        .select_from(BankStatement)
        .where(BankStatement.batch_id == batch_id)
    ).scalar_one()

    total_records = total_internal + total_bank

    # Matched count (MATCHED status only. UNDER_REVIEW excluded) 
    matched_count: int = db.execute(
        select(func.count())
        .select_from(ReconciliationResult)
        .where(
            ReconciliationResult.batch_id == batch_id,
            ReconciliationResult.status == ResultStatus.MATCHED,
        )
    ).scalar_one()

    match_rate = round(matched_count / total_records, 4) if total_records > 0 else 0.0

    # Processing time and throughput
    processing_time_seconds: float | None = None
    throughput: float | None = None
    if batch.processing_started_at and batch.processing_completed_at:
        delta = batch.processing_completed_at - batch.processing_started_at
        processing_time_seconds = round(delta.total_seconds(), 3)
        if processing_time_seconds > 0:
            throughput = round(total_records / processing_time_seconds, 2)

    # Exception list: UNRECONCILED and UNDER_REVIEW results
    exception_results = db.execute(
        select(
            ReconciliationResult,
            InternalLedger.transaction_id.label("txn_id"),
            BankStatement.bank_reference_id.label("bank_ref"),
        )
        .outerjoin(InternalLedger, ReconciliationResult.internal_txn_id == InternalLedger.id)
        .outerjoin(BankStatement, ReconciliationResult.bank_txn_id == BankStatement.id)
        .where(
            ReconciliationResult.batch_id == batch_id,
            ReconciliationResult.status.in_([ResultStatus.UNRECONCILED, ResultStatus.UNDER_REVIEW]),
        )
        .order_by(ReconciliationResult.status, ReconciliationResult.created_at)
    ).all()

    exception_list: list[ExceptionRecord] = []
    for row in exception_results:
        result: ReconciliationResult = row[0]
        # Choose the most informative reason available:
        # For UNDER_REVIEW rows (ambiguous many-to-one), use anomaly_reason.
        # For UNRECONCILED rows, use unreconciled_reason.
        reason = result.unreconciled_reason or result.anomaly_reason
        exception_list.append(
            ExceptionRecord(
                transaction_id=row.txn_id,
                bank_reference_id=row.bank_ref,
                status=result.status.value,
                reason=reason,
            )
        )

    # Anomaly count and breakdown
    anomaly_results = db.execute(
        select(ReconciliationResult.anomaly_reason)
        .where(
            ReconciliationResult.batch_id == batch_id,
            ReconciliationResult.is_anomaly.is_(True),
        )
    ).scalars().all()

    anomaly_count = len(anomaly_results)
    anomaly_breakdown: dict[str, int] = defaultdict(int)
    for reason in anomaly_results:
        # Truncate the verbose IsolationForest reason to the leading sentence
        # so the breakdown groups meaningfully rather than per-score.
        key = (reason or "Unknown").split(".")[0].strip()
        anomaly_breakdown[key] += 1

    return BatchReportResponse(
        batch_id=batch.id,
        uploaded_at=batch.uploaded_at,
        completed_at=batch.processing_completed_at,
        match_rate=match_rate,
        match_rate_definition=(
            "Matched records / (total internal + total bank records). "
            "Under-review records are not counted as matched."
        ),
        throughput=throughput,
        processing_time_seconds=processing_time_seconds,
        exception_list=exception_list,
        anomaly_count=anomaly_count,
        anomaly_breakdown=dict(anomaly_breakdown),
    )
