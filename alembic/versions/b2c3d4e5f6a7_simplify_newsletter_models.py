"""simplify newsletter models: drop facts and optional columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-09-25 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop LetterFact table if exists
    op.drop_table('facts', schema='letters')

    # Drop unused columns from letters.batches
    for col in ['language', 'country', 'size', 'model', 'status']:
        try:
            op.drop_column('batches', col, schema='letters')
        except Exception:
            pass

    # Drop unused columns from letters.items
    drop_cols = [
        ('language', False),
        ('country', False),
        ('source', False),
        ('llm_status', True),  # index exists
    ]
    for col, has_index in drop_cols:
        if has_index:
            try:
                op.drop_index(f'ix_letters_items_{col}', table_name='items', schema='letters')
            except Exception:
                pass
        try:
            op.drop_column('items', col, schema='letters')
        except Exception:
            pass

    # Drop outline metadata columns
    for col in ['model', 'prompt_version', 'tokens_input', 'tokens_output']:
        try:
            op.drop_column('outlines', col, schema='letters')
        except Exception:
            pass


def downgrade() -> None:
    # Recreate dropped columns minimally (types only); data won't be restored
    op.add_column('batches', sa.Column('language', sa.String(length=10), nullable=True), schema='letters')
    op.add_column('batches', sa.Column('country', sa.String(length=5), nullable=True), schema='letters')
    op.add_column('batches', sa.Column('size', sa.Integer(), nullable=True), schema='letters')
    op.add_column('batches', sa.Column('model', sa.String(length=100), nullable=True), schema='letters')
    op.add_column('batches', sa.Column('status', sa.String(length=20), nullable=True), schema='letters')

    op.add_column('items', sa.Column('language', sa.String(length=10), nullable=True), schema='letters')
    op.add_column('items', sa.Column('country', sa.String(length=5), nullable=True), schema='letters')
    op.add_column('items', sa.Column('source', sa.String(length=32), nullable=True), schema='letters')
    op.add_column('items', sa.Column('llm_status', sa.String(length=20), nullable=True), schema='letters')
    op.create_index('ix_letters_items_llm_status', 'items', ['llm_status'], unique=False, schema='letters')

    op.add_column('outlines', sa.Column('model', sa.String(length=100), nullable=True), schema='letters')
    op.add_column('outlines', sa.Column('prompt_version', sa.String(length=50), nullable=True), schema='letters')
    op.add_column('outlines', sa.Column('tokens_input', sa.Integer(), nullable=True), schema='letters')
    op.add_column('outlines', sa.Column('tokens_output', sa.Integer(), nullable=True), schema='letters')

    # Recreate facts table (structure only)
    op.create_table(
        'facts',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('item_id', sa.BigInteger(), sa.ForeignKey('letters.items.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('facts', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        schema='letters'
    )
