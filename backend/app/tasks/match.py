"""
app/tasks/match.py
-------------------
Celery task: Stage 2 of the processing chain.

Responsibility:
  1. Transition the batch from INGESTING to MATCHING.
  2. Delegate all reconciliation logic to matching_engine.run_waterfall().
  3. If the waterfall raises any exception, set the batch to FAILED and
     re-raise so Celery logs the full traceback.
  4. On success, pass batch_id to the next task in the chain (ml_triage).

Batch status transitions: INGESTING -> MATCHING -> (passed to ml_triage)
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.reconciliation_batch import BatchStatus, ReconciliationBatch
from app.services.matching_engine import run_waterfall

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.match")
def match(self, batch_id: str) -> str:
    """
    Run the four-pass waterfall matching engine for a completed ingestion run.

    Receives batch_id as a string from the ingest task via the Celery chain.
    Returns batch_id as a string so the chain passes it to ml_triage.
    """
    db: Session = SessionLocal()
    batch_uuid = uuid.UUID(batch_id)

    try:
        batch = db.get(ReconciliationBatch, batch_uuid)
        if batch is None:
            raise ValueError(f"Batch {batch_id} not found in the database.")

        batch.status = BatchStatus.MATCHING
        db.commit()
        logger.info("Matching started: batch=%s", batch_id)

        summary = run_waterfall(batch_id, db)

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
        logger.exception("Match task raised an unexpected error: batch=%s", batch_id)
        raise

    finally:
        db.close()
