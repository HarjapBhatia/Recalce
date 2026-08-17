"""
app/tasks/ingest.py
--------------------
Celery task: Stage 1 of the processing chain.

Responsibility:
  1. Download both CSV files from B2 using the keys stored on the batch row.
  2. Parse each file with csv.DictReader (NOT pandas, to avoid silent float
     coercion on decimal amounts).
  3. Validate every row individually through the Pydantic row schemas.
     - Valid rows are collected and bulk-inserted into the DB.
     - Invalid rows are recorded in BatchValidationError with their row
       number and the exact validation message.
  4. Detect duplicate transaction_id values within the same upload -- this
     is an integrity error, not a formatting error, and is handled after
     parsing, not inside the Pydantic model.
  5. If zero valid rows survive for either file, the batch is set to FAILED
     with a descriptive message so the user knows the file format is wrong.
  6. On success, passes batch_id to the next task in the chain (match).

Batch status transitions: PENDING -> INGESTING -> (passed to match)
"""

import csv
import io
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.bank_statement import BankStatement, BankStatus
from app.models.internal_ledger import InternalLedger, LedgerStatus
from app.models.reconciliation_batch import BatchStatus, ReconciliationBatch
from app.models.reconciliation_result import BatchValidationError, FileType
from app.schemas.row_schemas import BankStatementRow, InternalLedgerRow
from app.services import b2_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _set_batch_status(db: Session, batch: ReconciliationBatch, status: BatchStatus, message: str | None = None) -> None:
    """Update the batch status and optional error message, then commit."""
    batch.status = status
    if message:
        batch.error_message = message
    db.commit()


def _parse_csv_bytes(raw_bytes: bytes) -> list[dict]:
    """
    Decode raw bytes and return a list of row dicts via csv.DictReader.

    DictReader is used instead of pandas to guarantee that numeric strings
    like '52.99' are never passed through a float representation at any
    point. The decimal conversion happens later inside the Pydantic model.
    """
    text = raw_bytes.decode("utf-8-sig")  # utf-8-sig strips the BOM if present
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _ingest_internal_ledger(
    db: Session,
    batch_id: uuid.UUID,
    raw_bytes: bytes,
) -> tuple[int, int]:
    """
    Parse and insert internal ledger rows.

    Validates each row through InternalLedgerRow. Valid rows are inserted in
    bulk. Invalid rows and duplicate transaction_ids within the same upload
    are recorded in BatchValidationError.

    Returns (valid_count, invalid_count).
    """
    rows = _parse_csv_bytes(raw_bytes)
    valid_orm_rows: list[InternalLedger] = []
    seen_transaction_ids: set[str] = set()
    invalid_count = 0

    for row_number, raw_row in enumerate(rows, start=2):  # row 1 is the header
        # Strip leading/trailing whitespace from all keys and values produced
        # by DictReader, since some CSV exporters pad columns with spaces.
        cleaned = {k.strip(): v.strip() for k, v in raw_row.items() if k}

        # Pydantic validation
        try:
            parsed = InternalLedgerRow.model_validate(cleaned)
        except ValidationError as exc:
            # Flatten the list of error messages into a single readable string.
            messages = "; ".join(
                f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            )
            db.add(BatchValidationError(
                batch_id=batch_id,
                file_type=FileType.INTERNAL_LEDGER,
                row_number=row_number,
                error_message=messages,
            ))
            invalid_count += 1
            continue

        # Duplicate transaction_id detection within this upload.
        # This is separate from the cross-batch duplicate anomaly that the ML
        # model catches; here we are protecting against a bad export that
        # accidentally included the same row twice.
        if parsed.transaction_id in seen_transaction_ids:
            db.add(BatchValidationError(
                batch_id=batch_id,
                file_type=FileType.INTERNAL_LEDGER,
                row_number=row_number,
                error_message=f"Duplicate transaction_id '{parsed.transaction_id}' within this upload.",
            ))
            invalid_count += 1
            continue

        seen_transaction_ids.add(parsed.transaction_id)

        valid_orm_rows.append(InternalLedger(
            batch_id=batch_id,
            transaction_id=parsed.transaction_id,
            amount=parsed.amount,
            timestamp=parsed.timestamp,
            merchant_id=parsed.merchant_id,
            status=LedgerStatus.PENDING,
        ))

    if valid_orm_rows:
        db.bulk_save_objects(valid_orm_rows)

    db.commit()
    logger.info(
        "Internal ledger ingested: batch=%s valid=%d invalid=%d",
        batch_id, len(valid_orm_rows), invalid_count,
    )
    return len(valid_orm_rows), invalid_count


def _ingest_bank_statement(
    db: Session,
    batch_id: uuid.UUID,
    raw_bytes: bytes,
) -> tuple[int, int]:
    """
    Parse and insert bank statement rows.

    Works identically to _ingest_internal_ledger but targets the BankStatement
    model and BankStatementRow schema. Bank statements do not have a
    transaction_id to deduplicate, so that check is skipped here.

    Returns (valid_count, invalid_count).
    """
    rows = _parse_csv_bytes(raw_bytes)
    valid_orm_rows: list[BankStatement] = []
    invalid_count = 0

    for row_number, raw_row in enumerate(rows, start=2):
        cleaned = {k.strip(): v.strip() for k, v in raw_row.items() if k}

        try:
            parsed = BankStatementRow.model_validate(cleaned)
        except ValidationError as exc:
            messages = "; ".join(
                f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            )
            db.add(BatchValidationError(
                batch_id=batch_id,
                file_type=FileType.BANK_STATEMENT,
                row_number=row_number,
                error_message=messages,
            ))
            invalid_count += 1
            continue

        valid_orm_rows.append(BankStatement(
            batch_id=batch_id,
            bank_reference_id=parsed.bank_reference_id,
            deposit_amount=parsed.deposit_amount,
            # BankStatementRow parses settlement_date as datetime for flexibility;
            # we store only the date portion, as defined by the ORM model.
            settlement_date=parsed.settlement_date.date(),
            status=BankStatus.PENDING,
        ))

    if valid_orm_rows:
        db.bulk_save_objects(valid_orm_rows)

    db.commit()
    logger.info(
        "Bank statement ingested: batch=%s valid=%d invalid=%d",
        batch_id, len(valid_orm_rows), invalid_count,
    )
    return len(valid_orm_rows), invalid_count


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="tasks.ingest")
def ingest(self, batch_id: str) -> str:
    """
    Download CSVs from B2, validate each row, and bulk-insert into the DB.

    This is Stage 1 of the Celery task chain: ingest -> match -> ml_triage.

    The task is bound (bind=True) so that self.retry() is available if we
    want to add retry logic later (e.g., on transient B2 or DB errors).

    Returns batch_id as a string so the Celery chain passes it automatically
    to the next task (match) as its first positional argument.
    """
    db: Session = SessionLocal()
    batch_uuid = uuid.UUID(batch_id)

    try:
        # Retrieve the batch record and move it to INGESTING state immediately
        # so the frontend can show progress to the user.
        batch = db.get(ReconciliationBatch, batch_uuid)
        if batch is None:
            raise ValueError(f"Batch {batch_id} not found in the database.")

        _set_batch_status(db, batch, BatchStatus.INGESTING)
        logger.info("Ingestion started: batch=%s", batch_id)

        # Download both files from B2. These are blocking calls; B2 latency
        # is the main source of delay in this task for small files.
        internal_bytes = b2_service.download_file(batch.internal_file_key)
        bank_bytes = b2_service.download_file(batch.bank_file_key)

        # Ingest each file independently so a bad bank statement does not
        # prevent valid ledger rows from being written, and vice versa.
        internal_valid, _ = _ingest_internal_ledger(db, batch_uuid, internal_bytes)
        bank_valid, _ = _ingest_bank_statement(db, batch_uuid, bank_bytes)

        # If either file produced zero valid rows, the batch cannot be
        # reconciled. Fail fast with a message the user can act on.
        if internal_valid == 0:
            _set_batch_status(
                db, batch, BatchStatus.FAILED,
                "Internal ledger contained no valid rows. "
                "Check that the file has the required columns: "
                "transaction_id, amount, timestamp, merchant_id."
            )
            logger.error("Ingestion failed (no valid internal rows): batch=%s", batch_id)
            return batch_id

        if bank_valid == 0:
            _set_batch_status(
                db, batch, BatchStatus.FAILED,
                "Bank statement contained no valid rows. "
                "Check that the file has the required columns: "
                "bank_reference_id, deposit_amount, settlement_date."
            )
            logger.error("Ingestion failed (no valid bank rows): batch=%s", batch_id)
            return batch_id

        logger.info("Ingestion complete, handing off to match task: batch=%s", batch_id)
        # Return batch_id so the chain passes it to match() automatically.
        return batch_id

    except Exception as exc:
        # Catch-all: mark the batch as FAILED so it does not remain stuck in
        # INGESTING indefinitely. Re-raise so Celery logs the full traceback.
        db.rollback()
        try:
            batch = db.get(ReconciliationBatch, batch_uuid)
            if batch:
                _set_batch_status(db, batch, BatchStatus.FAILED, str(exc))
        except Exception:
            pass  # best effort; if the DB is down, we cannot write the failure
        logger.exception("Ingestion task raised an unexpected error: batch=%s", batch_id)
        raise

    finally:
        db.close()
