"""
ml/generate_data.py
-------------------
Generates synthetic reconciliation datasets from PaySim.

Produces (per run):
  - <split>_ledger.csv
  - <split>_bank.csv
  - <split>_ground_truth.csv

Usage:
  python ml/generate_data.py --split train --seed 42  --rows 5000
  python ml/generate_data.py --split test  --seed 999 --rows 2000
"""

import argparse
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── Constants ────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[1]
PAYSIM_PATH = BACKEND_DIR / "ml" / "data" / "PS_20174392719_1491204439457_log.csv"
OUT_DIR = BACKEND_DIR / "ml" / "data"

# These reconciliation cases remain in the generated data so deterministic
# matching rules can be exercised. They are not ML anomaly labels.
OPERATIONAL_BUCKETS = [
    ("exact",      0.55),
    ("date_shift", 0.12),
    ("fee_adj",    0.08),
    ("duplicate",  0.02),
    ("missing",    0.03),
    ("group",      0.15),
    ("ambiguous",  0.03),
]

# These rows are resolved by deterministic PostgreSQL queries before ML
# scoring. Their presence tests reconciliation behavior without contaminating
# the ML target or its evaluation population.
DATABASE_RULE_BUCKETS = {"duplicate", "ambiguous"}

# This is deliberately the only ML ground-truth label.  The internal matched
# and unmatched variants below are generation mechanics, not additional labels.
ANOMALY_BUCKETS = {"anomaly"}

SETTLEMENT_WINDOW_DAYS = 3
FEE_MIN = 0.01
FEE_MAX = 0.03


# ── Helpers ───────────────────────────────────────────────────────────────────
def to_cents(amount_float: float) -> int:
    """Convert float to integer cents — never store float in output."""
    return int(Decimal(str(amount_float)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def cents_to_decimal_str(cents: int) -> str:
    """Integer cents → '1999' → '19.99' string, safe for Decimal() parsing."""
    return str(Decimal(cents) / 100)


def make_txn_id(n: int) -> str:
    return f"TXN{n:07d}"


def make_batch_id(n: int) -> str:
    return f"BATCH{n:07d}"


def base_date_for_split(split: str) -> datetime:
    """Keep train and test periods independent and relative to run time."""
    days_back = 90 if split == "train" else 30
    return datetime.now() - timedelta(days=days_back)


def step_to_timestamp(
    step: int, base_date: datetime, jitter_minutes: int = 0
) -> datetime:
    """PaySim step is simulation-hour (1-744). Map to real datetime."""
    return base_date + timedelta(hours=int(step), minutes=jitter_minutes)


def anomaly_counts(n_rows: int) -> tuple[int, int]:
    """Create enough positives for both model populations without a fixed rate.

    Each model receives approximately sqrt(N) anomaly examples. The resulting
    fraction naturally declines as the dataset grows, while smaller datasets
    still retain enough positives for a stratified validation split.
    """
    per_model = max(1, int(np.ceil(np.sqrt(n_rows))))
    matched = min(per_model, n_rows)
    unmatched = min(per_model, max(0, n_rows - matched))
    return matched, unmatched


def assign_buckets(n: int, rng: random.Random) -> list[str]:
    """Assign operational buckets, then reserve dynamic anomalies per model."""
    names = [bucket for bucket, _ in OPERATIONAL_BUCKETS]
    weights = [weight for _, weight in OPERATIONAL_BUCKETS]
    buckets = rng.choices(names, weights=weights, k=n)

    matched_count, unmatched_count = anomaly_counts(n)
    anomaly_indices = rng.sample(range(n), k=matched_count + unmatched_count)
    for index in anomaly_indices[:matched_count]:
        buckets[index] = "anomaly_matched"
    for index in anomaly_indices[matched_count:]:
        buckets[index] = "anomaly_unmatched"
    return buckets


# ── Load PaySim ───────────────────────────────────────────────────────────────
def load_paysim(
    n_rows: int, rng: random.Random, base_date: datetime
) -> tuple[pd.DataFrame, int]:
    print(f"[generate] Loading PaySim from {PAYSIM_PATH} ...")
    df = pd.read_csv(
        PAYSIM_PATH,
        usecols=["step", "type", "amount", "nameDest"],
        dtype={"step": int, "type": str, "amount": float, "nameDest": str},
    )
    df = df[df["type"].isin(["PAYMENT", "TRANSFER"])].copy()
    df = df.sample(n=min(n_rows, len(df)), random_state=rng.randint(0, 99999)).reset_index(drop=True)

    # Map nameDest → synthetic merchant IDs
    dynamic_merchant_count = max(10, int(np.sqrt(n_rows)))
    unique_dests = df["nameDest"].unique()
    dest_to_merchant = {
        d: f"MER{(i % dynamic_merchant_count):03d}"
        for i, d in enumerate(unique_dests)
    }
    df["merchant_id"] = df["nameDest"].map(dest_to_merchant)

    # Derive the settlement window from the sampled raw PaySim steps. The
    # minimum evidence requirement scales with the current dataset volume.
    df_sorted = df.sort_values(["nameDest", "step"])
    step_diffs = df_sorted.groupby("nameDest")["step"].diff().dropna()
    step_diffs = step_diffs[step_diffs > 0]
    required_diffs = max(10, int(np.ceil(np.sqrt(len(df)))))
    if len(step_diffs) >= required_diffs:
        settlement_window_days = max(
            1, int(np.ceil(np.percentile(step_diffs, 75) / 24))
        )
    else:
        settlement_window_days = SETTLEMENT_WINDOW_DAYS

    # Amount: float → integer cents (never store float)
    df["amount_cents"] = df["amount"].apply(to_cents)

    # Timestamp from step + jitter
    df["timestamp"] = df.apply(
        lambda r: step_to_timestamp(
            r["step"], base_date, jitter_minutes=rng.randint(0, 59)
        ),
        axis=1,
    )
    df["transaction_id"] = [make_txn_id(i + 1) for i in range(len(df))]

    return (
        df[["transaction_id", "amount_cents", "timestamp", "merchant_id"]].copy(),
        settlement_window_days,
    )


# ── Row writers ───────────────────────────────────────────────────────────────
def _upper_fence(values: np.ndarray) -> float:
    """Return the data-derived outer Tukey fence for a normal distribution."""
    q1, q3 = np.percentile(values, [25, 75])
    return float(q3 + 3 * (q3 - q1))


def matched_anomaly_profile(
    n_rows: int, settlement_window_days: int, rng: random.Random
) -> tuple[float, int]:
    """Derive abnormal fee and delay levels from simulated normal behavior.

    Normal fee and delay observations are generated from the same current
    configuration used by ordinary fee-adjusted and date-shift rows. An outer
    Tukey fence then defines a clearly separate, data-dependent anomaly value.
    """
    profile_size = max(4, int(np.ceil(np.sqrt(n_rows))))
    normal_fee_rates = np.array(
        [rng.uniform(FEE_MIN, FEE_MAX) for _ in range(profile_size)]
    )
    normal_delays = np.array(
        [rng.randint(0, settlement_window_days) for _ in range(profile_size)]
    )

    fee_rate = min(0.95, max(_upper_fence(normal_fee_rates), normal_fee_rates.max()))
    delay_days = max(
        int(np.ceil(_upper_fence(normal_delays))),
        int(normal_delays.max()) + 1,
    )
    return fee_rate, delay_days


def unmatched_anomaly_amounts(df: pd.DataFrame) -> dict[str, int]:
    """Build merchant-specific outlier amounts from normal PaySim histories."""
    outlier_amounts: dict[str, int] = {}
    for merchant, history in df.groupby("merchant_id"):
        amounts = history["amount_cents"].to_numpy(dtype=float)
        median = float(np.median(amounts))
        upper_fence = _upper_fence(amounts)
        dynamic_gap = max(float(amounts.max()) - median, upper_fence - median, 1.0)
        outlier_amounts[merchant] = int(
            np.ceil(max(float(amounts.max()) + dynamic_gap, upper_fence))
        )
    return outlier_amounts


def write_exact(row, ledger_rows, bank_rows, gt_rows):
    bank_rows.append({
        "bank_reference_id": row["transaction_id"],
        "deposit_amount":    row["amount_cents"],
        "settlement_date":   row["timestamp"].date(),
    })
    gt_rows.append({**row, "bucket": "exact", "group_id": None, "expected_status": "MATCHED"})


def write_date_shift(row, ledger_rows, bank_rows, gt_rows, rng, settlement_window_days: int):
    shift = rng.randint(1, settlement_window_days)
    bank_rows.append({
        "bank_reference_id": row["transaction_id"],
        "deposit_amount":    row["amount_cents"],
        "settlement_date":   (row["timestamp"] + timedelta(days=shift)).date(),
    })
    gt_rows.append({**row, "bucket": "date_shift", "group_id": None, "expected_status": "MATCHED"})


def write_fee_adj(row, ledger_rows, bank_rows, gt_rows, rng, settlement_window_days: int):
    fee_rate = Decimal(str(round(rng.uniform(FEE_MIN, FEE_MAX), 4)))
    fee_cents = int((Decimal(row["amount_cents"]) * fee_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    deposit = row["amount_cents"] - fee_cents
    shift = rng.randint(0, settlement_window_days)
    bank_rows.append({
        "bank_reference_id": row["transaction_id"],
        "deposit_amount":    deposit,
        "settlement_date":   (row["timestamp"] + timedelta(days=shift)).date(),
    })
    gt_rows.append({**row, "bucket": "fee_adj", "group_id": None, "expected_status": "MATCHED"})


def write_duplicate(row, ledger_rows, bank_rows, gt_rows, rng):
    shift = rng.randint(0, 1)
    for _ in range(2):
        bank_rows.append({
            "bank_reference_id": row["transaction_id"],
            "deposit_amount":    row["amount_cents"],
            "settlement_date":   (row["timestamp"] + timedelta(days=shift)).date(),
        })
    gt_rows.append({**row, "bucket": "duplicate", "group_id": None, "expected_status": "MATCHED"})


def write_missing(row, ledger_rows, bank_rows, gt_rows):
    # No bank row — will end up UNRECONCILED
    gt_rows.append({**row, "bucket": "missing", "group_id": None, "expected_status": "UNRECONCILED"})


def write_matched_anomaly(
    row, ledger_rows, bank_rows, gt_rows, fee_rate: float, delay_days: int
):
    """Create a matched anomaly visible through fee_ratio and settle_delay."""
    unusual_cents = max(1, int(row["amount_cents"] * (1 - fee_rate)))
    bank_rows.append({
        "bank_reference_id": row["transaction_id"],
        "deposit_amount":    unusual_cents,
        "settlement_date":   (row["timestamp"] + timedelta(days=delay_days)).date(),
    })
    gt_rows.append({
        **row,
        "bucket": "anomaly",
        "anomaly_variant": "matched_fee_delay",
        "group_id": None,
        "expected_status": "MATCHED",
    })


def write_unmatched_anomaly(row, ledger_rows, bank_rows, gt_rows):
    """Create an unmatched anomaly visible through merchant amount z-score."""
    gt_rows.append({
        **row,
        "bucket": "anomaly",
        "anomaly_variant": "unmatched_amount",
        "group_id": None,
        "expected_status": "UNRECONCILED",
    })


# ── Group builders ────────────────────────────────────────────────────────────
def build_groups(df: pd.DataFrame, rng: random.Random, group_id_start: int):
    """
    Returns a list of (list_of_row_dicts, bank_row_dict, gt_row_dicts).
    Each group is 2-5 transactions from the same merchant → 1 bank row.
    """
    results = []
    gid = group_id_start

    by_merchant = {m: grp.to_dict("records") for m, grp in df.groupby("merchant_id")}

    for _, pool in by_merchant.items():
        if len(pool) < 2:
            continue
        rng.shuffle(pool)
        i = 0
        while i + 2 <= len(pool):
            size = rng.randint(2, min(5, len(pool) - i))
            members = pool[i: i + size]
            total_cents = sum(r["amount_cents"] for r in members)
            batch_ref = make_batch_id(gid)
            # Use the latest settlement date in the group + 0-2 day shift
            max_ts = max(r["timestamp"] for r in members)
            settle_date = (max_ts + timedelta(days=rng.randint(0, 2))).date()
            bank_row = {
                "bank_reference_id": batch_ref,
                "deposit_amount":    total_cents,
                "settlement_date":   settle_date,
            }
            gt = [
                {**r, "bucket": "group", "group_id": batch_ref, "expected_status": "MATCHED"}
                for r in members
            ]
            results.append((members, bank_row, gt))
            gid += 1
            i += size

    return results


def build_ambiguous_groups(df: pd.DataFrame, rng: random.Random, group_id_start: int, count: int):
    """
    Deliberately construct pairs where two disjoint subsets sum to the same target.
    """
    results = []
    gid = group_id_start

    rows = df.to_dict("records")
    rng.shuffle(rows)

    attempts = 0
    found = 0
    idx = 0

    while found < count and idx + 6 <= len(rows) and attempts < count * 20:
        attempts += 1
        # Take 6 rows, split 3+3, try to construct equal sums via manipulation
        chunk = rows[idx: idx + 6]
        # Force equal sums: take subset A = [a, b, c], adjust c so sum(A) == sum(B)
        a, b, c, d, e, f = chunk
        # Make sum(a+b+c) == sum(d+e+?) by setting f's amount
        target = a["amount_cents"] + b["amount_cents"] + c["amount_cents"]
        f_needed = target - d["amount_cents"] - e["amount_cents"]
        if f_needed <= 0:
            idx += 3
            continue

        f = dict(f)
        f["amount_cents"] = f_needed

        batch_ref = make_batch_id(gid)
        settle_date = (max(r["timestamp"] for r in chunk) + timedelta(days=1)).date()
        bank_row = {
            "bank_reference_id": batch_ref,
            "deposit_amount":    target,
            "settlement_date":   settle_date,
        }
        gt = [
            {**r, "bucket": "ambiguous", "group_id": batch_ref, "expected_status": "UNDER_REVIEW"}
            for r in [a, b, c, d, e, f]
        ]
        results.append(([a, b, c, d, e, f], bank_row, gt))
        gid += 1
        found += 1
        idx += 6

    return results


# ── Main ──────────────────────────────────────────────────────────────────────
def generate(split: str, seed: int, n_rows: int):
    rng = random.Random(seed)
    np.random.seed(seed)

    base_date = base_date_for_split(split)
    paysim, settlement_window_days = load_paysim(n_rows, rng, base_date)

    buckets = assign_buckets(len(paysim), rng)
    paysim["bucket"] = buckets
    matched_fee_rate, matched_delay_days = matched_anomaly_profile(
        len(paysim), settlement_window_days, rng
    )
    unmatched_amount_by_merchant = unmatched_anomaly_amounts(paysim)

    ledger_rows = []
    bank_rows = []
    gt_rows = []

    group_pool_indices = []
    ambiguous_pool_indices = []

    for i, (_, row) in enumerate(paysim.iterrows()):
        r = row.to_dict()
        bucket = r["bucket"]

        # The unmatched variant has no bank row, so its anomalous amount must
        # appear in the internal ledger before the ledger record is written.
        if bucket == "anomaly_unmatched":
            r["amount_cents"] = unmatched_amount_by_merchant[r["merchant_id"]]

        ledger_rows.append({
            "transaction_id": r["transaction_id"],
            "amount":         cents_to_decimal_str(r["amount_cents"]),
            "timestamp":      r["timestamp"].isoformat(),
            "merchant_id":    r["merchant_id"],
        })

        if bucket == "exact":
            write_exact(r, ledger_rows, bank_rows, gt_rows)
        elif bucket == "date_shift":
            write_date_shift(
                r, ledger_rows, bank_rows, gt_rows, rng, settlement_window_days
            )
        elif bucket == "fee_adj":
            write_fee_adj(
                r, ledger_rows, bank_rows, gt_rows, rng, settlement_window_days
            )
        elif bucket == "duplicate":
            write_duplicate(r, ledger_rows, bank_rows, gt_rows, rng)
        elif bucket == "missing":
            write_missing(r, ledger_rows, bank_rows, gt_rows)
        elif bucket == "anomaly_matched":
            write_matched_anomaly(
                r,
                ledger_rows,
                bank_rows,
                gt_rows,
                matched_fee_rate,
                matched_delay_days,
            )
        elif bucket == "anomaly_unmatched":
            write_unmatched_anomaly(r, ledger_rows, bank_rows, gt_rows)
        elif bucket == "group":
            group_pool_indices.append(i)
            gt_rows.append({**r, "bucket": "group", "group_id": None, "expected_status": "MATCHED"})
        elif bucket == "ambiguous":
            ambiguous_pool_indices.append(i)
            gt_rows.append({**r, "bucket": "ambiguous", "group_id": None, "expected_status": "UNDER_REVIEW"})

    # Build group settlements
    group_df = paysim.iloc[group_pool_indices].copy()
    groups = build_groups(group_df, rng, group_id_start=1)
    for members, bank_row, member_gt in groups:
        bank_rows.append(bank_row)
        # Update gt_rows for group members with the actual group_id
        for gt_row in gt_rows:
            if gt_row.get("bucket") == "group" and any(
                gt_row["transaction_id"] == m["transaction_id"] for m in members
            ):
                gt_row["group_id"] = bank_row["bank_reference_id"]

    # Build ambiguous groups
    ambiguous_df = paysim.iloc[ambiguous_pool_indices].copy() if ambiguous_pool_indices else pd.DataFrame()
    n_ambiguous = max(1, len(ambiguous_pool_indices) // 6)
    if not ambiguous_df.empty:
        ambiguous_groups = build_ambiguous_groups(ambiguous_df, rng, group_id_start=10000, count=n_ambiguous)
        for members, bank_row, member_gt in ambiguous_groups:
            bank_rows.append(bank_row)

    # Write CSVs
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ledger_df = pd.DataFrame(ledger_rows)
    bank_df = pd.DataFrame(bank_rows)
    gt_df = pd.DataFrame(gt_rows)
    gt_df["ml_eligible"] = ~gt_df["bucket"].isin(DATABASE_RULE_BUCKETS)

    ledger_path = OUT_DIR / f"{split}_ledger.csv"
    bank_path   = OUT_DIR / f"{split}_bank.csv"
    gt_path     = OUT_DIR / f"{split}_ground_truth.csv"

    ledger_df.to_csv(ledger_path, index=False)
    bank_df.to_csv(bank_path, index=False)
    gt_df.to_csv(gt_path, index=False)

    print(f"[generate] {split}: {len(ledger_df)} ledger rows, {len(bank_df)} bank rows")
    print(
        "  Dynamic configuration: "
        f"merchants={max(10, int(np.sqrt(n_rows)))}, "
        f"settlement_window={settlement_window_days} days, "
        f"matched_anomaly_fee={matched_fee_rate:.4f}, "
        f"matched_anomaly_delay={matched_delay_days} days"
    )
    print(f"  Bucket breakdown:\n{gt_df['bucket'].value_counts().to_string()}")
    print(f"  Written: {ledger_path}, {bank_path}, {gt_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Recalce synthetic datasets")
    parser.add_argument("--split", choices=["train", "test"], default="train")
    parser.add_argument("--seed",  type=int, default=42)
    parser.add_argument("--rows",  type=int, default=5000)
    args = parser.parse_args()

    generate(split=args.split, seed=args.seed, n_rows=args.rows)
