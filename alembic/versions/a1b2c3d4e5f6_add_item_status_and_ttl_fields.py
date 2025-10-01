"""add item status and ttl fields

Revision ID: a1b2c3d4e5f6
Revises: f7a8c9d0e1ab
Create Date: 2025-09-25 10:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f7a8c9d0e1ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('items', sa.Column('crawl_status', sa.String(length=20), nullable=True), schema='letters')
    op.add_column('items', sa.Column('llm_status', sa.String(length=20), nullable=True), schema='letters')
    op.add_column('items', sa.Column('last_error', sa.Text(), nullable=True), schema='letters')
    op.add_column('items', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')), schema='letters')
    op.add_column('items', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True), schema='letters')

    op.create_index('ix_letters_items_crawl_status', 'items', ['crawl_status'], unique=False, schema='letters')
    op.create_index('ix_letters_items_llm_status', 'items', ['llm_status'], unique=False, schema='letters')
    op.create_index('ix_letters_items_expires_at', 'items', ['expires_at'], unique=False, schema='letters')


def downgrade() -> None:
    op.drop_index('ix_letters_items_expires_at', table_name='items', schema='letters')
    op.drop_index('ix_letters_items_llm_status', table_name='items', schema='letters')
    op.drop_index('ix_letters_items_crawl_status', table_name='items', schema='letters')

    op.drop_column('items', 'expires_at', schema='letters')
    op.drop_column('items', 'updated_at', schema='letters')
    op.drop_column('items', 'last_error', schema='letters')
    op.drop_column('items', 'llm_status', schema='letters')
    op.drop_column('items', 'crawl_status', schema='letters')
