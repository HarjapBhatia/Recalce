"""Add processing timestamps and unreconciled_reason

Revision ID: c3f7a821b9e1
Revises: 1a4820b64a2a
Create Date: 2026-08-30 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f7a821b9e1'
down_revision: Union[str, None] = '1a4820b64a2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add processing timestamp columns to reconciliation_batches
    op.add_column(
        'reconciliation_batches',
        sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'reconciliation_batches',
        sa.Column('processing_completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Add unreconciled_reason column to reconciliation_results
    op.add_column(
        'reconciliation_results',
        sa.Column('unreconciled_reason', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('reconciliation_results', 'unreconciled_reason')
    op.drop_column('reconciliation_batches', 'processing_completed_at')
    op.drop_column('reconciliation_batches', 'processing_started_at')
