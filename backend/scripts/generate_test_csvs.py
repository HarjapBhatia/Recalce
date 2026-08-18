"""Generate CSV fixtures for testing the Recalce upload and matching flow.

The generated files are:
    internal_ledger_test.csv
    bank_statement_test.csv

Usage:
    python generate_test_csvs.py
    python backend/scripts/generate_test_csvs.py --rows 5000 --seed 42 --output-dir backend/tests/fixtures

The default data deliberately includes exact matches, settlement-date shifts,
fee-adjusted deposits, and ledger rows with no bank counterpart. It also
generates many-to-one groups (multiple ledger rows for a single bank deposit)
and intentionally ambiguous subset sum cases.

Both files use the upload schemas documented in ``context/03_backend_validation_guide.md``.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


MAX_ROWS_PER_UPLOAD = 50_000
DEFAULT_ROWS = 1_000
DEFAULT_SEED = 42
SETTLEMENT_WINDOW_DAYS = 3
FEE_MIN = Decimal("0.01")
FEE_MAX = Decimal("0.03")

# N:1 settings
DEFAULT_GROUP_SHARE = 0.15      # 15% of bank deposits are N:1 groups
DEFAULT_AMBIGUOUS_SHARE = 0.03  # 3% of bank deposits are ambiguous N:1 groups
MIN_GROUP_SIZE = 2
MAX_GROUP_SIZE = 6

LEDGER_FIELDS = ["transaction_id", "amount", "timestamp", "merchant_id"]
BANK_FIELDS = ["bank_reference_id", "deposit_amount", "settlement_date"]


def cents_to_amount(cents: int) -> str:
    """Convert integer cents to a two-decimal string without using floats."""
    return format(Decimal(cents) / Decimal("100"), ".2f")


def make_transaction_id(number: int) -> str:
    return f"TXN{number:06d}"

def make_batch_reference(number: int) -> str:
    return f"BATCH-{number:06d}"

def generate_rows(row_count: int, seed: int, group_share: float, ambiguous_share: float) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Build valid ledger and bank rows with predictable reconciliation cases."""
    rng = random.Random(seed)
    start = datetime(2024, 1, 15, 9, 0, 0)
    ledger_rows: list[dict[str, str]] = []
    bank_rows: list[dict[str, str]] = []

    case_weights = {
        "exact": 70.0 * (1.0 - group_share - ambiguous_share) / 0.85,
        "date_shift": 15.0 * (1.0 - group_share - ambiguous_share) / 0.85,
        "fee_adjusted": 10.0 * (1.0 - group_share - ambiguous_share) / 0.85,
        "missing": 5.0 * (1.0 - group_share - ambiguous_share) / 0.85,
        "group": group_share * 100,
        "ambiguous": ambiguous_share * 100,
    }
    cases = list(case_weights.keys())
    weights = list(case_weights.values())

    internal_number = 1
    bank_number = 1

    while internal_number <= row_count:
        case = rng.choices(cases, weights=weights, k=1)[0]

        # Determine group size (1 for non-groups)
        size = 1
        if case in ("group", "ambiguous"):
            size = rng.randint(MIN_GROUP_SIZE, MAX_GROUP_SIZE)

        if internal_number + size - 1 > row_count:
            # Not enough room for a group, force exact
            size = 1
            case = "exact"

        merchant_id = f"MERCH_{((bank_number - 1) % 25) + 1:03d}"

        group_internal_cents = []
        group_timestamp = None

        # Generate internal rows
        for i in range(size):
            tx_id = make_transaction_id(internal_number)
            ts = start + timedelta(minutes=(internal_number - 1) * 17)
            if group_timestamp is None:
                group_timestamp = ts
            # Ensure amounts are such that ambiguous sets can be formed if needed
            amt = rng.randint(1_000, 250_000)
            group_internal_cents.append(amt)

            ledger_rows.append({
                "transaction_id": tx_id,
                "amount": cents_to_amount(amt),
                "timestamp": ts.isoformat(sep=" "),
                "merchant_id": merchant_id,
            })
            internal_number += 1

        if case == "missing":
            continue

        total_cents = sum(group_internal_cents)
        deposit_cents = total_cents
        settlement_date = group_timestamp.date()

        if case == "date_shift":
            settlement_date += timedelta(days=rng.randint(1, SETTLEMENT_WINDOW_DAYS))
        elif case == "fee_adjusted":
            fee_rate = FEE_MIN + (FEE_MAX - FEE_MIN) * Decimal(str(rng.random()))
            fee_cents = int((Decimal(total_cents) * fee_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            deposit_cents = max(1, total_cents - fee_cents)
        elif case in ("group", "ambiguous"):
            # Include merchant id in bank reference for RapidFuzz to pick up
            bank_ref = f"{make_batch_reference(bank_number)}_{merchant_id}"

            # Groups might have fee adjustment too
            if rng.random() < 0.2:
                fee_rate = FEE_MIN + (FEE_MAX - FEE_MIN) * Decimal(str(rng.random()))
                fee_cents = int((Decimal(total_cents) * fee_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                deposit_cents = max(1, total_cents - fee_cents)

            if case == "ambiguous":
                # To make it ambiguous, we need another subset to sum to the same total.
                # We can just add another internal row that perfectly matches one of the combinations,
                # or add two rows that sum to one of the rows.
                # The easiest way: generate a pair of rows that sum to the same deposit,
                # but under the same merchant. This forces multiple combinations.

                # We'll just append one large row that exactly equals the total deposit_cents!
                tx_id = make_transaction_id(internal_number)
                ts = group_timestamp + timedelta(minutes=5)
                ledger_rows.append({
                    "transaction_id": tx_id,
                    "amount": cents_to_amount(deposit_cents), # This one row matches the deposit exactly
                    "timestamp": ts.isoformat(sep=" "),
                    "merchant_id": merchant_id,
                })
                internal_number += 1

        if case not in ("group", "ambiguous"):
            bank_ref = make_transaction_id(internal_number - 1)

        bank_rows.append({
            "bank_reference_id": bank_ref,
            "deposit_amount": cents_to_amount(deposit_cents),
            "settlement_date": settlement_date.isoformat(),
        })

        bank_number += 1

    return ledger_rows, bank_rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate_test_csvs(row_count: int, seed: int, group_share: float, ambiguous_share: float, output_dir: Path) -> tuple[Path, Path]:
    if not 1 <= row_count <= MAX_ROWS_PER_UPLOAD:
        raise ValueError(
            f"--rows must be between 1 and {MAX_ROWS_PER_UPLOAD:,}; got {row_count:,}."
        )

    ledger_rows, bank_rows = generate_rows(row_count, seed, group_share, ambiguous_share)
    if len(ledger_rows) > MAX_ROWS_PER_UPLOAD or len(bank_rows) > MAX_ROWS_PER_UPLOAD:
        raise ValueError("Generated CSV exceeds the 50,000-row upload limit.")

    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "internal_ledger_test.csv"
    bank_path = output_dir / "bank_statement_test.csv"
    write_csv(ledger_path, LEDGER_FIELDS, ledger_rows)
    write_csv(bank_path, BANK_FIELDS, bank_rows)
    return ledger_path, bank_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="Ledger rows (max 50,000).")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for repeatable data.")
    parser.add_argument("--group-share", type=float, default=DEFAULT_GROUP_SHARE, help="Fraction of rows to be Many-to-One groups.")
    parser.add_argument("--ambiguous-share", type=float, default=DEFAULT_AMBIGUOUS_SHARE, help="Fraction of rows to be ambiguous N:1 matches.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for the two generated CSVs (default: current directory).",
    )
    args = parser.parse_args()

    ledger_path, bank_path = generate_test_csvs(args.rows, args.seed, args.group_share, args.ambiguous_share, args.output_dir)
    print(f"Generated {ledger_path}")
    print(f"Generated {bank_path}")


if __name__ == "__main__":
    main()
