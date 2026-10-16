"""app/models package -- SQLAlchemy ORM models.

Importing this package eagerly registers every ORM model with the
declarative Base so that string-based relationship() references
(e.g. relationship("InternalLedger")) can be resolved at mapper
configuration time.
"""

from app.models.organization import Organization              # noqa: F401
from app.models.user import User, UserRole                   # noqa: F401
from app.models.internal_ledger import InternalLedger        # noqa: F401
from app.models.bank_statement import BankStatement          # noqa: F401
from app.models.reconciliation_batch import ReconciliationBatch  # noqa: F401
from app.models.reconciliation_result import (               # noqa: F401
    ReconciliationResult,
    BatchValidationError,
)

__all__ = [
    "Organization",
    "User",
    "UserRole",
    "InternalLedger",
    "BankStatement",
    "ReconciliationBatch",
    "ReconciliationResult",
    "BatchValidationError",
]
