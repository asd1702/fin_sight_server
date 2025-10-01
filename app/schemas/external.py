from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

class NaverNewsItemSchema(BaseModel):
    """
    네이버 뉴스 API 응답의 유효성 검사를 위한 Pydantic 스키마
    """
    title: str
    originallink: HttpUrl = Field(alias='link')
    description: str
    pubDate: str

class NewsDataItemSchema(BaseModel):
    """
    NEWS_DATA_API 응답의 유효성 검사를 위한 Pydantic 스키마
    """
    title: str
    url: HttpUrl = Field(alias='link')
    description: Optional[str] = None
    pubDate: Optional[str] = None