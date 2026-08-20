"""
app/services/subset_sum.py
---------------------------
Pure-algorithm engine for Many-to-One (N:1) reconciliation.

This module is deliberately free of SQLAlchemy imports so that it can be
unit-tested without a database connection. The matching_engine.py layer is
responsible for loading ORM objects, converting them to the lightweight
CandidateRow / BankDeposit dataclasses used here, and persisting the results
returned by run_many_to_one_pass().

Pipeline (six stages, in order)
--------------------------------
1. Candidate narrowing
   For each unmatched bank deposit, restrict candidate internal transactions to
   the same merchant cluster and the configured settlement look-back window.
   Transactions whose individual amount exceeds the maximum permissible sum
   (deposit / (1 - FEE_TOLERANCE_MAX)) are also discarded.

2. RapidFuzz reference matching
   When the bank deposit carries a reference string (bank_reference_id), score
   it against every merchant_id in the candidate pool using Token Sort Ratio and
   Partial Ratio from rapidfuzz.fuzz. If any merchant scores >= FUZZY_THRESHOLD
   (default 75), the candidate pool is narrowed exclusively to that merchant.
   When no merchant clears the threshold, the deposit is left UNRECONCILED
   (safer than matching across unrelated merchants).

3. Pool capping and complexity guards
   If the narrowed pool still exceeds MAX_CANDIDATE_POOL (50), the deposit is
   escalated to UNDER_REVIEW with reason CANDIDATE_POOL_OVERFLOW rather than
   running an exhaustive search.

4. Fee-aware branch-and-bound subset sum
   All amounts are converted to integer cents (int(amount * 100)) to avoid
   floating-point drift. The allowable sum interval is:
       [target_cents, floor(target_cents / (1 - FEE_TOLERANCE_MAX))]
   The solver uses depth-first search with two pruning conditions:
   - Upper bound: if current_sum + candidate > s_max, skip.
   - Lower bound: if current_sum + suffix_sum[i] < s_min, prune the branch.
   Max recursion depth is capped at MAX_GROUP_SIZE. All valid subsets are
   collected; the search is NOT stopped at the first solution.

5. Strict ambiguity detection
   - 0 solutions  -> bank deposit stays UNRECONCILED.
   - 1 solution   -> MATCHED, fee_deducted = sum - deposit.
   - >= 2 solutions -> ALL involved transactions and the bank deposit are
                      marked UNDER_REVIEW with reason AMBIGUOUS_SUBSET_SUM_TIE.
                      No tie-breaking heuristic is applied; financial safety
                      takes priority over automation.

6. Global conflict resolution
   Across all bank deposits in the batch, if two MATCHED groups share any
   internal transaction, the lower-confidence group is demoted to UNDER_REVIEW
   with reason OVERLAPPING_GROUP_SETTLEMENT_CONFLICT.

Data contracts
--------------
Input:  list[CandidateRow], list[BankDeposit], and config scalars.
Output: tuple of (list[GroupMatch], consumed_internal_ids, consumed_bank_ids).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from math import floor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration defaults (overridden by matching_engine from settings)
# ---------------------------------------------------------------------------

FUZZY_THRESHOLD: float = 75.0      # Minimum RapidFuzz score to accept a merchant hint
MAX_CANDIDATE_POOL: int = 50        # Hard cap; beyond this, escalate to UNDER_REVIEW
MAX_GROUP_SIZE: int = 6             # Maximum internal transactions per bank deposit


# ---------------------------------------------------------------------------
# Input / output dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateRow:
    """
    Lightweight representation of one unmatched internal ledger transaction.

    `amount` is the original Decimal value from the database. Integer-cent
    arithmetic is accessed through the `amount_cents` property to avoid any
    floating-point conversion on the Decimal itself.
    """

    db_id: object           # uuid.UUID from InternalLedger.id
    transaction_id: str     # human-readable TXN-XXXXXX label
    merchant_id: str
    amount: Decimal         # NUMERIC(19,4) from the database, never float
    timestamp_date: object  # datetime.date for temporal window filtering

    @property
    def amount_cents(self) -> int:
        """Return amount as an integer number of cents with no floating-point conversion."""
        return int(self.amount * 100)


@dataclass(frozen=True)
class BankDeposit:
    """Lightweight representation of one unmatched bank statement row."""

    db_id: object            # uuid.UUID from BankStatement.id
    bank_reference_id: str   # raw reference string; may contain a merchant hint
    deposit_amount: Decimal  # NUMERIC(19,4)
    settlement_date: object  # datetime.date

    @property
    def deposit_cents(self) -> int:
        """Return deposit_amount as integer cents."""
        return int(self.deposit_amount * 100)


@dataclass
class GroupMatch:
    """
    A single resolved (or ambiguous) group settlement result.

    Produced by run_many_to_one_pass() and consumed by matching_engine.py,
    which translates it into ReconciliationGroup + ReconciliationGroupMember
    ORM rows and updates InternalLedger / BankStatement statuses.

    Fields
    ------
    bank_deposit     : the bank statement row this group resolves.
    matched_members  : the internal transactions included in the match.
                       Empty list when status == UNDER_REVIEW.
    status           : "MATCHED" or "UNDER_REVIEW".
    fee_deducted_cents: total_internal_cents - deposit_cents. Zero for UNDER_REVIEW.
    anomaly_reason   : human-readable reason string for UNDER_REVIEW cases.
    review_metadata  : JSON string listing competing transaction_id combinations,
                       populated only for AMBIGUOUS_SUBSET_SUM_TIE cases.
    """

    bank_deposit: BankDeposit
    matched_members: list[CandidateRow]
    status: str                           # "MATCHED" | "UNDER_REVIEW"
    fee_deducted_cents: int = 0
    anomaly_reason: str | None = None
    review_metadata: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fuzzy_score(bank_ref: str, merchant_id: str) -> float:
    """
    Return the best RapidFuzz similarity score between bank_ref and merchant_id.

    Two scoring strategies are combined and the higher score is returned:
    - token_sort_ratio: handles word reordering and punctuation differences
      (e.g. "ACME SETTLE" vs "SETTLE ACME" -> 100).
    - partial_ratio: handles embedded substrings
      (e.g. "BATCH-MERCH001-20240115" vs "MERCH001" -> high score).

    Returns 0.0 if rapidfuzz is not installed, allowing the caller to proceed
    without the optional dependency (N:1 matching will be skipped entirely).
    """
    try:
        from rapidfuzz import fuzz  # optional dependency
        return max(
            fuzz.token_sort_ratio(bank_ref, merchant_id),
            fuzz.partial_ratio(bank_ref, merchant_id),
        )
    except ImportError:
        logger.debug("rapidfuzz not installed; fuzzy merchant matching disabled.")
        return 0.0


def _branch_and_bound(
    candidates: list[CandidateRow],
    s_min: int,
    s_max: int,
    max_depth: int,
) -> list[list[int]]:
    """
    Find all index subsets of `candidates` whose integer-cent sum is in [s_min, s_max].

    The `candidates` list MUST be sorted descending by amount_cents before
    calling this function. This ordering enables both pruning conditions:

    Upper-bound prune:
        If current_sum + candidates[i].amount_cents > s_max, we skip item i.
        We do NOT break, because a smaller item later could still fit.

    Lower-bound prune:
        If current_sum + suffix_sum[i] < s_min, no combination starting at
        index i can reach the minimum, so we prune the entire branch.

    Parameters
    ----------
    candidates : CandidateRow list, sorted descending by amount_cents.
    s_min      : minimum acceptable total in integer cents (the deposit amount).
    s_max      : maximum acceptable total in integer cents
                 (= floor(deposit / (1 - fee_tolerance))).
    max_depth  : maximum subset size (MAX_GROUP_SIZE, default 6).

    Returns
    -------
    List of index lists. Each inner list contains indices into `candidates`
    that form one valid subset. An empty outer list means no solution was found.
    """
    n = len(candidates)
    cents = [c.amount_cents for c in candidates]

    # Precompute suffix sums for the lower-bound prune
    suffix = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + cents[i]

    solutions: list[list[int]] = []

    def _dfs(idx: int, current_sum: int, path: list[int]) -> None:
        # Record any valid subset with at least 2 members
        if s_min <= current_sum <= s_max and len(path) >= 2:
            solutions.append(list(path))
            # Do NOT return: a strict superset might also be valid within s_max

        # Base cases
        if idx == n or len(path) >= max_depth:
            return

        # Lower-bound prune: even taking all remaining items cannot reach s_min
        if current_sum + suffix[idx] < s_min:
            return

        for i in range(idx, n):
            new_sum = current_sum + cents[i]
            # Upper-bound prune: this item pushes sum over s_max; try next (smaller) item
            if new_sum > s_max:
                continue
            path.append(i)
            _dfs(i + 1, new_sum, path)
            path.pop()

    _dfs(0, 0, [])
    return solutions


def _confidence_score(deposit: BankDeposit, members: list[CandidateRow]) -> float:
    """
    Return a sortable confidence score used during Stage 6 conflict resolution.

    Priority 1: exact-sum matches (fee_deducted == 0) beat fee-adjusted ones.
    Priority 2: fewer members beat more members (parsimony / Occam's Razor).
    Higher return value = higher confidence.
    """
    total_cents = sum(m.amount_cents for m in members)
    is_exact = (total_cents == deposit.deposit_cents)
    return (1.0 if is_exact else 0.0) - len(members) * 0.001


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_many_to_one_pass(
    unmatched_internal: list[CandidateRow],
    unmatched_bank: list[BankDeposit],
    settlement_window_days: int,
    fee_tolerance_max: float,
    max_candidate_pool: int = MAX_CANDIDATE_POOL,
    max_group_size: int = MAX_GROUP_SIZE,
    fuzzy_threshold: float = FUZZY_THRESHOLD,
) -> tuple[list[GroupMatch], set[object], set[object]]:
    """
    Run the full 6-stage Many-to-One matching pipeline for one batch.

    Parameters
    ----------
    unmatched_internal     : internal ledger rows still PENDING after 1:1 passes.
    unmatched_bank         : bank deposit rows still PENDING after 1:1 passes.
    settlement_window_days : look-back window in days for temporal narrowing.
    fee_tolerance_max      : maximum fee fraction allowed (e.g. 0.03 = 3%).
    max_candidate_pool     : hard pool size cap before escalating to UNDER_REVIEW.
    max_group_size         : maximum number of members per group (2 to N).
    fuzzy_threshold        : minimum RapidFuzz score to accept a merchant hint.

    Returns
    -------
    groups : list[GroupMatch]
        All resolved and under-review groups, ready for persistence.
    consumed_internal_ids : set of db_id values for internal rows claimed by
        MATCHED groups. These will be set to MATCHED in the database.
    consumed_bank_ids : set of db_id values for bank rows resolved by this pass
        (MATCHED or UNDER_REVIEW). Pass 5 (UNRECONCILED fallback) will skip them.

    Note: UNDER_REVIEW groups do NOT consume their candidate internal IDs.
    Those transactions remain in the unmatched pool and will be written as
    UNRECONCILED by Pass 5, so the reviewer can still act on them.
    """
    from datetime import timedelta

    groups: list[GroupMatch] = []
    consumed_bank_ids: set[object] = set()
    # Build a running set of internal IDs claimed by MATCHED groups so far;
    # updated after each deposit is processed to prevent double-claiming.
    claimed_internal_ids: set[object] = set()

    # Pre-index internal rows by merchant_id for O(1) cluster lookup
    by_merchant: dict[str, list[CandidateRow]] = {}
    for row in unmatched_internal:
        by_merchant.setdefault(row.merchant_id, []).append(row)

    for deposit in unmatched_bank:
        # ── Stage 1+2: Merchant identification then candidate narrowing ────────
        # Run fuzzy merchant matching FIRST against all known merchant IDs so
        # that Stage 1 only gathers candidates from the correct merchant cluster.
        # The old order (Stage 1 across all merchants → Stage 2 narrow) caused
        # CANDIDATE_POOL_OVERFLOW for any merchant with >MAX_CANDIDATE_POOL
        # transactions inside the settlement window, even though Stage 2 would
        # have reduced that to a manageable subset.
        s_min_cents = deposit.deposit_cents
        s_max_cents = floor(deposit.deposit_cents / (1.0 - fee_tolerance_max))

        earliest = deposit.settlement_date - timedelta(days=settlement_window_days)

        # ── Stage 2 (early): identify target merchant via fuzzy match ──────────
        best_merchant: str | None = None
        best_score: float = 0.0
        for mid in by_merchant:
            score = _fuzzy_score(deposit.bank_reference_id, mid)
            if score > best_score:
                best_score = score
                best_merchant = mid

        if best_score < fuzzy_threshold or best_merchant is None:
            # No merchant hint above threshold: skip N:1 for financial safety
            logger.debug(
                "Deposit %s: best fuzzy score %.1f%% < threshold %.0f%%; skipping N:1.",
                deposit.bank_reference_id,
                best_score,
                fuzzy_threshold,
            )
            continue

        # ── Stage 1: Candidate narrowing (merchant-scoped) ────────────────────
        candidate_pool: list[CandidateRow] = [
            row
            for row in by_merchant[best_merchant]
            if (
                earliest <= row.timestamp_date <= deposit.settlement_date
                and row.amount_cents <= s_max_cents
                and row.db_id not in claimed_internal_ids
            )
        ]

        if not candidate_pool:
            continue

        # ── Stage 3: Pool cap ─────────────────────────────────────────────────
        if len(candidate_pool) > max_candidate_pool:
            logger.warning(
                "Deposit %s: pool size %d > cap %d; escalating to UNDER_REVIEW.",
                deposit.bank_reference_id,
                len(candidate_pool),
                max_candidate_pool,
            )
            groups.append(GroupMatch(
                bank_deposit=deposit,
                matched_members=[],
                status="UNDER_REVIEW",
                anomaly_reason="CANDIDATE_POOL_OVERFLOW",
            ))
            consumed_bank_ids.add(deposit.db_id)
            continue

        # ── Stage 4: Branch-and-bound subset sum ──────────────────────────────
        # Sort descending so the upper-bound prune in _branch_and_bound works.
        candidate_pool.sort(key=lambda r: r.amount_cents, reverse=True)
        solution_indices = _branch_and_bound(
            candidate_pool, s_min_cents, s_max_cents, max_group_size
        )

        if not solution_indices:
            continue  # No valid subset; leave deposit UNRECONCILED

        solutions: list[list[CandidateRow]] = [
            [candidate_pool[i] for i in idx_list]
            for idx_list in solution_indices
        ]

        # ── Stage 5: Strict ambiguity detection ───────────────────────────────
        if len(solutions) == 1:
            members = solutions[0]
            total_cents = sum(m.amount_cents for m in members)
            fee_cents = total_cents - s_min_cents
            groups.append(GroupMatch(
                bank_deposit=deposit,
                matched_members=members,
                status="MATCHED",
                fee_deducted_cents=fee_cents,
            ))
            for m in members:
                claimed_internal_ids.add(m.db_id)
            consumed_bank_ids.add(deposit.db_id)
            logger.info(
                "Deposit %s MATCHED with %d members (fee=%d cents).",
                deposit.bank_reference_id,
                len(members),
                fee_cents,
            )
        else:
            # Multiple valid subsets: strict financial safety
            combinations_json = json.dumps([
                [row.transaction_id for row in sol] for sol in solutions
            ])
            groups.append(GroupMatch(
                bank_deposit=deposit,
                matched_members=[],
                status="UNDER_REVIEW",
                anomaly_reason=(
                    f"AMBIGUOUS_SUBSET_SUM_TIE: {len(solutions)} possible "
                    f"combinations found for deposit {deposit.bank_reference_id}"
                ),
                review_metadata=combinations_json,
            ))
            consumed_bank_ids.add(deposit.db_id)
            logger.warning(
                "Deposit %s UNDER_REVIEW: %d ambiguous subsets.",
                deposit.bank_reference_id,
                len(solutions),
            )

    # ── Stage 6: Global conflict resolution ───────────────────────────────────
    # Build an index from internal_txn db_id -> list of MATCHED groups that claim it.
    matched_groups = [g for g in groups if g.status == "MATCHED"]
    txn_to_groups: dict[object, list[GroupMatch]] = {}
    for g in matched_groups:
        for m in g.matched_members:
            txn_to_groups.setdefault(m.db_id, []).append(g)

    for _txn_id, competing in txn_to_groups.items():
        if len(competing) <= 1:
            continue
        # Higher confidence wins; demote all losers
        competing.sort(
            key=lambda g: _confidence_score(g.bank_deposit, g.matched_members),
            reverse=True,
        )
        winner = competing[0]
        for loser in competing[1:]:
            loser.status = "UNDER_REVIEW"
            loser.anomaly_reason = (
                f"OVERLAPPING_GROUP_SETTLEMENT_CONFLICT: transaction also "
                f"claimed by deposit {winner.bank_deposit.bank_reference_id}"
            )
            loser.matched_members = []
            loser.fee_deducted_cents = 0
            logger.warning(
                "Conflict: deposit %s demoted; deposit %s retains the transaction.",
                loser.bank_deposit.bank_reference_id,
                winner.bank_deposit.bank_reference_id,
            )

    # Final consumed_internal_ids reflects only genuinely MATCHED groups
    consumed_internal_ids: set[object] = set()
    for g in groups:
        if g.status == "MATCHED":
            for m in g.matched_members:
                consumed_internal_ids.add(m.db_id)

    return groups, consumed_internal_ids, consumed_bank_ids
