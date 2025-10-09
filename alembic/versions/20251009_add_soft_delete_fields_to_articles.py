"""add soft delete fields to articles

Revision ID: add_soft_delete_20251009
Revises: f7a8c9d0e1ab_add_letters_schema_and_tables
Create Date: 2025-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_soft_delete_20251009'
down_revision = 'f7a8c9d0e1ab'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')), schema='articles')
    op.add_column('articles', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True), schema='articles')
    op.add_column('articles', sa.Column('deleted_by', sa.String(length=100), nullable=True), schema='articles')
    op.add_column('articles', sa.Column('delete_reason', sa.Text(), nullable=True), schema='articles')
    op.add_column('articles', sa.Column('delete_lock_until', sa.DateTime(timezone=True), nullable=True), schema='articles')
    op.create_index('ix_articles_is_deleted', 'articles', ['is_deleted'], unique=False, schema='articles')
    op.create_index('ix_articles_delete_lock_until', 'articles', ['delete_lock_until'], unique=False, schema='articles')


def downgrade() -> None:
    op.drop_index('ix_articles_delete_lock_until', table_name='articles', schema='articles')
    op.drop_index('ix_articles_is_deleted', table_name='articles', schema='articles')
    op.drop_column('articles', 'delete_lock_until', schema='articles')
    op.drop_column('articles', 'delete_reason', schema='articles')
    op.drop_column('articles', 'deleted_by', schema='articles')
    op.drop_column('articles', 'deleted_at', schema='articles')
    op.drop_column('articles', 'is_deleted', schema='articles')
