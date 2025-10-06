"""add indicator_state and ingestion_runs tables

Revision ID: 20251001_add_indicator_state
Revises: add_outline_meta_20250930
Create Date: 2025-10-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20251001_add_indicator_state'
down_revision: Union[str, None] = 'add_outline_meta_20250930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'indicator_state',
        sa.Column('indicator_id', sa.String(length=50), nullable=False),
        sa.Column('last_loaded_date', sa.Date(), nullable=True),
        sa.Column('total_rows', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('indicator_id'),
        schema='statistics'
    )

    op.create_table(
        'ingestion_runs',
        sa.Column('run_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='STARTED'),
        sa.Column('incremental_from', sa.Date(), nullable=True),
        sa.Column('incremental_to', sa.Date(), nullable=True),
        sa.Column('indicators_processed', sa.Integer(), nullable=True),
        sa.Column('rows_inserted', sa.BigInteger(), nullable=True),
        sa.Column('rows_updated', sa.BigInteger(), nullable=True),
        sa.Column('rows_skipped', sa.BigInteger(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        schema='statistics'
    )


def downgrade() -> None:
    op.drop_table('ingestion_runs', schema='statistics')
    op.drop_table('indicator_state', schema='statistics')
