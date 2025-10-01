"""add letters schema and newsletter tables

Revision ID: f7a8c9d0e1ab
Revises: e1a2b3c4d5f6
Create Date: 2025-09-25 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f7a8c9d0e1ab'
down_revision: Union[str, None] = 'e1a2b3c4d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute("CREATE SCHEMA IF NOT EXISTS letters")

    op.create_table(
        'batches',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('company', sa.String(length=255), nullable=False, index=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('country', sa.String(length=5), nullable=True),
        sa.Column('size', sa.Integer(), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        schema='letters'
    )

    op.create_table(
        'items',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('batch_id', sa.BigInteger(), sa.ForeignKey('letters.batches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('url', sa.String(length=1024), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('country', sa.String(length=5), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('batch_id', 'url', name='uq_letter_item_batch_url'),
        schema='letters'
    )

    op.create_table(
        'facts',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('item_id', sa.BigInteger(), sa.ForeignKey('letters.items.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('facts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        schema='letters'
    )

    op.create_table(
        'outlines',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('batch_id', sa.BigInteger(), sa.ForeignKey('letters.batches.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('outline', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('prompt_version', sa.String(length=50), nullable=True),
        sa.Column('tokens_input', sa.Integer(), nullable=True),
        sa.Column('tokens_output', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        schema='letters'
    )


def downgrade() -> None:
    op.drop_table('outlines', schema='letters')
    op.drop_table('facts', schema='letters')
    op.drop_table('items', schema='letters')
    op.drop_table('batches', schema='letters')
    # 스키마는 유지(다른 객체가 있을 수 있음)
