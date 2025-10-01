"""Add trigram and GIN indexes for search

Revision ID: e1a2b3c4d5f6
Revises: dd11ee22ff33
Create Date: 2025-09-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5f6'
down_revision: Union[str, None] = 'dd11ee22ff33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ctx = op.get_context()

    # Enable pg_trgm extension (needed for trigram indexes). Requires autocommit.
    with ctx.autocommit_block():
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Create trigram GIN indexes for title and description, and JSONB GIN for hashtags.
    # Use CONCURRENTLY to avoid long table locks; requires autocommit.
    with ctx.autocommit_block():
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_articles_title_trgm
            ON articles.articles USING GIN (title gin_trgm_ops)
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_articles_desc_trgm
            ON articles.articles USING GIN (description gin_trgm_ops)
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_articles_hashtags_gin
            ON articles.articles USING GIN (hashtags)
            """
        )


def downgrade() -> None:
    ctx = op.get_context()
    # Drop indexes if exist; trigram extension left in place (safe and may be used elsewhere)
    with ctx.autocommit_block():
        op.execute("DROP INDEX IF EXISTS articles.idx_articles_hashtags_gin")
        op.execute("DROP INDEX IF EXISTS articles.idx_articles_desc_trgm")
        op.execute("DROP INDEX IF EXISTS articles.idx_articles_title_trgm")
