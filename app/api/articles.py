"""
기사 관련 API 엔드포인트 모듈

이 모듈은 기사 목록 조회, 카테고리 조회, 키워드 검색, 상세 조회와
관리자 전용 엔드포인트(소프트 삭제, 복구, 완전 삭제)를 제공합니다.

모든 핸들러는 DB 세션을 FastAPI 의존성(`get_db`)으로 주입받아 동작하며,
SQLAlchemy 예외는 적절한 HTTP 상태 코드로 매핑합니다.

주의: 관리자 인증은 간단한 헤더 기반 방식으로 구현되어 있으며,
개발 편의를 위해 `UNSAFE_ADMIN_MODE` 환경변수에 따라 우회될 수 있습니다.
실 서비스에서는 더 강력한 인증/인가 방식을 적용할 예정입니다.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, text
from typing import List
import logging
import asyncio
from datetime import datetime, timedelta, timezone
import os

from ..database import get_db
from ..models import Article, EnrichedArticle, ArticleStatus
from ..schemas.article import ArticleSimpleSchema, ArticleDetailSchema, KeywordSchema

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/articles",
    tags=["articles"],
)


# --- 관리자 보호용 간단 헤더 기반 인증 ---
# 환경변수 ADMIN_API_KEY로 보호하고, 개발용으로 UNSAFE_ADMIN_MODE 우회 옵션 존재
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
UNSAFE_ADMIN_MODE = str(os.getenv("UNSAFE_ADMIN_MODE", "")).lower() in ("1", "true", "yes", "on")

def require_admin(x_admin_key: str | None = Header(default=None, alias="X-ADMIN-KEY")):
    """관리자 전용 엔드포인트 보호용 의존성 함수.

    개발 편의를 위해 `UNSAFE_ADMIN_MODE`가 활성화되면 인증을 우회합니다.
    프로덕션에서는 이 우회 모드를 사용하지 마세요.
    """
    # 임시 우회(개발 전용) - 운영 환경에서는 비활성화 권장
    if UNSAFE_ADMIN_MODE:
        logger.warning("UNSAFE_ADMIN_MODE enabled: bypassing admin authentication for admin endpoints")
        return True
    if not ADMIN_API_KEY:
        # 관리 키가 구성되지 않은 경우 기본적으로 접근 차단
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin API not configured")
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return True


@router.get("/today", response_model=List[ArticleSimpleSchema])
async def get_today_news(db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    """최근 처리된('PROCESSED') 기사 중 최신 순으로 목록을 반환합니다.

    파라미터 검증을 수행하며, 잘못된 파라미터는 400으로 응답합니다.
    DB 오류는 500으로 매핑합니다.
    """
    try:
        # 파라미터 유효성 검사
        if skip < 0 or limit <= 0 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="잘못된 쿼리 파라미터입니다: skip은 0 이상, limit은 1-100 사이여야 합니다",
            )

        articles = (
            db.query(Article)
            .filter(Article.status == ArticleStatus.PROCESSED, Article.is_deleted == False)
            .order_by(Article.published_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        return articles

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_today_news: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="데이터베이스 연결 오류가 발생했습니다",
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_today_news: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다",
        )


@router.get("/category/{category}", response_model=List[ArticleSimpleSchema])
async def get_news_by_category(category: str, db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    """특정 카테고리에 속하는 기사 목록을 반환합니다."""
    try:
        # 파라미터 유효성 검사
        if not category or len(category.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="카테고리 파라미터는 필수이며 빈 값일 수 없습니다",
            )

        if skip < 0 or limit <= 0 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="잘못된 쿼리 파라미터입니다: skip은 0 이상, limit은 1-100 사이여야 합니다",
            )

        articles = (
            db.query(Article)
            .filter(
                Article.status == ArticleStatus.PROCESSED,
                Article.is_deleted == False,
                Article.category == category,
            )
            .order_by(Article.published_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        if not articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{category}' 카테고리의 기사를 찾을 수 없습니다",
            )

        return articles

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_news_by_category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="데이터베이스 연결 오류가 발생했습니다",
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_news_by_category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다",
        )


@router.get("/search", response_model=List[ArticleSimpleSchema])
async def search_articles(q: str, db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    """제목/설명/해시태그를 대상으로 부분 일치(ILIKE) 검색을 수행합니다."""
    try:
        # 파라미터 유효성 검사
        if not q or len(q.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="q 파라미터는 필수이며 빈 값일 수 없습니다",
            )
        if skip < 0 or limit <= 0 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="잘못된 쿼리 파라미터입니다: skip은 0 이상, limit은 1-100 사이여야 합니다",
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
                Article.is_deleted == False,
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
            detail="데이터베이스 연결 오류가 발생했습니다",
        )
    except Exception as e:
        logger.error(f"Unexpected error in search_articles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다",
        )


@router.get("/{article_id}", response_model=ArticleDetailSchema)
async def get_article_detail(article_id: int, db: Session = Depends(get_db)):
    """특정 기사(기사ID)에 대한 상세 정보를 반환합니다.

    상세 정보에는 EnrichedArticle 테이블의 추가 메타(배경 지식, 키워드 등)를
    병합하여 반환합니다. DB 조회 결과에 따라 적절한 HTTP 상태 코드를 반환합니다.
    """
    try:
        # 파라미터 유효성 검사
        if article_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="기사 ID는 양의 정수여야 합니다",
            )

        article = db.query(Article).filter(Article.id == article_id, Article.is_deleted == False).first()

        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ID {article_id}인 기사를 찾을 수 없습니다",
            )

        if article.status != ArticleStatus.PROCESSED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"ID {article_id}인 기사가 아직 처리 중입니다",
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
            images=article.content.images if article.content and article.content.images else [],
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_article_detail: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="데이터베이스 연결 오류가 발생했습니다",
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_article_detail: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다",
        )



# ---------------- Admin endpoints ----------------
@router.delete("/admin/{article_id}", status_code=204)
async def admin_soft_delete_article(
    article_id: int,
    reason: str | None = None,
    lock_hours: int = 24,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """관리자 전용: 소프트 삭제(플래그 처리) 수행.

    삭제 사유, 삭제자 및 잠금(삭제 이후 일정 시간 동안 완전 삭제 금지) 정보를 기록합니다.
    """
    if article_id <= 0:
        raise HTTPException(status_code=400, detail="유효하지 않은 ID")
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="기사 없음")
    if article.is_deleted:
        return
    now = datetime.now(timezone.utc)
    article.is_deleted = True
    article.deleted_at = now
    article.delete_reason = reason
    article.deleted_by = "admin"
    article.delete_lock_until = now + timedelta(hours=max(0, lock_hours))
    db.add(article)
    db.commit()


@router.post("/admin/{article_id}/restore", status_code=204)
async def admin_restore_article(
    article_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """관리자 전용: 소프트 삭제된 기사를 복구합니다."""
    if article_id <= 0:
        raise HTTPException(status_code=400, detail="유효하지 않은 ID")
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="기사 없음")
    if not article.is_deleted:
        return
    article.is_deleted = False
    article.deleted_at = None
    article.delete_reason = None
    article.deleted_by = None
    article.delete_lock_until = None
    db.add(article)
    db.commit()


@router.delete("/admin/{article_id}/purge", status_code=204)
async def admin_purge_article(
    article_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """관리자 전용: 영구 삭제(하드 삭제). 삭제 잠금(lock)이 남아있으면 거부됩니다."""
    if article_id <= 0:
        raise HTTPException(status_code=400, detail="유효하지 않은 ID")
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return
    # 락 시간이 남아있으면 삭제 금지
    now = datetime.now(timezone.utc)
    if article.delete_lock_until and article.delete_lock_until > now:
        raise HTTPException(status_code=409, detail="락 시간이 지나야 영구 삭제 가능")
    # 하드 삭제 (관계에 delete-orphan 설정되어 있음)
    db.delete(article)
    db.commit()