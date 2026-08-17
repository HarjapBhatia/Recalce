"""
app/tasks/ml_triage.py
-----------------------
Celery task: Stage 3 of the processing chain.

Responsibility:
  1. Transition the batch from MATCHING to ML_TRIAGE.
  2. Fetch all ReconciliationResult rows for the batch and join their linked
     InternalLedger and BankStatement rows so features can be computed.
  3. Build separate feature matrices for matched and unmatched records using
     the functions in ml/features.py.
  4. Score each record using the pre-loaded IsolationForest models held in
     app/services/anomaly_service. The models are loaded once at worker
     startup (not here) via the worker_process_init signal in celery_app.py.
  5. Write is_anomaly=True and a human-readable anomaly_reason to any result
     that the model predicts as anomalous (-1 from model.predict()).
  6. Transition the batch from ML_TRIAGE to COMPLETE and commit.

On any unexpected exception, the batch is set to FAILED before re-raising so
it never stays stuck in ML_TRIAGE indefinitely.

Batch status transitions: MATCHING -> ML_TRIAGE -> COMPLETE

Design notes:
  - Scoring is skipped gracefully if the models were not loaded at startup
    (e.g. model files are missing). The batch still completes; records are
    simply not flagged. This is preferable to crashing the entire pipeline
    because a model file is missing.
  - Unmatched bank rows (internal_txn is None) are not scored because they
    carry no merchant_id, which is required to compute merchant_freq and
    amount_zscore. They remain UNRECONCILED without an anomaly flag.
  - The feature computation is done in pandas (which anomaly_service and
    ml/features.py expect). Converting ORM objects to dicts first is
    intentional: it decouples the ML code from SQLAlchemy's lazy loading,
    avoids N+1 queries, and produces clean plain-Python data for the feature
    engineering functions.
"""

import logging
import uuid

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.reconciliation_batch import BatchStatus, ReconciliationBatch
from app.models.reconciliation_result import ReconciliationResult, ResultStatus
from app.services import anomaly_service
from ml.features import matched_features, unmatched_features

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_matched_records(results: list[ReconciliationResult]) -> list[dict]:
    """
    Collect the fields needed by matched_features() from each matched result.

    Requires that internal_txn and bank_txn are already eagerly loaded on the
    result objects (done in the main task with joinedload).

    settlement_delay_days is computed here from the two source rows. This is
    the same calculation the matching engine would use to classify a DATE_SHIFT
    match; we reproduce it here so the ML feature is consistent with matching
    logic.
    """
    records = []
    for r in results:
        if r.status != ResultStatus.MATCHED:
            continue
        if r.internal_txn is None or r.bank_txn is None:
            # Defensive guard: a matched result always has both sides set.
            # If somehow one is missing, skip it rather than crashing.
            logger.warning("Matched result %s is missing a linked transaction row -- skipping.", r.id)
            continue

        txn_date = r.internal_txn.timestamp.date()
        settlement_delay = max(0, (r.bank_txn.settlement_date - txn_date).days)

        records.append({
            "result_id": r.id,
            "amount": float(r.internal_txn.amount),
            "timestamp": r.internal_txn.timestamp,
            "merchant_id": r.internal_txn.merchant_id,
            # fee_deducted is already computed and stored by the matching engine.
            "fee_deducted": float(r.fee_deducted),
            "settlement_delay_days": settlement_delay,
        })

    return records


def _build_unmatched_records(results: list[ReconciliationResult]) -> list[dict]:
    """
    Collect the fields needed by unmatched_features() from each unreconciled
    internal ledger result.

    Only internal-side unmatched records are scored. Bank-side unmatched rows
    (where internal_txn is None) are excluded because they have no merchant_id
    and cannot produce meaningful merchant frequency or z-score features.
    """
    records = []
    for r in results:
        if r.status != ResultStatus.UNRECONCILED:
            continue
        if r.internal_txn is None:
            # This is an unmatched bank-side row. Not scoreable.
            continue

        records.append({
            "result_id": r.id,
            "amount": float(r.internal_txn.amount),
            "timestamp": r.internal_txn.timestamp,
            "merchant_id": r.internal_txn.merchant_id,
        })

    return records


def _score_and_flag(
    db: Session,
    result_id_lookup: dict[uuid.UUID, ReconciliationResult],
    records: list[dict],
    feature_fn,
    predict_fn,
    score_fn,
    label: str,
) -> int:
    """
    Build the feature matrix, score all records, and write anomaly flags.

    Returns the number of records flagged as anomalous.
    """
    if not records:
        return 0

    df = pd.DataFrame(records)
    feature_matrix = feature_fn(df)
    predictions = predict_fn(feature_matrix)
    raw_scores = score_fn(feature_matrix)

    flagged = 0
    for i, prediction in enumerate(predictions):
        if prediction == -1:
            result_id = records[i]["result_id"]
            result = result_id_lookup.get(result_id)
            if result is None:
                continue
            result.is_anomaly = True
            # Provide the raw score in the reason so reviewers can see how
            # far the record was from the decision boundary. Negative scores
            # mean anomalous; more negative means more unusual.
            result.anomaly_reason = (
                f"IsolationForest ({label}) flagged this record as anomalous. "
                f"Anomaly score: {raw_scores[i]:.4f} "
                f"(threshold: {result_id_lookup[result_id].match_type.value} model)."
            )
            flagged += 1

    return flagged


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="tasks.ml_triage")
def ml_triage(self, batch_id: str) -> str:
    """
    Score all reconciliation results for a batch using the IsolationForest models.

    This is Stage 3 of the Celery task chain: ingest -> match -> ml_triage.

    Receives batch_id as a string from the match task via the Celery chain.
    Returns batch_id as a string (though nothing follows in the current chain).

    If the models were not loaded at startup (FileNotFoundError at worker
    init), scoring is skipped and the batch still transitions to COMPLETE.
    This prevents a missing model file from blocking all reconciliation.
    """
    db: Session = SessionLocal()
    batch_uuid = uuid.UUID(batch_id)

    try:
        batch = db.get(ReconciliationBatch, batch_uuid)
        if batch is None:
            raise ValueError(f"Batch {batch_id} not found in the database.")

        batch.status = BatchStatus.ML_TRIAGE
        db.commit()
        logger.info("ML triage started: batch=%s", batch_id)

        # Eagerly load both linked transaction rows in a single query to avoid
        # N+1 queries when _build_matched_records and _build_unmatched_records
        # access r.internal_txn and r.bank_txn on each row.
        results: list[ReconciliationResult] = (
            db.query(ReconciliationResult)
            .filter(ReconciliationResult.batch_id == batch_uuid)
            .options(
                joinedload(ReconciliationResult.internal_txn),
                joinedload(ReconciliationResult.bank_txn),
            )
            .all()
        )

        # Build a direct lookup so _score_and_flag can retrieve a result by
        # its UUID without iterating the entire list on every flagged record.
        result_lookup: dict[uuid.UUID, ReconciliationResult] = {r.id: r for r in results}

        matched_records = _build_matched_records(results)
        unmatched_records = _build_unmatched_records(results)

        logger.info(
            "ML triage: batch=%s matched_records=%d unmatched_records=%d",
            batch_id, len(matched_records), len(unmatched_records),
        )

        try:
            # Check if models are available. If not, skip scoring entirely.
            anomaly_service._assert_loaded()

            flagged_matched = _score_and_flag(
                db=db,
                result_id_lookup=result_lookup,
                records=matched_records,
                feature_fn=matched_features,
                predict_fn=anomaly_service.predict_matched,
                score_fn=anomaly_service.score_matched,
                label="matched",
            )
            flagged_unmatched = _score_and_flag(
                db=db,
                result_id_lookup=result_lookup,
                records=unmatched_records,
                feature_fn=unmatched_features,
                predict_fn=anomaly_service.predict_unmatched,
                score_fn=anomaly_service.score_unmatched,
                label="unmatched",
            )

            db.commit()
            logger.info(
                "ML triage complete: batch=%s flagged_matched=%d flagged_unmatched=%d",
                batch_id, flagged_matched, flagged_unmatched,
            )

        except RuntimeError as exc:
            # Models were not loaded. Log a warning but do not fail the batch.
            logger.warning(
                "Anomaly scoring skipped for batch=%s: %s", batch_id, exc
            )

        batch.status = BatchStatus.COMPLETE
        db.commit()
        logger.info("Batch complete: batch=%s", batch_id)
        return batch_id

    except Exception as exc:
        db.rollback()
        try:
            batch = db.get(ReconciliationBatch, batch_uuid)
            if batch:
                batch.status = BatchStatus.FAILED
                batch.error_message = str(exc)
                db.commit()
        except Exception:
            pass
        logger.exception("ML triage task raised an unexpected error: batch=%s", batch_id)
        raise

    finally:
        db.close()
