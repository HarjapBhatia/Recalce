"""Add file content LargeBinary columns and make B2 file keys nullable

Revision ID: e4a8f3c21d7b
Revises: c3f7a821b9e1
Create Date: 2026-10-02 18:30:00.000000

Architecture simplification: store uploaded CSV bytes temporarily in the
database instead of Backblaze B2. The old B2 key columns are made nullable
(they were NOT NULL in the initial migration) so existing rows don't break.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a8f3c21d7b'
down_revision: Union[str, None] = 'c3f7a821b9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add temporary file content columns (LargeBinary, nullable)
    op.add_column(
        'reconciliation_batches',
        sa.Column('internal_file_content', sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        'reconciliation_batches',
        sa.Column('bank_file_content', sa.LargeBinary(), nullable=True),
    )

    # Make the legacy B2 file key columns nullable so new rows don't need them
    op.alter_column(
        'reconciliation_batches',
        'internal_file_key',
        existing_type=sa.String(),
        nullable=True,
    )
    op.alter_column(
        'reconciliation_batches',
        'bank_file_key',
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    # Restore NOT NULL on the file key columns
    op.alter_column(
        'reconciliation_batches',
        'bank_file_key',
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        'reconciliation_batches',
        'internal_file_key',
        existing_type=sa.String(),
        nullable=False,
    )

    # Drop the file content columns
    op.drop_column('reconciliation_batches', 'bank_file_content')
    op.drop_column('reconciliation_batches', 'internal_file_content')
