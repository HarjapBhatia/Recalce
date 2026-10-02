"""
app/tasks/match.py

Pipeline Stage 2: Matching.

Responsibility:
1. Transition the batch from INGESTING to MATCHING.
2. Delegate all reconciliation logic to matching_engine.run_waterfall().
3. If the waterfall raises any exception, set the batch to FAILED and
    re-raise so the pipeline logs the full traceback.
4. On success, control passes to the next stage (ml_triage).

Batch status transitions: INGESTING -> MATCHING -> (passed to ml_triage)
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.reconciliation_batch import BatchStatus, ReconciliationBatch
from app.services.matching_engine import run_waterfall

logger = logging.getLogger(__name__)


def run_match_step(db: Session, batch_id: uuid.UUID) -> None:
    """
    Run the four-pass waterfall matching engine for a completed ingestion run.

    Receives the shared DB session and batch_id from the pipeline orchestrator.
    """
    try:
        batch = db.get(ReconciliationBatch, batch_id)
        if batch is None:
            raise ValueError(f"Batch {batch_id} not found in the database.")

        batch.status = BatchStatus.MATCHING
        db.commit()
        logger.info("Matching started: batch=%s", batch_id)

        summary = run_waterfall(str(batch_id), db)

        logger.info(
            "Matching complete, handing off to ml_triage: batch=%s exact=%d "
            "date_shift=%d fee_adjusted=%d unreconciled_internal=%d unreconciled_bank=%d",
            batch_id,
            summary["exact"],
            summary["date_shift"],
            summary["fee_adjusted"],
            summary["unreconciled_internal"],
            summary["unreconciled_bank"],
        )

    except Exception as exc:
        db.rollback()
        try:
            batch = db.get(ReconciliationBatch, batch_id)
            if batch:
                batch.status = BatchStatus.FAILED
                batch.error_message = str(exc)
                db.commit()
        except Exception:
            pass
        logger.exception("Match step raised an unexpected error: batch=%s", batch_id)
        raise
