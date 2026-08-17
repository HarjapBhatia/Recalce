"""
tests/test_row_schemas.py
--------------------------
Unit tests for Pydantic CSV row validators.

These run without any DB or S3 — just pure schema validation logic.
"""

import pytest
from decimal import Decimal
from app.schemas.row_schemas import InternalLedgerRow, BankStatementRow


def test_clean_dollar_sign():
    row = InternalLedgerRow(
        transaction_id="TXN001",
        amount="$52.00",
        timestamp="2024-01-15T10:30:00",
        merchant_id="MER001",
    )
    assert row.amount == Decimal("52.00")


def test_clean_comma_amount():
    row = InternalLedgerRow(
        transaction_id="TXN002",
        amount="1,234.56",
        timestamp="2024-01-15",
        merchant_id="MER002",
    )
    assert row.amount == Decimal("1234.56")


def test_invalid_amount_raises():
    with pytest.raises(Exception):
        InternalLedgerRow(
            transaction_id="TXN003",
            amount="not-a-number",
            timestamp="2024-01-15",
            merchant_id="MER003",
        )


def test_extra_columns_ignored():
    row = InternalLedgerRow(
        transaction_id="TXN004",
        amount="100.00",
        timestamp="2024-01-15",
        merchant_id="MER004",
        unexpected_column="should be ignored",  # type: ignore[call-arg]
    )
    assert row.transaction_id == "TXN004"


def test_bank_statement_row():
    row = BankStatementRow(
        bank_reference_id="BANK001",
        deposit_amount="$99.99",
        settlement_date="2024-01-18",
    )
    assert row.deposit_amount == Decimal("99.99")
