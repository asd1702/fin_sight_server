from sqlalchemy import Column, String, Date, DateTime, BigInteger, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.models.base import Base
from sqlalchemy.sql import func


class IndicatorState(Base):
    """각 지표의 마지막 적재 상태(증분 수집 커서)를 저장"""
    __tablename__ = 'indicator_state'
    __table_args__ = {'schema': 'statistics'}

    indicator_id = Column(String(50), primary_key=True)
    last_loaded_date = Column(Date, nullable=True)
    total_rows = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IngestionRun(Base):
    """ECOS 지표 일괄 수집 실행(run) 메타데이터"""
    __tablename__ = 'ingestion_runs'
    __table_args__ = {'schema': 'statistics'}

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default='STARTED')  # STARTED / SUCCESS / PARTIAL / FAILED
    incremental_from = Column(Date, nullable=True)
    incremental_to = Column(Date, nullable=True)
    indicators_processed = Column(Integer, nullable=True)
    rows_inserted = Column(BigInteger, nullable=True)
    rows_updated = Column(BigInteger, nullable=True)
    rows_skipped = Column(BigInteger, nullable=True)
    error_count = Column(Integer, nullable=True)
    message = Column(Text, nullable=True)