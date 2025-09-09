# models/article.py

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, BigInteger, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .base import Base
from .enums import ArticleStatus

class Article(Base):
    __tablename__ = "articles"
    id = Column(BigInteger, primary_key=True)
    title = Column(Text, nullable=False)
    url = Column(String(1024), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)

    published_at = Column(DateTime(timezone=True))
    category = Column(String(50), nullable=True, index=True)
    status = Column(Enum(ArticleStatus), nullable=False, default=ArticleStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    content = relationship("ArticleContent", uselist=False, back_populates="article", cascade="all, delete-orphan")
    enriched = relationship("EnrichedArticle", uselist=False, back_populates="article", cascade="all, delete-orphan")

    __table_args__ = {'schema': 'articles'}

class ArticleContent(Base):
    __tablename__ = "article_contents"
    id = Column(BigInteger, primary_key=True)
    article_id = Column(BigInteger, ForeignKey("articles.articles.id"), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    images = Column(JSONB, nullable=True)  # 이미지 URL 목록 저장
    article = relationship("Article", back_populates="content")

    __table_args__ = {'schema': 'articles'}

class EnrichedArticle(Base):
    __tablename__ = "enriched_articles"
    id = Column(BigInteger, primary_key=True)
    article_id = Column(BigInteger, ForeignKey("articles.articles.id"), unique=True, nullable=False)
    background = Column(JSONB)
    keywords = Column(JSONB)
    category = Column(String(50), nullable=False)
    
    related_statistics = Column(JSONB, nullable=True)
    statistics_data = Column(JSONB, nullable=True)

    article = relationship("Article", back_populates="enriched")

    __table_args__ = {'schema': 'articles'}