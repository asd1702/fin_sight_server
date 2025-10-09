"""merge branches to unify multiple heads

Revision ID: merge_heads_20251009
Revises: 20251001_add_indicator_state, add_soft_delete_20251009
Create Date: 2025-10-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'merge_heads_20251009'
down_revision: Union[str, tuple[str, ...], None] = ('20251001_add_indicator_state', 'add_soft_delete_20251009')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge revision; no schema changes.
    pass


def downgrade() -> None:
    # Can't un-merge; no-op.
    pass
