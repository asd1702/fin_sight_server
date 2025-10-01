"""add outline metadata & status fields

Revision ID: add_outline_meta_20250930
Revises: drop_company_col_20250929
Create Date: 2025-09-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_outline_meta_20250930'
down_revision = 'drop_company_col_20250929'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns with nullable first where needed, then backfill / set defaults
    op.add_column('outlines', sa.Column('status', sa.String(length=20), nullable=True), schema='letters')
    op.add_column('outlines', sa.Column('outline_version', sa.Integer(), nullable=True), schema='letters')
    op.add_column('outlines', sa.Column('prompt_key', sa.String(length=100), nullable=True), schema='letters')
    op.add_column('outlines', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True), schema='letters')
    # Removed momentum_score/meta per simplification request

    # Backfill defaults
    op.execute("UPDATE letters.outlines SET status='completed' WHERE status IS NULL")
    op.execute("UPDATE letters.outlines SET outline_version=1 WHERE outline_version IS NULL")

    # Enforce NOT NULL on required columns
    op.alter_column('outlines', 'status', nullable=False, schema='letters')
    op.alter_column('outlines', 'outline_version', nullable=False, schema='letters')

    # Indexes
    op.create_index('ix_letters_outlines_status', 'outlines', ['status'], unique=False, schema='letters')
    op.create_index('ix_letters_outlines_prompt_key', 'outlines', ['prompt_key'], unique=False, schema='letters')
    op.create_index('ix_letters_outlines_published_at', 'outlines', ['published_at'], unique=False, schema='letters')


def downgrade() -> None:
    op.drop_index('ix_letters_outlines_published_at', table_name='outlines', schema='letters')
    op.drop_index('ix_letters_outlines_prompt_key', table_name='outlines', schema='letters')
    op.drop_index('ix_letters_outlines_status', table_name='outlines', schema='letters')
    # Removed columns (momentum_score, meta) never applied after simplification; nothing to drop.
    op.drop_column('outlines', 'published_at', schema='letters')
    op.drop_column('outlines', 'prompt_key', schema='letters')
    op.drop_column('outlines', 'outline_version', schema='letters')
    op.drop_column('outlines', 'status', schema='letters')
