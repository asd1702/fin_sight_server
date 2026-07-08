"""replace pg_trgm with pg_bigm functional indexes for korean search

Revision ID: replace_trgm_bigm_20251010
Revises: merge_heads_20251009
Create Date: 2025-10-10
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'replace_trgm_bigm_20251010'
down_revision: Union[str, None] = 'merge_heads_20251009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_bigm")

    op.execute("DROP INDEX IF EXISTS articles.idx_articles_title_trgm")
    op.execute("DROP INDEX IF EXISTS articles.idx_articles_desc_trgm")

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_articles_title_bigm_lower
        ON articles.articles USING gin (lower(title) gin_bigm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_articles_desc_bigm_lower
        ON articles.articles USING gin (lower(description) gin_bigm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS articles.idx_articles_title_bigm_lower")
    op.execute("DROP INDEX IF EXISTS articles.idx_articles_desc_bigm_lower")

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_articles_title_trgm
        ON articles.articles USING gin (title gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_articles_desc_trgm
        ON articles.articles USING gin (description gin_trgm_ops)
        """
    )
