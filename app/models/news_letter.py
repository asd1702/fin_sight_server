from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class LetterBatch(Base):
        """뉴스/테마/기업 단위 묶음 생성 배치
        단순화된 필수 필드만 유지:
            - sector: 'company' | 'macro' | 'market' | 'tech' 등 영문 카테고리
            - key_word: 검색 키워드 또는 고정 토픽 식별자 (소문자/slug 권장)
            - created_at

        기존 company 필드는 key_word로 개념 전환되므로 마이그레이션에서 컬럼 rename / 또는 신규 추가 후 백필.
        """
        __tablename__ = "batches"

        id = Column(BigInteger, primary_key=True)
        sector = Column(String(50), nullable=False, index=True)            # 예: company, macro, market, tech
        key_word = Column(String(255), nullable=False, index=True)         # 예: nvidia, us_economy, snp500
        created_at = Column(DateTime(timezone=True), server_default=func.now())  # 생성 시각

        items = relationship("LetterItem", back_populates="batch", cascade="all, delete-orphan")  # 배치 하위 기사 목록
        outline = relationship("LetterOutline", back_populates="batch", uselist=False, cascade="all, delete-orphan")  # 배치 결과 아웃라인(1:1)

        __table_args__ = {
                "schema": "letters",
        }


class LetterItem(Base):
    """
    배치 내에 수집된 개별 기사(메타 + 임시 본문) 테이블
    - 목적: 외부 API 재호출 방지(메타 보존) + 크롤링 본문 임시 저장(LLM 실패 시 재시도 대비)
    - 최소 필드만 유지: URL, 제목/요약(옵션), 본문 임시 저장, 크롤링 상태, 오류, TTL
    """
    __tablename__ = "items"

    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey("letters.batches.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(Text, nullable=True)  # 기사 제목(크롤링 시 업데이트 가능)
    url = Column(String(1024), nullable=True)  # 기사 URL(배치 내 유니크)
    description = Column(Text, nullable=True)  # 기사 요약
    published_at = Column(DateTime(timezone=True), nullable=True)  # 기사 게시 시각(옵션)
    content = Column(Text, nullable=True)  # 크롤링한 본문(임시 보관)

    # 처리 상태(기사 단위)
    crawl_status = Column(String(20), nullable=True, index=True)  # PENDING/CRAWLING/CRAWLED/FAILED

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 생성 시각
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())  # 갱신 시각
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)  # TTL 기준 시각

    batch = relationship("LetterBatch", back_populates="items")

    __table_args__ = (
        UniqueConstraint("batch_id", "url", name="uq_letter_item_batch_url"),  # 동일 배치 내 중복 URL 방지
        {"schema": "letters"},
    )

class LetterOutline(Base):
    """
    배치 단위 최종 칼럼 아웃라인(JSON) 테이블
    - 최소 필드만 유지: 배치 FK, outline JSON, 생성 시각
    """
    __tablename__ = "outlines"

    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey("letters.batches.id", ondelete="CASCADE"), nullable=False, unique=True)
    outline = Column(JSONB, nullable=False)  # 에디터가 사용하는 최종 JSON
    # --- 확장 메타데이터 ---
    status = Column(String(20), nullable=False, server_default='completed', index=True)  # draft|processing|delivered|completed|failed
    outline_version = Column(Integer, nullable=False, server_default='1')  # outline schema/content 버전 관리
    prompt_key = Column(String(100), nullable=True, index=True)  # 사용된 프롬프트 키(토픽)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)  # 외부 배포(게시) 시각
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 생성 시각

    batch = relationship("LetterBatch", back_populates="outline")

    __table_args__ = {"schema": "letters"}