from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json

from ..database import get_db
from ..models import Article, EnrichedArticle, ArticleStatus
from ..schemas.article import ArticleSimpleSchema, ArticleDetailSchema, KeywordSchema

router = APIRouter(
    prefix="/api/articles",
    tags=["articles"]
)

@router.get("/today", response_model=List[ArticleSimpleSchema])
def get_today_news(db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    """
    '오늘의 뉴스'를 위한 API
    """
    articles = db.query(Article)\
                .filter(Article.status == ArticleStatus.PROCESSED)\
                .order_by(Article.published_at.desc())\
                .offset(skip)\
                .limit(limit)\
                .all()
    return articles

@router.get("/category/{category}", response_model=List[ArticleSimpleSchema])
def get_news_by_category(category: str, db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    """
    카테고리별 뉴스 목록 반환
    """
    articles = db.query(Article)\
                .filter(Article.status == ArticleStatus.PROCESSED, Article.category == category)\
                .order_by(Article.published_at.desc())\
                .offset(skip)\
                .limit(limit)\
                .all()
    if not articles:
        raise HTTPException(status_code=404, detail=f"'{category}' 카테고리의 기사를 찾을 수 없습니다.")
    return articles

@router.get("/{article_id}", response_model=ArticleDetailSchema)
def get_article_detail(article_id: int, db: Session = Depends(get_db)):
    """
    특정 기사의 상세 정보 (배경지식, 키워드 포함) 반환
    """
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article or article.status != ArticleStatus.PROCESSED:
        raise HTTPException(status_code=404, detail="해당 기사를 찾을 수 없습니다.")
    
    enriched_data = db.query(EnrichedArticle).filter(EnrichedArticle.article_id == article_id).first()

    # ArticleDetailSchema에 맞는 데이터 구성
    return ArticleDetailSchema(
        id=article.id,
        title=article.title,
        description=article.description,
        category=article.category,
        published_at=article.published_at,
        url=article.url,
        background=enriched_data.background if enriched_data and enriched_data.background else None,
        keywords=enriched_data.keywords if enriched_data and enriched_data.keywords else [],
        related_statistics=enriched_data.related_statistics if enriched_data and enriched_data.related_statistics else [],
        statistics_data=enriched_data.statistics_data if enriched_data and enriched_data.statistics_data else [],
        images=article.content.images if article.content and article.content.images else []
    )