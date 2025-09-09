from sqlalchemy import (Column, String, Text, Date, Float,
                        ForeignKey, PrimaryKeyConstraint)
from sqlalchemy.orm import relationship
from app.models.base import Base

class Indicator(Base):
    """
    경제 통계 지표의 메타데이터를 저장하는 테이블.
    """
    __tablename__ = 'indicators'

    # 고유 ID (비즈니스 로직용)
    indicator_id = Column(String(50), primary_key=True)
    
    # 지표 정보
    name = Column(Text, nullable=False)
    frequency = Column(String(10))
    unit = Column(String(50))
    source = Column(String(50))
    notes = Column(Text)

    # 원본 소스(ECOS)의 식별 코드
    stat_code = Column(String(20))
    item_code1 = Column(String(20))
    item_code2 = Column(String(20))
    item_code3 = Column(String(20))
    item_code4 = Column(String(20))
    
    # 'statistics' 스키마에 속함을 명시
    __table_args__ = {'schema': 'statistics'}
    
    # IndicatorData와의 관계 설정 (하나의 지표는 여러 개의 데이터 포인트를 가짐)
    observations = relationship("Observation", back_populates="indicator")


class Observation(Base):
    """
    각 경제 통계 지표의 시계열 데이터를 저장하는 테이블.
    """
    __tablename__ = 'observations'

    # Indicator 테이블의 indicator_id를 참조하는 외래 키
    indicator_id = Column(String(50), ForeignKey('statistics.indicators.indicator_id'), nullable=False)
    date = Column(Date, nullable=False)
    value = Column(Float, nullable=False)

    # 'statistics' 스키마에 속함을 명시
    # (indicator_id, date)를 복합 기본 키로 설정하여 데이터 무결성 보장
    __table_args__ = (
        PrimaryKeyConstraint('indicator_id', 'date'),
        {'schema': 'statistics'}
    )

    # Indicator와의 관계 설정
    indicator = relationship("Indicator", back_populates="observations")
