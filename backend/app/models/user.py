"""
app/models/user.py

User - a platform user with one of three roles:
  SUPER_ADMIN  Platform owner with full system access.
  ADMIN        Organization administrator (co-admins supported).
  ANALYST      Financial analyst within an organization.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.reconciliation_batch import ReconciliationBatch


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    organization: Mapped["Organization | None"] = relationship(
        "Organization", back_populates="users"
    )
    created_batches: Mapped[list["ReconciliationBatch"]] = relationship(
        "ReconciliationBatch",
        back_populates="created_by",
        foreign_keys="ReconciliationBatch.created_by_user_id",
    )
    assigned_batches: Mapped[list["ReconciliationBatch"]] = relationship(
        "ReconciliationBatch",
        back_populates="assigned_analyst",
        foreign_keys="ReconciliationBatch.assigned_analyst_id",
    )
