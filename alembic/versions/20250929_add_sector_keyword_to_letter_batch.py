"""add sector & key_word columns to letters.batches

Revision ID: add_sector_keyword_20250929
Revises: <PUT_PREVIOUS_REVISION_ID>
Create Date: 2025-09-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_sector_keyword_20250929'
# Set this to the latest current head before this migration; guessing previous custom newsletter change
down_revision = 'c3d4e5f6a7b8'  # adjust if Alembic reports a different head
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 새 컬럼 추가 (nullable 임시 추가 후 데이터 백필 → NOT NULL 제약 강화)
    op.add_column('batches', sa.Column('sector', sa.String(length=50), nullable=True), schema='letters')
    op.add_column('batches', sa.Column('key_word', sa.String(length=255), nullable=True), schema='letters')

    # 2. 기존 company 값 백필 -> key_word, sector 기본값 'company'
    # (company 컬럼이 존재할 것을 전제로 함)
    op.execute("UPDATE letters.batches SET sector='company', key_word=LOWER(REGEXP_REPLACE(TRIM(company), '[^0-9A-Za-z]+', '_', 'g')) WHERE company IS NOT NULL")

    # 3. NOT NULL 제약 설정
    op.alter_column('batches', 'sector', nullable=False, schema='letters')
    op.alter_column('batches', 'key_word', nullable=False, schema='letters')

    # 4. 인덱스 생성
    op.create_index('ix_letters_batches_sector', 'batches', ['sector'], unique=False, schema='letters')
    op.create_index('ix_letters_batches_key_word', 'batches', ['key_word'], unique=False, schema='letters')
    op.create_index('ix_letters_batches_sector_keyword_created_at', 'batches', ['sector', 'key_word', 'created_at'], unique=False, schema='letters')

    # (선택) 필요한 경우 company 컬럼을 제거하려면 아래 주석 해제
    # op.drop_column('batches', 'company', schema='letters')


def downgrade() -> None:
    # 롤백 시 컬럼 제거 (company 컬럼은 남겨두었다고 가정)
    op.drop_index('ix_letters_batches_sector_keyword_created_at', table_name='batches', schema='letters')
    op.drop_index('ix_letters_batches_key_word', table_name='batches', schema='letters')
    op.drop_index('ix_letters_batches_sector', table_name='batches', schema='letters')
    op.drop_column('batches', 'key_word', schema='letters')
    op.drop_column('batches', 'sector', schema='letters')
