"""
app/db/base.py
--------------
Imports all ORM models so they register with the shared declarative Base.

Alembic's env.py and any code that needs all tables discoverable on
Base.metadata should import this module rather than importing individual
model files. This guarantees every table is visible to autogenerate.
"""

from app.db.session import Base  # noqa: F401

# Import every model class so its table is registered on Base.metadata.
# The order does not matter here -- SQLAlchemy resolves relationships lazily.
from app.models.reconciliation_batch import ReconciliationBatch  # noqa: F401
from app.models.internal_ledger import InternalLedger  # noqa: F401
from app.models.bank_statement import BankStatement  # noqa: F401
from app.models.reconciliation_result import (  # noqa: F401
    ReconciliationResult,
    BatchValidationError,
)
