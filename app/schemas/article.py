from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Optional

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

# --- 기사 상세 정보에 사용될 전체 정보 스키마 ---
class ArticleDetailSchema(ArticleSimpleSchema):
    model_config = ConfigDict(from_attributes=True)
    
    url: str
    background: Optional[str] = None
    keywords: List[KeywordSchema] = []
