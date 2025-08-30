from sqlalchemy import Column, Integer, String, Text, DateTime, func
from .base import Base
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

class DomainTerm(Base):
    __tablename__ = "domain_terms"
    id = Column(Integer, primary_key=True)
    term = Column(Text, nullable=False, unique=True, index=True)
    summary = Column(Text)
    definition = Column(Text)
    embedding = Column(Vector(1536))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    articles = relationship("ArticleTermMapping", back_populates="term", cascade="all, delete-orphan")