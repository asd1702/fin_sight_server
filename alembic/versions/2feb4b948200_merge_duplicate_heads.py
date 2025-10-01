"""Merge duplicate heads

Revision ID: 2feb4b948200
Revises: a194b75c5d8c, add_images_col
Create Date: 2025-09-11 22:20:32.093115

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2feb4b948200'
down_revision: Union[str, None] = ('a194b75c5d8c', 'add_images_col')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
