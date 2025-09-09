from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Optional, Dict, Any

# --- 키워드 응답 형식을 위한 스키마 ---
class KeywordSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    term: str
    summary: Optional[str] = None

# --- 기사 목록에 사용될 간단한 정보 스키마 ---
class ArticleSimpleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    published_at: datetime

# --- 통계 지표 응답 형식을 위한 스키마 ---
class StatisticIndicatorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    indicator_id: str
    name: str
    description: Optional[str] = None

class StatisticDataSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    date: str
    value: float
    indicator_id: str

# --- 기사 상세 정보에 사용될 전체 정보 스키마 ---
class ArticleDetailSchema(ArticleSimpleSchema):
    model_config = ConfigDict(from_attributes=True)
    
    url: str
    background: Optional[dict] = None  # JSONB 필드이므로 dict 타입으로 변경
    keywords: Optional[list] = []  # JSONB 필드이므로 list 타입으로 변경
    related_statistics: Optional[list] = []  # 새로 추가된 필드
    statistics_data: Optional[list] = []  # 새로 추가된 필드
    images: Optional[list] = []  # 이미지 URL 목록
