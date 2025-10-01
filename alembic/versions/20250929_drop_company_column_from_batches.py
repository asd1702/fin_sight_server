"""Drop legacy company column from letters.batches now that sector/key_word are in use.

Revision ID: drop_company_col_20250929
Revises: add_sector_keyword_20250929
Create Date: 2025-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'drop_company_col_20250929'
down_revision = 'add_sector_keyword_20250929'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Make company nullable first (in case constraint blocks drop) then drop
    try:
        op.alter_column('batches', 'company', existing_type=sa.String(length=255), nullable=True, schema='letters')
    except Exception:
        pass
    try:
        op.drop_column('batches', 'company', schema='letters')
    except Exception:
        pass


def downgrade() -> None:
    # Recreate company column (empty data)
    try:
        op.add_column('batches', sa.Column('company', sa.String(length=255), nullable=True), schema='letters')
    except Exception:
        pass
