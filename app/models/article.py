"""
기사 관련 ORM 모델 정의

이 파일에는 기사(Article), 기사 본문(ArticleContent), 그리고
LLM으로부터 생성된 보강 정보(EnrichedArticle) 모델이 포함되어 있습니다.

스키마(schema)는 'articles'로 지정되어 있고, 관계는
1:1 형태(US = uselist=False)로 구성되어 있습니다
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, BigInteger, func, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .base import Base
from .enums import ArticleStatus


class Article(Base):
    """기사 메타데이터를 저장하는 메인 엔터티.

    주요 필드:
      - title, url, description, image_url
      - published_at: 기사 발행 시각(타임존 포함)
      - status: 처리 상태(ArticleStatus)
      - Soft delete 관련 필드(is_deleted, deleted_at 등)
      - hashtags: JSONB 배열로 저장된 해시태그 목록
    """
    __tablename__ = "articles"
    id = Column(BigInteger, primary_key=True)
    title = Column(Text, nullable=False)
    url = Column(String(1024), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(1024), nullable=True)

    published_at = Column(DateTime(timezone=True))
    category = Column(String(50), nullable=True, index=True)
    status = Column(Enum(ArticleStatus), nullable=False, default=ArticleStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Soft delete 관련 필드들
    is_deleted = Column(Boolean, nullable=False, server_default='false', index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String(100), nullable=True)
    delete_reason = Column(Text, nullable=True)
    delete_lock_until = Column(DateTime(timezone=True), nullable=True, index=True)

    # 해시태그를 JSONB 배열로 보관
    hashtags = Column(JSONB, nullable=True)

    # 관계 설정: Article -> ArticleContent(1:1), Article -> EnrichedArticle(1:1)
    content = relationship("ArticleContent", uselist=False, back_populates="article", cascade="all, delete-orphan")
    enriched = relationship("EnrichedArticle", uselist=False, back_populates="article", cascade="all, delete-orphan")

    __table_args__ = {'schema': 'articles'}


class ArticleContent(Base):
    """기사 본문과 이미지 목록을 저장하는 테이블."""
    __tablename__ = "article_contents"
    id = Column(BigInteger, primary_key=True)
    article_id = Column(BigInteger, ForeignKey("articles.articles.id"), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    images = Column(JSONB, nullable=True)  # 이미지 URL 목록 저장
    article = relationship("Article", back_populates="content")

    __table_args__ = {'schema': 'articles'}


class EnrichedArticle(Base):
    """LLM 분석 결과 및 보강 메타데이터를 저장하는 테이블."""
    __tablename__ = "enriched_articles"
    id = Column(BigInteger, primary_key=True)
    article_id = Column(BigInteger, ForeignKey("articles.articles.id"), unique=True, nullable=False)
    background = Column(JSONB)
    keywords = Column(JSONB)
    category = Column(String(50), nullable=False)

    # 관련 통계 및 가공된 시계열 데이터
    related_statistics = Column(JSONB, nullable=True)
    statistics_data = Column(JSONB, nullable=True)
    hashtags = Column(JSONB, nullable=True)

    article = relationship("Article", back_populates="enriched")

    __table_args__ = {'schema': 'articles'}