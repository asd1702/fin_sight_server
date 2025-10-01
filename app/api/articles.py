from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, text
from typing import List
import logging
import asyncio

from ..database import get_db
from ..models import Article, EnrichedArticle, ArticleStatus
from ..schemas.article import ArticleSimpleSchema, ArticleDetailSchema, KeywordSchema

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/articles",
    tags=["articles"]
)

@router.get("/today", response_model=List[ArticleSimpleSchema])
async def get_today_news(db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    """
    '오늘의 뉴스'를 위한 API
    """
    try:
        # 파라미터 유효성 검사
        if skip < 0 or limit <= 0 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="잘못된 쿼리 파라미터입니다: skip은 0 이상, limit은 1-100 사이여야 합니다"
            )
        
        articles = db.query(Article)\
                    .filter(Article.status == ArticleStatus.PROCESSED)\
                    .order_by(Article.published_at.desc())\
                    .offset(skip)\
                    .limit(limit)\
                    .all()
        
        return articles
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_today_news: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="데이터베이스 연결 오류가 발생했습니다"
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_today_news: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다"
        )

@router.get("/category/{category}", response_model=List[ArticleSimpleSchema])
async def get_news_by_category(category: str, db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    """
    카테고리별 뉴스 목록 반환
    """
    try:
        # 파라미터 유효성 검사
        if not category or len(category.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="카테고리 파라미터는 필수이며 빈 값일 수 없습니다"
            )
        
        if skip < 0 or limit <= 0 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="잘못된 쿼리 파라미터입니다: skip은 0 이상, limit은 1-100 사이여야 합니다"
            )
        
        articles = db.query(Article)\
                    .filter(Article.status == ArticleStatus.PROCESSED, Article.category == category)\
                    .order_by(Article.published_at.desc())\
                    .offset(skip)\
                    .limit(limit)\
                    .all()
        
        if not articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"'{category}' 카테고리의 기사를 찾을 수 없습니다"
            )
        
        return articles
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_news_by_category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="데이터베이스 연결 오류가 발생했습니다"
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_news_by_category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다"
        )

@router.get("/search", response_model=List[ArticleSimpleSchema])
async def search_articles(q: str, db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    """
    키워드/해시태그 검색 API
    - 제목(title), 설명(description)은 부분 일치(ILIKE)
    - 해시태그(JSONB 배열)는 부분 일치: jsonb_array_elements_text + ILIKE
      (hashtags가 NULL일 수 있어 COALESCE로 가드)
    """
    try:
        # 파라미터 유효성 검사
        if not q or len(q.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="q 파라미터는 필수이며 빈 값일 수 없습니다"
            )
        if skip < 0 or limit <= 0 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="잘못된 쿼리 파라미터입니다: skip은 0 이상, limit은 1-100 사이여야 합니다"
            )

        pattern = f"%{q.strip()}%"

        # 해시태그 부분 일치 EXISTS 절 (스키마-테이블: articles.articles)
        hashtags_exists = text(
            """
            EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(COALESCE(articles.articles.hashtags, '[]'::jsonb)) AS tag
                WHERE tag ILIKE :pattern
            )
            """
        )

        query = (
            db.query(Article)
            .filter(
                Article.status == ArticleStatus.PROCESSED,
                or_(
                    Article.title.ilike(pattern),
                    Article.description.ilike(pattern),
                    hashtags_exists,
                ),
            )
            .order_by(Article.published_at.desc())
            .offset(skip)
            .limit(limit)
        )

        # text 절 바인딩 파라미터 주입
        articles = query.params(pattern=pattern).all()
        return articles

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in search_articles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="데이터베이스 연결 오류가 발생했습니다"
        )
    except Exception as e:
        logger.error(f"Unexpected error in search_articles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다"
        )

@router.get("/{article_id}", response_model=ArticleDetailSchema)
async def get_article_detail(article_id: int, db: Session = Depends(get_db)):
    """
    특정 기사의 상세 정보 (배경지식, 키워드 포함) 반환
    """
    try:
        # 파라미터 유효성 검사
        if article_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="기사 ID는 양의 정수여야 합니다"
            )
        
        article = db.query(Article).filter(Article.id == article_id).first()
        
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"ID {article_id}인 기사를 찾을 수 없습니다"
            )
        
        if article.status != ArticleStatus.PROCESSED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"ID {article_id}인 기사가 아직 처리 중입니다"
            )
        
        enriched_data = db.query(EnrichedArticle).filter(EnrichedArticle.article_id == article_id).first()

        # ArticleDetailSchema에 맞는 데이터 구성
        return ArticleDetailSchema(
            id=article.id,
            title=article.title,
            description=article.description,
            category=article.category,
            published_at=article.published_at,
            url=article.url,
            background=enriched_data.background if enriched_data and enriched_data.background else [],
            keywords=enriched_data.keywords if enriched_data and enriched_data.keywords else [],
            hashtags=(enriched_data.hashtags if enriched_data and enriched_data.hashtags else (article.hashtags or [])),
            related_statistics=enriched_data.related_statistics if enriched_data and enriched_data.related_statistics else [],
            statistics_data=enriched_data.statistics_data if enriched_data and enriched_data.statistics_data else [],
            images=article.content.images if article.content and article.content.images else []
        )
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_article_detail: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="데이터베이스 연결 오류가 발생했습니다"
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_article_detail: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다"
        )