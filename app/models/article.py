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
    sentences = relationship("ArticleSentence", back_populates="article", cascade="all, delete-orphan")
    enriched = relationship("EnrichedArticle", uselist=False, back_populates="article", cascade="all, delete-orphan")
    terms = relationship("ArticleTermMapping", back_populates="article", cascade="all, delete-orphan")

class ArticleContent(Base):
    __tablename__ = "article_contents"
    id = Column(BigInteger, primary_key=True)
    article_id = Column(BigInteger, ForeignKey("articles.id"), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    article = relationship("Article", back_populates="content")

class ArticleSentence(Base):
    __tablename__ = "article_sentences"
    id = Column(BigInteger, primary_key=True)
    article_id = Column(BigInteger, ForeignKey("articles.id"), index=True, nullable=False)
    idx = Column(Integer, nullable=False)
    sentence = Column(Text, nullable=False)
    embedding = Column(Vector(1536))
    article = relationship("Article", back_populates="sentences")

class EnrichedArticle(Base):
    __tablename__ = "enriched_articles"
    id = Column(BigInteger, primary_key=True)
    article_id = Column(BigInteger, ForeignKey("articles.id"), unique=True, nullable=False)
    background = Column(JSONB)
    keywords = Column(JSONB)
    category = Column(String(50), nullable=False)
    article = relationship("Article", back_populates="enriched")