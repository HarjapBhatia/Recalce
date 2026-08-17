"""Generate CSV fixtures for testing the Recalce upload and matching flow.

The generated files are:
    internal_ledger_test.csv
    bank_statement_test.csv

Usage:
    python generate_test_csvs.py
    python backend/scripts/generate_test_csvs.py --rows 5000 --seed 42 --output-dir backend/tests/fixtures

The default data deliberately includes exact matches, settlement-date shifts,
fee-adjusted deposits, and ledger rows with no bank counterpart.  Both files
use the upload schemas documented in ``context/03_backend_validation_guide.md``.
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

LEDGER_FIELDS = ["transaction_id", "amount", "timestamp", "merchant_id"]
BANK_FIELDS = ["bank_reference_id", "deposit_amount", "settlement_date"]


def cents_to_amount(cents: int) -> str:
    """Convert integer cents to a two-decimal string without using floats."""
    return format(Decimal(cents) / Decimal("100"), ".2f")


def make_transaction_id(number: int) -> str:
    return f"TXN{number:06d}"


def generate_rows(row_count: int, seed: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Build valid ledger and bank rows with predictable reconciliation cases."""
    rng = random.Random(seed)
    start = datetime(2024, 1, 15, 9, 0, 0)
    ledger_rows: list[dict[str, str]] = []
    bank_rows: list[dict[str, str]] = []

    # Keep at least one example of every case, including for small test runs.
    case_order = ["exact", "date_shift", "fee_adjusted", "missing"]
    for number in range(1, row_count + 1):
        transaction_id = make_transaction_id(number)
        timestamp = start + timedelta(minutes=(number - 1) * 17)
        amount_cents = rng.randint(1_000, 250_000)
        merchant_id = f"MERCH_{((number - 1) % 25) + 1:03d}"

        ledger_rows.append(
            {
                "transaction_id": transaction_id,
                "amount": cents_to_amount(amount_cents),
                "timestamp": timestamp.isoformat(sep=" "),
                "merchant_id": merchant_id,
            }
        )

        if number <= len(case_order):
            case = case_order[number - 1]
        else:
            case = rng.choices(
                ["exact", "date_shift", "fee_adjusted", "missing"],
                weights=[70, 15, 10, 5],
                k=1,
            )[0]

        if case == "missing":
            continue

        deposit_cents = amount_cents
        settlement_date = timestamp.date()
        if case == "date_shift":
            settlement_date += timedelta(days=rng.randint(1, SETTLEMENT_WINDOW_DAYS))
        elif case == "fee_adjusted":
            fee_rate = FEE_MIN + (FEE_MAX - FEE_MIN) * Decimal(str(rng.random()))
            fee_cents = int(
                (Decimal(amount_cents) * fee_rate).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            deposit_cents = max(1, amount_cents - fee_cents)

        bank_rows.append(
            {
                "bank_reference_id": transaction_id,
                "deposit_amount": cents_to_amount(deposit_cents),
                "settlement_date": settlement_date.isoformat(),
            }
        )

    return ledger_rows, bank_rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate_test_csvs(row_count: int, seed: int, output_dir: Path) -> tuple[Path, Path]:
    if not 1 <= row_count <= MAX_ROWS_PER_UPLOAD:
        raise ValueError(
            f"--rows must be between 1 and {MAX_ROWS_PER_UPLOAD:,}; got {row_count:,}."
        )

    ledger_rows, bank_rows = generate_rows(row_count, seed)
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for the two generated CSVs (default: current directory).",
    )
    args = parser.parse_args()

    ledger_path, bank_path = generate_test_csvs(args.rows, args.seed, args.output_dir)
    print(f"Generated {ledger_path} ({args.rows:,} rows)")
    print(f"Generated {bank_path} (at most {args.rows:,} rows)")


if __name__ == "__main__":
    main()
