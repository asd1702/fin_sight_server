"""Add hashtags to enriched_articles

Revision ID: ccddeeff0011
Revises: 17e63d07e08d
Create Date: 2025-09-17 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ccddeeff0011'
down_revision: Union[str, None] = '17e63d07e08d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'articles' 
          AND table_name = 'enriched_articles' 
          AND column_name = 'hashtags'
    """))
    if not result.fetchone():
        op.add_column('enriched_articles', sa.Column('hashtags', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='articles')


def downgrade() -> None:
    op.drop_column('enriched_articles', 'hashtags', schema='articles')
