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
   If the narrowed pool still exceeds MAX_CANDIDATE_POOL (200), the deposit is
   escalated to UNDER_REVIEW with reason CANDIDATE_POOL_OVERFLOW rather than
   running an exhaustive search.

4. Fee-aware subset-sum solver (Strategy B or C, chosen automatically)
   All amounts are converted to integer cents (int(amount * 100)) to avoid
   floating-point drift. The allowable sum interval is:
       [target_cents, floor(target_cents / (1 - FEE_TOLERANCE_MAX))]

   Strategy B — Dynamic Programming (DP):
     Used when target deposit ≤ $50,000 (5,000,000 cents). Complexity O(N×W)
     where W is the target in cents. Builds a dict mapping reachable cent sums
     to one representative subset. Returns the first subset found whose sum
     falls within [s_min, s_max]. This handles the vast majority of real-world
     retail and SMB deposits quickly.

   Strategy C — Meet-in-the-Middle (MitM):
     Used when target deposit > $50,000 or N > 40 (DP would be too memory-
     expensive). Complexity O(2^(N/2) × N/2). Splits the candidate pool in
     half, enumerates all subset sums for each half, then binary-searches for
     complementary pairs. Practical for N up to ~60 items.

   Both strategies collect ALL valid solutions (not just the first) so that
   ambiguity detection in Stage 5 remains correct.

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

import bisect
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from math import floor
from typing import Iterator

logger = logging.getLogger(__name__)

# Configuration defaults (overridden by matching_engine from settings)

FUZZY_THRESHOLD: float = 75.0      # Minimum RapidFuzz score to accept a merchant hint
MAX_CANDIDATE_POOL: int = 200       # Raised from 50; DP/MitM can handle larger pools
MAX_GROUP_SIZE: int = 25            # Raised from 6; no longer limited by brute-force cost

# Threshold for strategy selection:
# deposits <= this value (in cents) use Strategy B (DP), larger use Strategy C (MitM).
DP_THRESHOLD_CENTS: int = 5_000_000   # $50,000.00


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
    bank_deposit     : the bank statement row this group resolves.
    matched_members  : the internal transactions included in the match. Empty list when status == UNDER_REVIEW.
    status           : "MATCHED" or "UNDER_REVIEW".
    fee_deducted_cents: total_internal_cents - deposit_cents. Zero for UNDER_REVIEW.
    anomaly_reason   : human-readable reason string for UNDER_REVIEW cases.
    review_metadata  : JSON string listing competing transaction_id combinations, populated only for AMBIGUOUS_SUBSET_SUM_TIE cases.
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
_fuzz_module = None
_fuzz_imported = False

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
    global _fuzz_module, _fuzz_imported
    if not _fuzz_imported:
        _fuzz_imported = True
        try:
            from rapidfuzz import fuzz
            _fuzz_module = fuzz
        except ImportError:
            logger.debug("rapidfuzz not installed; fuzzy merchant matching disabled.")
            _fuzz_module = None

    if _fuzz_module is None:
        return 0.0

    return max(
        _fuzz_module.token_sort_ratio(bank_ref, merchant_id),
        _fuzz_module.partial_ratio(bank_ref, merchant_id),
    )


# ---------------------------------------------------------------------------
# Strategy B — Dynamic Programming subset-sum
# ---------------------------------------------------------------------------

def _dp_subset_sum(
    candidates: list[CandidateRow],
    s_min: int,
    s_max: int,
    max_group_size: int,
) -> list[list[int]]:
    """
    Find up to 2 index subsets of `candidates` whose integer-cent sum is in
    [s_min, s_max], bounded by max_group_size.

    Two-phase approach
    ------------------
    Phase 1 — DP reachability:
        Build a 0/1 knapsack DP table mapping reachable_sum -> (size, indices).
        This gives us one representative solution in O(N × W) time.
        If no solution exists, return [] immediately (fast rejection).

    Phase 2 — Second-solution search (for ambiguity detection):
        If Phase 1 found a solution S1, we need to know whether a *different*
        subset S2 also reaches a valid sum. We run a lightweight DFS that
        excludes the exact indices in S1, capped at depth max_group_size.
        Because the candidate pool is already narrowed to ≤200 items and the
        DFS is pruned by suffix sums, this is fast in practice.

    The two-phase design gives us:
    - O(N × W) fast path for the common case (unique match).
    - Correct ambiguity detection without storing all paths in the DP table
      (which would explode memory for dense solutions).

    Returns
    -------
    [] if no solution exists.
    [s1] if exactly one distinct solution was found.
    [s1, s2] if at least two distinct solutions exist (ambiguous).
    """
    # -----------------------------------------------------------------------
    # Phase 1: DP — find one solution fast
    # -----------------------------------------------------------------------
    # dp[sum_cents] = (group_size, indices_tuple)
    dp: dict[int, tuple[int, tuple]] = {0: (0, ())}

    first_solution: tuple[int, ...] | None = None

    for item_idx, candidate in enumerate(candidates):
        c = candidate.amount_cents
        if c <= 0:
            continue

        # Iterate existing states in descending-sum order to avoid reuse (0/1 knapsack)
        for existing_sum, (sz, idxs) in sorted(dp.items(), reverse=True):
            new_sum = existing_sum + c
            new_size = sz + 1

            if new_sum > s_max or new_size > max_group_size:
                continue

            if new_sum >= s_min and new_size >= 2 and first_solution is None:
                first_solution = idxs + (item_idx,)
                # Don't return yet — finish building the full DP table so
                # Phase 2 can use it for faster pruning (suffix sums computed below).

            if new_sum not in dp or dp[new_sum][0] > new_size:
                dp[new_sum] = (new_size, idxs + (item_idx,))

    if first_solution is None:
        return []  # No solution at all

    # -----------------------------------------------------------------------
    # Phase 2: DFS excluding first_solution's indices — find a second solution
    # -----------------------------------------------------------------------
    first_set = set(first_solution)
    n = len(candidates)
    cents = [c.amount_cents for c in candidates]

    # Precompute suffix sums for lower-bound pruning
    suffix = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + cents[i]

    second_solution: list[int] | None = None

    def _dfs2(idx: int, current_sum: int, path: list[int]) -> None:
        nonlocal second_solution
        if second_solution is not None:
            return  # already found one, stop

        if current_sum >= s_min and len(path) >= 2:
            candidate_set = set(path)
            if candidate_set != first_set:
                second_solution = list(path)
                return

        if idx == n or len(path) >= max_group_size:
            return

        # Lower-bound prune
        if current_sum + suffix[idx] < s_min:
            return

        for i in range(idx, n):
            new_sum = current_sum + cents[i]
            if new_sum > s_max:
                continue
            path.append(i)
            _dfs2(i + 1, new_sum, path)
            path.pop()
            if second_solution is not None:
                return

    _dfs2(0, 0, [])

    result = [list(first_solution)]
    if second_solution is not None:
        result.append(second_solution)
    return result


# ---------------------------------------------------------------------------
# Strategy C — Meet-in-the-Middle subset-sum
# ---------------------------------------------------------------------------

def _all_subsets(
    items: list[tuple[int, int]],   # (cents_value, original_index)
    max_size: int,
) -> Iterator[tuple[int, tuple[int, ...]]]:
    """
    Yield (sum_cents, indices_tuple) for every non-empty subset of `items`
    that has at most `max_size` members.

    Uses an iterative bitmask enumeration to avoid Python recursion overhead.
    For |items| <= 30 this is fast enough (~10^9 ops limit means up to 20 items
    runs in well under 1 second in CPython).
    """
    n = len(items)
    for mask in range(1, 1 << n):
        bits = bin(mask).count("1")
        if bits > max_size:
            continue
        total = 0
        idxs: list[int] = []
        for bit in range(n):
            if mask & (1 << bit):
                total += items[bit][0]
                idxs.append(items[bit][1])
        yield total, tuple(idxs)


def _mitm_subset_sum(
    candidates: list[CandidateRow],
    s_min: int,
    s_max: int,
    max_group_size: int,
) -> list[list[int]]:
    """
    Find ALL index subsets of `candidates` whose integer-cent sum is in [s_min, s_max]
    using Meet-in-the-Middle.

    Algorithm
    ---------
    1. Split candidates into left half L and right half R.
    2. Enumerate all (sum, indices) pairs for L  -> build a sorted list and a
       lookup dict  left_map: sum -> list[indices_tuple].
    3. For each right subset (sum_R, idxs_R):
       - Compute target range for the left half: [s_min - sum_R, s_max - sum_R].
       - Binary-search left sums for any value in that range.
       - Combine matching pairs, enforcing total size <= max_group_size.
    4. Collect unique solutions; stop after 2 (ambiguity detection only).

    Complexity: O(2^(N/2) × N/2) — dramatically better than O(2^N).

    Parameters
    ----------
    candidates     : list of CandidateRow (any order).
    s_min, s_max   : inclusive allowable total range in integer cents.
    max_group_size : maximum number of members allowed in a subset.

    Returns
    -------
    List of index lists. Returns at most 2 distinct subsets.
    """
    MAX_SOLUTIONS = 2

    n = len(candidates)
    mid = n // 2
    left_items  = [(candidates[i].amount_cents, i) for i in range(mid)]
    right_items = [(candidates[i].amount_cents, i) for i in range(mid, n)]

    # Build left lookup: sorted list of sums + map sum -> list of index tuples
    left_sums_sorted: list[int] = []
    left_map: dict[int, list[tuple[int, ...]]] = {}

    left_max_size = max_group_size  # left half alone can use up to max_group_size
    for sum_l, idxs_l in _all_subsets(left_items, left_max_size):
        if sum_l not in left_map:
            bisect.insort(left_sums_sorted, sum_l)
            left_map[sum_l] = []
        left_map[sum_l].append(idxs_l)

    # Also consider the empty left subset (sum = 0) for right-only solutions
    if 0 not in left_map:
        bisect.insort(left_sums_sorted, 0)
        left_map[0] = [()]

    found_set: set[frozenset] = set()   # dedup by frozen set of original indices
    found: list[list[int]] = []

    right_max_size = max_group_size  # right half alone can use up to max_group_size

    # Include empty right subset too (so left-only solutions are found)
    right_candidates = list(_all_subsets(right_items, right_max_size))
    right_candidates.append((0, ()))   # empty right half

    for sum_r, idxs_r in right_candidates:
        need_min = s_min - sum_r
        need_max = s_max - sum_r

        if need_max < 0:
            continue  # right half already exceeds s_max

        # Binary search for left sums in [need_min, need_max]
        lo = bisect.bisect_left(left_sums_sorted, need_min)
        hi = bisect.bisect_right(left_sums_sorted, need_max)

        for li in range(lo, hi):
            sum_l = left_sums_sorted[li]
            for idxs_l in left_map[sum_l]:
                combined_size = len(idxs_l) + len(idxs_r)
                if combined_size < 2:
                    continue   # require at least 2 members
                if combined_size > max_group_size:
                    continue   # depth cap

                combined = list(idxs_l) + list(idxs_r)
                key = frozenset(combined)
                if key in found_set:
                    continue
                found_set.add(key)
                found.append(combined)
                if len(found) >= MAX_SOLUTIONS:
                    return found

    return found


# ---------------------------------------------------------------------------
# Strategy dispatcher
# ---------------------------------------------------------------------------

def _find_subsets(
    candidates: list[CandidateRow],
    s_min: int,
    s_max: int,
    max_group_size: int,
) -> list[list[int]]:
    """
    Dispatch to Strategy B (DP) or Strategy C (MitM) based on deposit size
    and candidate pool size.

    Decision rules
    --------------
    - If s_max <= DP_THRESHOLD_CENTS (50,000 dollars) AND len(candidates) <= 40:
        Use DP (Strategy B) — O(N×W), fast for small-to-mid targets.
    - Otherwise:
        Use MitM (Strategy C) — O(2^(N/2)), handles large targets / large pools.

    Both strategies return the same contract: list of index lists, ≤2 entries.
    """
    n = len(candidates)
    if s_max <= DP_THRESHOLD_CENTS and n <= 40:
        logger.debug(
            "Strategy B (DP): N=%d, s_min=%d, s_max=%d", n, s_min, s_max
        )
        return _dp_subset_sum(candidates, s_min, s_max, max_group_size)
    else:
        logger.debug(
            "Strategy C (MitM): N=%d, s_min=%d, s_max=%d", n, s_min, s_max
        )
        return _mitm_subset_sum(candidates, s_min, s_max, max_group_size)


# ---------------------------------------------------------------------------
# Confidence scoring for Stage 6 conflict resolution
# ---------------------------------------------------------------------------

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

    Parameters:
    unmatched_internal     : internal ledger rows still PENDING after 1:1 passes.
    unmatched_bank         : bank deposit rows still PENDING after 1:1 passes.
    settlement_window_days : look-back window in days for temporal narrowing.
    fee_tolerance_max      : maximum fee fraction allowed (e.g. 0.03 = 3%).
    max_candidate_pool     : hard pool size cap before escalating to UNDER_REVIEW.
    max_group_size         : maximum number of members per group (2 to N).
    fuzzy_threshold        : minimum RapidFuzz score to accept a merchant hint.

    Returns:
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
        # Stage 1+2: Merchant identification then candidate narrowing
        # Run fuzzy merchant matching FIRST against all known merchant IDs so
        # that Stage 1 only gathers candidates from the correct merchant cluster.
        # The old order (Stage 1 across all merchants → Stage 2 narrow) caused
        # CANDIDATE_POOL_OVERFLOW for any merchant with >MAX_CANDIDATE_POOL
        # transactions inside the settlement window, even though Stage 2 would
        # have reduced that to a manageable subset.
        s_min_cents = deposit.deposit_cents
        s_max_cents = floor(deposit.deposit_cents / (1.0 - fee_tolerance_max))

        earliest = deposit.settlement_date - timedelta(days=settlement_window_days)

        # Stage 2 (early): identify target merchant via fuzzy match
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

        # Stage 1: Candidate narrowing (merchant-scoped)
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

        # Stage 3: Pool cap
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

        # Stage 4: Optimised subset-sum (Strategy B or C)
        solution_indices = _find_subsets(
            candidate_pool, s_min_cents, s_max_cents, max_group_size
        )

        if not solution_indices:
            continue  # No valid subset; leave deposit UNRECONCILED

        solutions: list[list[CandidateRow]] = [
            [candidate_pool[i] for i in idx_list]
            for idx_list in solution_indices
        ]

        # Stage 5: Strict ambiguity detection
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

    # Stage 6: Global conflict resolution
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
