"""Add images column to article_contents

Revision ID: add_images_col
Revises: be06d2857cf1
Create Date: 2025-09-10 01:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_images_col'
down_revision: Union[str, None] = 'be06d2857cf1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL connection을 통해 컬럼 존재 여부 확인
    conn = op.get_bind()
    
    # images 컬럼 존재 여부 확인
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'articles' 
        AND table_name = 'article_contents' 
        AND column_name = 'images'
    """))
    
    if not result.fetchone():
        op.add_column('article_contents', sa.Column('images', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='articles')


def downgrade() -> None:
    op.drop_column('article_contents', 'images', schema='articles')
