from sqlalchemy import Column, String, Date, DateTime, BigInteger, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.models.base import Base
from sqlalchemy.sql import func


"""
statistics 스키마용 메타 테이블 정의

이 모듈은 수집(ingestion) 관련 메타데이터를 저장하기 위한 ORM 모델을 포함합니다:
- IndicatorState: 지표별 증분 수집 커서와 집계 정보 저장
- IngestionRun: 각 일괄 수집 실행에 대한 메타/통계 정보 저장
"""


class IndicatorState(Base):
        """
        지표별 증분 수집 상태 모델

        주요 필드:
            - indicator_id: 지표 키 (PK)
            - last_loaded_date: 마지막으로 성공적으로 적재된 날짜 (증분 수집 커서)
            - total_rows: 해당 지표로 적재된 총 행 수 (기본값 0)
            - updated_at: 레코드 생성/수정 시각 (자동)

        개발자 메모:
            - last_loaded_date를 이용해 다음 수집 시점의 증분 범위를 계산합니다.
            - total_rows는 단순 통계용이며, 정확한 카운트가 필요한 경우 별도 쿼리를 권장합니다.
        """
        __tablename__ = 'indicator_state'
        __table_args__ = {'schema': 'statistics'}

        # 지표 식별자 (예: 'gdp', 'unemployment_rate')
        indicator_id = Column(String(50), primary_key=True)
        # 마지막으로 정상적으로 적재된 날짜 (증분 수집 커서)
        last_loaded_date = Column(Date, nullable=True)
        # 이 지표에 대해 현재까지 적재된 총 행 수
        total_rows = Column(BigInteger, nullable=False, default=0)
        # 레코드 생성/수정 시각을 자동으로 관리
        updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IngestionRun(Base):
        """
        일괄 수집 실행(run) 메타데이터 모델

        주요 필드:
            - run_id: UUID PK
            - started_at / finished_at: 실행 시작/종료 시각
            - status: 실행 상태 ('STARTED', 'SUCCESS', 'PARTIAL', 'FAILED')
            - incremental_from / incremental_to: 이 실행에서 처리한 증분 기간
            - indicators_processed: 처리된 지표 수
            - rows_inserted/rows_updated/rows_skipped: DB 반영 행 수 통계
            - error_count: 에러 수
            - message: 간단한 실행 메시지/오류 요약

        개발자 메모:
            - status는 워크플로우 상태 추적용으로 사용됩니다. PARTIAL은 일부 실패가 발생한 경우에 사용하세요.
            - started_at은 기본값으로 자동 설정되며, finished_at은 실행 종료 시 수동 업데이트됩니다.
        """
        __tablename__ = 'ingestion_runs'
        __table_args__ = {'schema': 'statistics'}

        run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
        started_at = Column(DateTime(timezone=True), server_default=func.now())
        finished_at = Column(DateTime(timezone=True), nullable=True)
        status = Column(String(20), nullable=False, default='STARTED')  # 실행 상태: STARTED / SUCCESS / PARTIAL / FAILED
        incremental_from = Column(Date, nullable=True)
        incremental_to = Column(Date, nullable=True)
        indicators_processed = Column(Integer, nullable=True)
        rows_inserted = Column(BigInteger, nullable=True)
        rows_updated = Column(BigInteger, nullable=True)
        rows_skipped = Column(BigInteger, nullable=True)
        error_count = Column(Integer, nullable=True)
        message = Column(Text, nullable=True)