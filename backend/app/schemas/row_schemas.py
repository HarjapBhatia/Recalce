"""
app/schemas/row_schemas.py
--------------------------
Pydantic models for validating individual CSV rows during ingestion.

Key rules (per IMPLEMENTATION_CONTEXT.md §7):
- amount: raw string → Decimal (never through float)
- timestamp: permissive parsing via python-dateutil
- extra columns: ignored (extra="ignore")
- Dirty values like "$52.00" or "52,00" are cleaned before parsing
"""

from decimal import Decimal, InvalidOperation
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator
from dateutil import parser as date_parser


class InternalLedgerRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    transaction_id: str
    amount:         Decimal
    timestamp:      datetime
    merchant_id:    str

    @field_validator("amount", mode="before")
    @classmethod
    def clean_amount(cls, value: object) -> Decimal:
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
        try:
            return Decimal(str(value))
        except InvalidOperation:
            raise ValueError(f"'{value}' is not a valid decimal amount")

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        try:
            return date_parser.parse(str(value))
        except (ValueError, TypeError):
            raise ValueError(f"'{value}' could not be parsed as a date or time")


class BankStatementRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bank_reference_id: str
    deposit_amount:    Decimal
    settlement_date:   datetime  # parsed to date in the ingestion task

    @field_validator("deposit_amount", mode="before")
    @classmethod
    def clean_deposit(cls, value: object) -> Decimal:
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
        try:
            return Decimal(str(value))
        except InvalidOperation:
            raise ValueError(f"'{value}' is not a valid decimal amount")

    @field_validator("settlement_date", mode="before")
    @classmethod
    def parse_date(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        try:
            return date_parser.parse(str(value))
        except (ValueError, TypeError):
            raise ValueError(f"'{value}' could not be parsed as a date")
