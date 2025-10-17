"""
뉴스레터(레터) 도메인 모델 정의

LetterBatch, LetterItem, LetterOutline은 레터 생성 파이프라인에서
사용되는 핵심 엔터티입니다. 각 모델은 'letters' 스키마에 저장됩니다.
"""

from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class LetterBatch(Base):
    """레터 생성의 배치 단위 엔터티.

    sector와 key_word로 배치가 식별되며, 각 배치에는 여러 LetterItem과
    단일 LetterOutline(최종 초안)이 연결됩니다.
    """
    __tablename__ = "batches"

    id = Column(BigInteger, primary_key=True)
    sector = Column(String(50), nullable=False, index=True)  # 예: company, macro, market, tech
    key_word = Column(String(255), nullable=False, index=True)  # 예: nvidia, us_economy, snp500
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 생성 시각

    # 관계: 배치에 속한 기사(여러 개)
    items = relationship("LetterItem", back_populates="batch", cascade="all, delete-orphan")
    # 관계: 배치의 최종 아웃라인(1:1)
    outline = relationship("LetterOutline", back_populates="batch", uselist=False, cascade="all, delete-orphan")

    __table_args__ = {"schema": "letters"}


class LetterItem(Base):
    """배치에 포함된 개별 기사(임시 메타/본문 보관).

    외부 API 재호출을 막기 위해 메타를 보존하고, LLM 분석이 실패했을 때
    재시도할 수 있도록 본문을 임시로 저장합니다.
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
    """배치 단위 최종 아웃라인 JSON과 메타데이터를 저장."""
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