"""Add hashtags to articles table

Revision ID: dd11ee22ff33
Revises: ccddeeff0011
Create Date: 2025-09-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'dd11ee22ff33'
down_revision: Union[str, None] = 'ccddeeff0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # 안전하게 존재 여부 확인 후 추가
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'articles' 
          AND table_name = 'articles' 
          AND column_name = 'hashtags'
    """))
    if not result.fetchone():
        op.add_column('articles', sa.Column('hashtags', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='articles')


def downgrade() -> None:
    op.drop_column('articles', 'hashtags', schema='articles')
