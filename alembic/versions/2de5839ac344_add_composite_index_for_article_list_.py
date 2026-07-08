"""add composite index for article list ordering

Revision ID: 2de5839ac344
Revises: replace_trgm_bigm_20251010
Create Date: 2026-07-08 17:12:27.737411

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2de5839ac344'
down_revision: Union[str, None] = 'replace_trgm_bigm_20251010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_list "
        "ON articles.articles (status, is_deleted, published_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_category_list "
        "ON articles.articles (status, is_deleted, category, published_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS articles.idx_articles_category_list")
    op.execute("DROP INDEX IF EXISTS articles.idx_articles_list")
