"""
app/services/matching_engine.py
---------------------------------
Five-pass waterfall reconciliation engine.

All passes execute in strict order. Each pass operates only on rows that
remain PENDING after earlier passes, so once a row is claimed it is never
re-examined.

Pass 1 -- EXACT:
  Same transaction_id (or bank_reference_id), same amount, same calendar day.
  This is the cheapest and most confident match.

Pass 2 -- DATE_SHIFT:
  Same IDs, same amount, but settlement_date is 1 to SETTLEMENT_WINDOW_DAYS
  days later than the transaction timestamp.date(). Covers normal settlement
  delays that do not involve a fee change.

Pass 3 -- FEE_ADJUSTED:
  Same IDs, date within the settlement window, but deposit_amount is between
  (amount * (1 - FEE_TOLERANCE_MAX)) and amount. Covers the common case where
  a payment processor deducts a small fee before settling.

Pass 4 -- MANY_TO_ONE:
  Subset-sum pass: finds groups of 2-MAX_GROUP_SIZE internal transactions from
  the same merchant that together sum (within fee tolerance) to a single bank
  deposit. Uses branch-and-bound DFS in integer cents to enumerate all valid
  subsets. Deposits with a single valid subset are MATCHED; deposits with
  multiple competing subsets are UNDER_REVIEW. Results are persisted as
  ReconciliationGroup + ReconciliationGroupMember rows, with a corresponding
  ReconciliationResult row (match_type=MANY_TO_ONE) per internal transaction in
  MATCHED groups, and a single bank-side ReconciliationResult for UNDER_REVIEW
  groups.

Pass 5 -- UNRECONCILED:
  Any PENDING row remaining after passes 1-4 could not be matched. Each
  surviving internal row and bank row gets its own UNRECONCILED result record.

The function is a plain Python function, not a Celery task. The match task
in app/tasks/match.py owns the DB session lifecycle and calls run_waterfall.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.bank_statement import BankStatement, BankStatus
from app.models.internal_ledger import InternalLedger, LedgerStatus
from app.models.reconciliation_result import (
    MatchType,
    ReconciliationGroup,
    ReconciliationGroupMember,
    ReconciliationResult,
    ResultStatus,
)
from app.services.subset_sum import BankDeposit, CandidateRow, run_many_to_one_pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _create_matched_result(
    db: Session,
    batch_id: uuid.UUID,
    internal_row: InternalLedger,
    bank_row: BankStatement,
    match_type: MatchType,
) -> None:
    """
    Write one ReconciliationResult row and update both source rows to MATCHED.

    fee_deducted is computed here rather than in the Pydantic schema because
    it is only meaningful once we know which bank row the internal row matched
    to. For EXACT and DATE_SHIFT matches the fee is zero; for FEE_ADJUSTED it
    is the actual difference between the ledger amount and the deposit amount.
    """
    if match_type == MatchType.FEE_ADJUSTED:
        fee_deducted = internal_row.amount - bank_row.deposit_amount
    else:
        fee_deducted = Decimal("0")

    db.add(ReconciliationResult(
        batch_id=batch_id,
        internal_txn_id=internal_row.id,
        bank_txn_id=bank_row.id,
        match_type=match_type,
        fee_deducted=fee_deducted,
        status=ResultStatus.MATCHED,
    ))
    internal_row.status = LedgerStatus.MATCHED
    bank_row.status = BankStatus.MATCHED


def _create_unreconciled_internal(db: Session, batch_id: uuid.UUID, row: InternalLedger) -> None:
    """Write an UNRECONCILED result for an internal ledger row with no bank match."""
    db.add(ReconciliationResult(
        batch_id=batch_id,
        internal_txn_id=row.id,
        bank_txn_id=None,
        match_type=MatchType.UNRECONCILED,
        fee_deducted=Decimal("0"),
        status=ResultStatus.UNRECONCILED,
    ))
    row.status = LedgerStatus.UNMATCHED


def _create_unreconciled_bank(db: Session, batch_id: uuid.UUID, row: BankStatement) -> None:
    """Write an UNRECONCILED result for a bank row with no internal match."""
    db.add(ReconciliationResult(
        batch_id=batch_id,
        internal_txn_id=None,
        bank_txn_id=row.id,
        match_type=MatchType.UNRECONCILED,
        fee_deducted=Decimal("0"),
        status=ResultStatus.UNRECONCILED,
    ))
    row.status = BankStatus.UNMATCHED


# ---------------------------------------------------------------------------
# Four-pass waterfall
# ---------------------------------------------------------------------------


def run_waterfall(batch_id: str, db: Session) -> dict:
    """
    Execute all four reconciliation passes for a batch in memory and persist in bulk.

    All matching logic is performed in-memory using hash maps for O(1) lookups.
    Results and status updates are persisted via bulk SQL operations to eliminate
    individual database round-trips over the network.
    """
    batch_uuid = uuid.UUID(batch_id)
    summary = {
        "exact": 0,
        "date_shift": 0,
        "fee_adjusted": 0,
        "many_to_one": 0,           # MATCHED group deposits resolved by Pass 4
        "under_review_groups": 0,   # UNDER_REVIEW group deposits from Pass 4
        "unreconciled_internal": 0,
        "unreconciled_bank": 0,
    }

    # Fetch all pending records for the batch in a single query per table
    internal_rows = (
        db.query(InternalLedger)
        .filter(InternalLedger.batch_id == batch_uuid, InternalLedger.status == LedgerStatus.PENDING)
        .all()
    )
    bank_rows = (
        db.query(BankStatement)
        .filter(BankStatement.batch_id == batch_uuid, BankStatement.status == BankStatus.PENDING)
        .all()
    )

    unmatched_internal = {row.id: row for row in internal_rows}
    unmatched_bank = {row.id: row for row in bank_rows}

    results_to_insert: list[ReconciliationResult] = []

    # -------------------------------------------------------------------
    # Pass 1: EXACT -- same reference ID, same amount, same calendar day
    # -------------------------------------------------------------------
    bank_index_exact: dict[tuple, list[BankStatement]] = {}
    for bank_row in unmatched_bank.values():
        key = (bank_row.bank_reference_id, bank_row.deposit_amount, bank_row.settlement_date)
        bank_index_exact.setdefault(key, []).append(bank_row)

    for int_id, int_row in list(unmatched_internal.items()):
        txn_date = int_row.timestamp.date()
        key = (int_row.transaction_id, int_row.amount, txn_date)
        candidates = bank_index_exact.get(key)
        if candidates:
            bank_row = candidates.pop(0)
            del unmatched_internal[int_id]
            del unmatched_bank[bank_row.id]
            results_to_insert.append(
                ReconciliationResult(
                    batch_id=batch_uuid,
                    internal_txn_id=int_row.id,
                    bank_txn_id=bank_row.id,
                    match_type=MatchType.EXACT,
                    fee_deducted=Decimal("0"),
                    status=ResultStatus.MATCHED,
                )
            )
            summary["exact"] += 1

    # -------------------------------------------------------------------
    # Pass 2: DATE_SHIFT -- same IDs and amount, settlement up to N days late
    # -------------------------------------------------------------------
    window = settings.SETTLEMENT_WINDOW_DAYS
    bank_index_date: dict[tuple, list[BankStatement]] = {}
    for bank_row in unmatched_bank.values():
        key = (bank_row.bank_reference_id, bank_row.deposit_amount)
        bank_index_date.setdefault(key, []).append(bank_row)

    for int_id, int_row in list(unmatched_internal.items()):
        txn_date = int_row.timestamp.date()
        key = (int_row.transaction_id, int_row.amount)
        candidates = bank_index_date.get(key, [])
        found_bank_row = None
        for b_row in candidates:
            delay = (b_row.settlement_date - txn_date).days
            if 0 < delay <= window:
                found_bank_row = b_row
                break

        if found_bank_row:
            candidates.remove(found_bank_row)
            del unmatched_internal[int_id]
            del unmatched_bank[found_bank_row.id]
            results_to_insert.append(
                ReconciliationResult(
                    batch_id=batch_uuid,
                    internal_txn_id=int_row.id,
                    bank_txn_id=found_bank_row.id,
                    match_type=MatchType.DATE_SHIFT,
                    fee_deducted=Decimal("0"),
                    status=ResultStatus.MATCHED,
                )
            )
            summary["date_shift"] += 1

    # -------------------------------------------------------------------
    # Pass 3: FEE_ADJUSTED -- same IDs, date within window, amount reduced by fee
    # -------------------------------------------------------------------
    fee_tolerance = settings.FEE_TOLERANCE_MAX
    bank_index_fee: dict[str, list[BankStatement]] = {}
    for bank_row in unmatched_bank.values():
        bank_index_fee.setdefault(bank_row.bank_reference_id, []).append(bank_row)

    for int_id, int_row in list(unmatched_internal.items()):
        txn_date = int_row.timestamp.date()
        candidates = bank_index_fee.get(int_row.transaction_id, [])
        min_deposit = int_row.amount * (1 - Decimal(str(fee_tolerance)))
        found_bank_row = None
        for b_row in candidates:
            delay = (b_row.settlement_date - txn_date).days
            if 0 <= delay <= window and min_deposit <= b_row.deposit_amount < int_row.amount:
                found_bank_row = b_row
                break

        if found_bank_row:
            candidates.remove(found_bank_row)
            del unmatched_internal[int_id]
            del unmatched_bank[found_bank_row.id]
            results_to_insert.append(
                ReconciliationResult(
                    batch_id=batch_uuid,
                    internal_txn_id=int_row.id,
                    bank_txn_id=found_bank_row.id,
                    match_type=MatchType.FEE_ADJUSTED,
                    fee_deducted=int_row.amount - found_bank_row.deposit_amount,
                    status=ResultStatus.MATCHED,
                )
            )
            summary["fee_adjusted"] += 1

    # -------------------------------------------------------------------
    # Pass 4: MANY_TO_ONE -- subset-sum group settlement matching
    # -------------------------------------------------------------------
    # Convert remaining ORM objects to lightweight dataclasses so the
    # subset_sum module stays free of SQLAlchemy dependencies and is
    # independently unit-testable.
    candidate_rows = [
        CandidateRow(
            db_id=row.id,
            transaction_id=row.transaction_id,
            merchant_id=row.merchant_id,
            amount=row.amount,
            timestamp_date=row.timestamp.date(),
        )
        for row in unmatched_internal.values()
    ]
    bank_deposits = [
        BankDeposit(
            db_id=row.id,
            bank_reference_id=row.bank_reference_id,
            deposit_amount=row.deposit_amount,
            settlement_date=row.settlement_date,
        )
        for row in unmatched_bank.values()
    ]

    groups_to_insert: list[ReconciliationGroup] = []
    members_to_insert: list[ReconciliationGroupMember] = []

    if candidate_rows and bank_deposits:
        n1_groups, consumed_int_ids, consumed_bank_ids = run_many_to_one_pass(
            unmatched_internal=candidate_rows,
            unmatched_bank=bank_deposits,
            settlement_window_days=settings.SETTLEMENT_WINDOW_DAYS,
            fee_tolerance_max=settings.FEE_TOLERANCE_MAX,
            max_candidate_pool=settings.MAX_CANDIDATE_POOL,
            max_group_size=settings.MAX_GROUP_SIZE,
        )

        for grp in n1_groups:
            deposit = grp.bank_deposit
            fee_decimal = Decimal(grp.fee_deducted_cents) / Decimal("100")
            total_internal_decimal = deposit.deposit_amount + fee_decimal

            # Build the parent ReconciliationGroup row
            group_id = uuid.uuid4()
            group_status = (
                ResultStatus.MATCHED if grp.status == "MATCHED" else ResultStatus.UNDER_REVIEW
            )
            groups_to_insert.append(
                ReconciliationGroup(
                    id=group_id,
                    batch_id=batch_uuid,
                    bank_txn_id=deposit.db_id,
                    match_type=MatchType.MANY_TO_ONE,
                    total_internal_amount=total_internal_decimal,
                    bank_deposit_amount=deposit.deposit_amount,
                    fee_deducted=fee_decimal,
                    status=group_status,
                    member_count=len(grp.matched_members),
                    review_metadata=grp.review_metadata,
                )
            )

            if grp.status == "MATCHED":
                # One ReconciliationResult + one GroupMember per internal transaction
                for member in grp.matched_members:
                    members_to_insert.append(
                        ReconciliationGroupMember(
                            group_id=group_id,
                            internal_txn_id=member.db_id,
                        )
                    )
                    results_to_insert.append(
                        ReconciliationResult(
                            batch_id=batch_uuid,
                            internal_txn_id=member.db_id,
                            bank_txn_id=deposit.db_id,
                            group_id=group_id,
                            match_type=MatchType.MANY_TO_ONE,
                            fee_deducted=fee_decimal,
                            status=ResultStatus.MATCHED,
                        )
                    )
                    # Remove from the unmatched pools so Pass 5 skips them
                    unmatched_internal.pop(member.db_id, None)
                    unmatched_bank.pop(deposit.db_id, None)

                summary["many_to_one"] += 1

            else:  # UNDER_REVIEW
                # One bank-side result row to surface in the Under Review tab
                results_to_insert.append(
                    ReconciliationResult(
                        batch_id=batch_uuid,
                        internal_txn_id=None,
                        bank_txn_id=deposit.db_id,
                        group_id=group_id,
                        match_type=MatchType.MANY_TO_ONE,
                        fee_deducted=Decimal("0"),
                        status=ResultStatus.UNDER_REVIEW,
                        anomaly_reason=grp.anomaly_reason,
                    )
                )
                # Remove the bank deposit from the unmatched pool; internal
                # transactions remain UNRECONCILED (safer than marking them matched)
                unmatched_bank.pop(deposit.db_id, None)

                summary["under_review_groups"] += 1

    # -------------------------------------------------------------------
    # Pass 5: UNRECONCILED -- remaining unmatched rows
    # -------------------------------------------------------------------
    for int_id, int_row in unmatched_internal.items():
        results_to_insert.append(
            ReconciliationResult(
                batch_id=batch_uuid,
                internal_txn_id=int_id,
                bank_txn_id=None,
                match_type=MatchType.UNRECONCILED,
                fee_deducted=Decimal("0"),
                status=ResultStatus.UNRECONCILED,
            )
        )
        summary["unreconciled_internal"] += 1

    for bank_id_val, bank_row in unmatched_bank.items():
        results_to_insert.append(
            ReconciliationResult(
                batch_id=batch_uuid,
                internal_txn_id=None,
                bank_txn_id=bank_id_val,
                match_type=MatchType.UNRECONCILED,
                fee_deducted=Decimal("0"),
                status=ResultStatus.UNRECONCILED,
            )
        )
        summary["unreconciled_bank"] += 1

    # -------------------------------------------------------------------
    # Bulk Database Persistence (Fast single-query execution)
    # -------------------------------------------------------------------
    # Derive IDs from the in-memory dictionaries rather than from ORM
    # object attributes.  This avoids marking objects dirty and prevents
    # SQLAlchemy autoflush from issuing thousands of individual UPDATEs.
    unmatched_int_set = set(unmatched_internal.keys())
    matched_int_ids = [r.id for r in internal_rows if r.id not in unmatched_int_set]
    unmatched_int_ids = list(unmatched_int_set)

    unmatched_bank_set = set(unmatched_bank.keys())
    matched_bank_ids = [r.id for r in bank_rows if r.id not in unmatched_bank_set]
    unmatched_bank_ids = list(unmatched_bank_set)

    # Detach all loaded objects so the bulk .update() calls below do not
    # trigger autoflush over the (now-stale) in-memory instances.
    db.expire_all()

    if matched_int_ids:
        db.query(InternalLedger).filter(InternalLedger.id.in_(matched_int_ids)).update(
            {"status": LedgerStatus.MATCHED}, synchronize_session=False
        )
    if unmatched_int_ids:
        db.query(InternalLedger).filter(InternalLedger.id.in_(unmatched_int_ids)).update(
            {"status": LedgerStatus.UNMATCHED}, synchronize_session=False
        )

    if matched_bank_ids:
        db.query(BankStatement).filter(BankStatement.id.in_(matched_bank_ids)).update(
            {"status": BankStatus.MATCHED}, synchronize_session=False
        )
    if unmatched_bank_ids:
        db.query(BankStatement).filter(BankStatement.id.in_(unmatched_bank_ids)).update(
            {"status": BankStatus.UNMATCHED}, synchronize_session=False
        )

    if groups_to_insert:
        db.bulk_save_objects(groups_to_insert)
    if members_to_insert:
        db.bulk_save_objects(members_to_insert)
    if results_to_insert:
        db.bulk_save_objects(results_to_insert)

    db.commit()
    logger.info("Waterfall complete: batch=%s summary=%s", batch_id, summary)
    return summary
