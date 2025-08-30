from pydantic import BaseModel, HttpUrl, ValidationError

class NaverNewsItemSchema(BaseModel):
    """
    네이버 뉴스 API 응답의 유효성 검사를 위한 Pydantic 스키마
    """
    title: str
    originallink: HttpUrl
    description: str
    pubDate: str