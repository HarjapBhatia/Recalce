"""
app/services/pipeline_service.py

Orchestrates the reconciliation pipeline as a single background function.

Replaces the previous Celery task chain (ingest -> match -> ml_triage) with
a synchronous execution within a FastAPI BackgroundTask. The three stages
still run sequentially because each stage depends on the output of the
previous one.

After the pipeline completes (or fails), the raw CSV file bytes stored
temporarily in the database are cleared to NULL to prevent database bloat.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.reconciliation_batch import ReconciliationBatch, BatchStatus
from app.tasks.ingest import ingest_batch
from app.tasks.match import run_match_step
from app.tasks.ml_triage import run_ml_triage_step

logger = logging.getLogger(__name__)


def run_reconciliation_pipeline(batch_id: uuid.UUID) -> None:
    """
    Execute the full reconciliation pipeline for a batch.

    This function is intended to be called via FastAPI's BackgroundTasks:
        background_tasks.add_task(run_reconciliation_pipeline, batch_id)

    The three stages run sequentially:
      1. Ingest: read CSV bytes from DB, validate, bulk-insert rows
      2. Match:  run the 4-pass waterfall reconciliation algorithm
      3. ML Triage: score results with IsolationForest anomaly models

    On completion or failure, the raw CSV file bytes are cleared from the
    database to free space.
    """
    db: Session = SessionLocal()

    try:
        # Stage 1: Ingest
        ingest_batch(db, batch_id)

        # Stage 2: Match
        run_match_step(db, batch_id)

        # Stage 3: ML Triage
        run_ml_triage_step(db, batch_id)

    except Exception:
        logger.exception("Pipeline failed for batch %s", batch_id)

    finally:
        # CLEANUP: Delete the raw CSV file bytes from the database to save
        # space, regardless of whether the pipeline succeeded or failed.
        try:
            batch = db.get(ReconciliationBatch, batch_id)
            if batch:
                batch.internal_file_content = None
                batch.bank_file_content = None
                db.commit()
        except Exception:
            logger.exception("Failed to clear file content for batch %s", batch_id)
        finally:
            db.close()
