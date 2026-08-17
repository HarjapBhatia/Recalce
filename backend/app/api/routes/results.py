"""
app/api/routes/results.py
--------------------------
GET /api/v1/results/{batch_id}

Returns the full reconciliation result set for a completed batch, including
a summary of match counts, individual result rows with joined transaction
details, and any row-level validation errors from ingestion.
"""

import uuid
import math

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, or_, desc, asc
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.reconciliation_batch import ReconciliationBatch, BatchStatus
from app.models.reconciliation_result import (
    ReconciliationResult,
    MatchType,
    ResultStatus,
    BatchValidationError,
)
from app.models.internal_ledger import InternalLedger
from app.models.bank_statement import BankStatement
from app.schemas.result_schemas import (
    ResultsResponse,
    ResultSummary,
    ResultItem,
    ValidationErrorItem,
)

router = APIRouter(tags=["results"])

@router.post("/results/{result_id}/match", response_model=ResultItem)
def mark_matched(
    result_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(ReconciliationResult).where(ReconciliationResult.id == result_id)
    ).scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    result.status = ResultStatus.MATCHED
    db.commit()
    
    return ResultItem.model_validate(result)

@router.get("/results/{batch_id}", response_model=ResultsResponse)
def get_results(
    batch_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = None,
    sort: str | None = None,
    tab: str = "all",
    db: Session = Depends(get_db),
) -> ResultsResponse:
    batch = db.execute(
        select(ReconciliationBatch).where(ReconciliationBatch.id == batch_id)
    ).scalar_one_or_none()

    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch {batch_id} not found.",
        )

    if batch.status != BatchStatus.COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Batch is not complete. Current status: {batch.status.value}"
            ),
        )

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

    # Calculate Summary and Tab Counts
    all_recs_stmt = select(
        ReconciliationResult.match_type,
        ReconciliationResult.status,
        ReconciliationResult.is_anomaly,
        ReconciliationResult.internal_txn_id,
        ReconciliationResult.bank_txn_id,
    ).where(ReconciliationResult.batch_id == batch_id)
    
    all_recs = db.execute(all_recs_stmt).all()

    exact = 0
    date_shift = 0
    fee_adjusted = 0
    unreconciled_internal = 0
    unreconciled_bank = 0
    anomalies = 0
    
    tab_counts = {
        "all": len(all_recs),
        "matched": 0,
        "unreconciled": 0,
        "under_review": 0,
        "anomalies": 0,
    }

    for rec in all_recs:
        match_t = rec.match_type
        stat = rec.status
        is_anom = rec.is_anomaly
        
        if match_t == MatchType.EXACT:
            exact += 1
        elif match_t == MatchType.DATE_SHIFT:
            date_shift += 1
        elif match_t == MatchType.FEE_ADJUSTED:
            fee_adjusted += 1
        elif match_t == MatchType.UNRECONCILED:
            if rec.internal_txn_id is not None:
                unreconciled_internal += 1
            if rec.bank_txn_id is not None:
                unreconciled_bank += 1

        if is_anom:
            anomalies += 1
            
        if stat == ResultStatus.MATCHED and not is_anom:
            tab_counts["matched"] += 1
        if stat == ResultStatus.UNRECONCILED and not is_anom:
            tab_counts["unreconciled"] += 1
        if stat == ResultStatus.UNDER_REVIEW:
            tab_counts["under_review"] += 1
        if is_anom:
            tab_counts["anomalies"] += 1

    summary = ResultSummary(
        total_internal=total_internal,
        total_bank=total_bank,
        exact_matches=exact,
        date_shift_matches=date_shift,
        fee_adjusted_matches=fee_adjusted,
        unreconciled_internal=unreconciled_internal,
        unreconciled_bank=unreconciled_bank,
        anomalies_flagged=anomalies,
    )

    # Base query for results
    stmt = (
        select(
            ReconciliationResult,
            InternalLedger.transaction_id.label("txn_id"),
            InternalLedger.amount.label("int_amount"),
            InternalLedger.timestamp.label("int_timestamp"),
            InternalLedger.merchant_id.label("merchant"),
            BankStatement.bank_reference_id.label("bank_ref"),
            BankStatement.deposit_amount.label("dep_amount"),
            BankStatement.settlement_date.label("settle_date"),
        )
        .outerjoin(
            InternalLedger,
            ReconciliationResult.internal_txn_id == InternalLedger.id,
        )
        .outerjoin(
            BankStatement,
            ReconciliationResult.bank_txn_id == BankStatement.id,
        )
        .where(ReconciliationResult.batch_id == batch_id)
    )

    # Apply Tab Filter
    if tab == "matched":
        stmt = stmt.where(ReconciliationResult.status == ResultStatus.MATCHED, ReconciliationResult.is_anomaly == False)
    elif tab == "unreconciled":
        stmt = stmt.where(ReconciliationResult.status == ResultStatus.UNRECONCILED, ReconciliationResult.is_anomaly == False)
    elif tab == "under_review":
        stmt = stmt.where(ReconciliationResult.status == ResultStatus.UNDER_REVIEW)
    elif tab == "anomalies":
        stmt = stmt.where(ReconciliationResult.is_anomaly == True)

    # Apply Search Filter
    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            or_(
                func.lower(InternalLedger.transaction_id).like(func.lower(search_term)),
                func.lower(BankStatement.bank_reference_id).like(func.lower(search_term)),
                func.lower(InternalLedger.merchant_id).like(func.lower(search_term)),
            )
        )
        
    # Get total items after filtering
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_items = db.execute(count_stmt).scalar_one()
    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

    # Apply Sort Filter
    if sort == "highToLow":
        stmt = stmt.order_by(
            func.coalesce(InternalLedger.amount, BankStatement.deposit_amount, 0).desc()
        )
    elif sort == "lowToHigh":
        stmt = stmt.order_by(
            func.coalesce(InternalLedger.amount, BankStatement.deposit_amount, 0).asc()
        )
    else:
        stmt = stmt.order_by(ReconciliationResult.created_at.desc())

    # Apply Pagination
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    rows = db.execute(stmt).all()

    result_items: list[ResultItem] = []
    for row in rows:
        rec: ReconciliationResult = row[0]
        result_items.append(
            ResultItem(
                id=rec.id,
                match_type=rec.match_type,
                status=rec.status,
                fee_deducted=rec.fee_deducted,
                is_anomaly=rec.is_anomaly,
                anomaly_reason=rec.anomaly_reason,
                internal_transaction_id=row.txn_id,
                internal_amount=row.int_amount,
                internal_timestamp=row.int_timestamp,
                merchant_id=row.merchant,
                bank_reference_id=row.bank_ref,
                deposit_amount=row.dep_amount,
                settlement_date=row.settle_date,
            )
        )

    errors = db.execute(
        select(BatchValidationError).where(
            BatchValidationError.batch_id == batch_id
        )
    ).scalars().all()

    error_items = [
        ValidationErrorItem(
            file_type=e.file_type,
            row_number=e.row_number,
            error_message=e.error_message,
        )
        for e in errors
    ]

    return ResultsResponse(
        batch_id=batch_id,
        status=batch.status,
        summary=summary,
        results=result_items,
        validation_errors=error_items,
        page=page,
        total_pages=total_pages,
        total_items=total_items,
        tab_counts=tab_counts,
    )
