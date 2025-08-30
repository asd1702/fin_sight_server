from sqlalchemy import Column, Integer, Text, BigInteger, Float, ForeignKey, DateTime, func
from .base import Base
from sqlalchemy.orm import relationship

class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False, unique=True, index=True)
    articles = relationship("ArticleTermMapping", back_populates="topic")

class ArticleTermMapping(Base):
    __tablename__ = "article_term_mapping"
    article_id = Column(BigInteger, ForeignKey("articles.id"), primary_key=True)
    term_id = Column(Integer, ForeignKey("domain_terms.id"), primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), primary_key=True)
    similarity = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    article = relationship("Article", back_populates="terms")
    term = relationship("DomainTerm", back_populates="articles")
    topic = relationship("Topic", back_populates="articles")