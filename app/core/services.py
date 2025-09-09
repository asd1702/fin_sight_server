import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from bs4 import BeautifulSoup
from dateutil.parser import parse

from ..models import (
    Article, 
    ArticleContent, 
    EnrichedArticle, 
    ArticleStatus,
)

from ..models.statistic_model.statistic import (
    Indicator, Observation
)
from logs.logging_config import get_logger
logger = get_logger(__name__)


class DatabaseError(Exception):
    """데이터베이스 관련 오류"""
    pass


class ValidationError(Exception):
    """데이터 검증 오류"""
    pass

def create_article(db: Session, title: str, url: str, description: str, published_at: str, content: str, images: list[str] = None) -> Article | None:
    if not title or not url or not content:
        raise ValidationError("title, url, content는 필수 입력값입니다.")
    if len(content.strip()) < 50:
        return None
    
    try:
        if db.query(Article).filter(Article.url == url).first():
            logger.debug(f"중복된 URL 발견, 건너뜀: {url}")
            return None
        
        try:
            parsed_date = parse(published_at)
        except (ValueError, TypeError):
            raise ValidationError(f"날짜 형식이 올바르지 않습니다: {published_at}")
    
        new_article = Article(
            title=title.strip(),
            url=url.strip(),
            description=BeautifulSoup(description, "html.parser").get_text(strip=True),
            published_at=parsed_date,
            status=ArticleStatus.PENDING
        )
        new_article.content = ArticleContent(
            content=content.strip(),
            images=images if images else []
        )

        db.add(new_article)
        db.commit()
        db.refresh(new_article)

        logger.info(f"신규 기사 저장 완료: (ID: {new_article.id}) {new_article.title}")
        return new_article
    
    except SQLAlchemyError as e:
        logger.error(f"데이터베이스 오류 발생 (URL: {url}): {e}")
        db.rollback()
        raise DatabaseError(f"기사 저장 중 데이터베이스 오류가 발생했습니다.")
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"기사 저장 중 예상치 못한 오류 발생 (URL: {url}): {e}")
        db.rollback()
        raise

def get_pending_articles(db: Session) -> list[Article]:
    """
    처리가 필요한 기사들을 반환합니다.
    - PENDING: 아직 처리되지 않은 신규 기사
    - FAILED: 이전에 실패했던 기사 (재시도)
    """
    return db.query(Article).filter(
        Article.status.in_([ArticleStatus.PENDING, ArticleStatus.FAILED])
    ).all()

def get_article_by_id(db: Session, article_id: int) -> Article | None:
    return db.query(Article).filter(Article.id == article_id).first()

def update_article_status(db: Session, article: Article, status: ArticleStatus):
    try:
        article.status = status
        db.commit()
        logger.info(f"기사 ID {article.id}의 상태를 {status.value}(으)로 업데이트.")
    except SQLAlchemyError as e:
        logger.error(f"기사 ID {article.id} 상태 업데이트 중 오류 발생: {e}")
        db.rollback()
        raise DatabaseError("기사 상태 업데이트 중 데이터베이스 오류가 발생했습니다.")

def save_enriched_data_and_cleanup(db: Session, article: Article, analysis_result: dict):
    """
    LLM의 통합 분석 결과를 EnrichedArticle 테이블에 저장하고 기사 상태를 업데이트합니다.
    """
    try:
        # analysis_result 딕셔너리에서 직접 데이터를 추출
        background_data = analysis_result.get("background_knowledge")
        keywords_data = analysis_result.get("keywords")
        category_data = analysis_result.get("category", "기타")

        # enriched_articles 테이블에 저장
        new_enriched = EnrichedArticle(
            article_id=article.id,
            background=background_data,
            keywords=keywords_data,
            category=category_data
        )
        db.add(new_enriched)

        # articles 테이블의 상태와 카테고리 업데이트
        article.category = category_data
        article.status = ArticleStatus.PROCESSED
    
        db.commit()
        logger.info(f"기사 ID {article.id}의 분석 결과 저장 및 정리 완료")
    
    except SQLAlchemyError as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 DB 오류 발생: {e}")
        db.rollback()
        raise DatabaseError("분석 결과 저장 중 데이터베이스 오류가 발생했습니다.")
    except Exception as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 예상치 못한 오류 발생: {e}")
        db.rollback()
        raise

def get_contextual_statistics_for_article(
    db: Session, 
    indicator_ids: list[str], 
    article_published_at: datetime
) -> list[dict]:
    """
    기사 발행일을 기준으로, 각 지표의 주기에 맞춰 동적으로 기간을 설정하여
    시계열 데이터를 조회하고 프론트엔드에 전달할 형태로 가공합니다.
    """
    if not indicator_ids:
        return []

    # 1. 요청된 ID에 해당하는 지표 메타데이터를 한 번에 조회
    indicators = db.query(Indicator).filter(Indicator.indicator_id.in_(indicator_ids)).all()
    indicator_meta_map = {ind.indicator_id: ind for ind in indicators}
    
    results = []
    end_date = article_published_at.date()

    for indicator_id in indicator_ids:
        meta = indicator_meta_map.get(indicator_id)
        if not meta:
            logger.warning(f"ID '{indicator_id}'에 해당하는 지표를 DB에서 찾을 수 없습니다.")
            continue

        # 2. 지표의 주기에 따라 조회할 시작 날짜를 동적으로 계산
        frequency = meta.frequency
        if frequency == 'D':  # 일별 데이터 (예: KOSPI) -> 최근 3개월
            start_date = end_date - relativedelta(months=3)
        elif frequency == 'M': # 월별 데이터 (예: CPI) -> 최근 2년 (24개월)
            start_date = end_date - relativedelta(months=24)
        elif frequency == 'Q': # 분기별 데이터 (예: GDP) -> 최근 5년
            start_date = end_date - relativedelta(years=5)
        else: # 주기가 없거나 예상 못한 경우 -> 기본값 1년
            start_date = end_date - relativedelta(years=1)
            logger.info(f"지표 ID '{indicator_id}'의 주기가 '{frequency}'이므로 기본 기간(1년)을 적용합니다.")

        # 3. 계산된 기간으로 시계열 데이터(Observation) 조회
        observations = (
            db.query(Observation)
            .filter(
                Observation.indicator_id == indicator_id,
                Observation.date.between(start_date, end_date),
            )
            .order_by(Observation.date.asc())
            .all()
        )
        
        # 4. 프론트엔드에서 사용하기 좋은 형태로 최종 데이터 구조화
        results.append({
            "indicator_id": meta.indicator_id,
            "name": meta.name,
            "unit": meta.unit,
            "notes": meta.notes,
            "frequency": meta.frequency,
            "observations": [
                {"date": obs.date.isoformat(), "value": obs.value}
                for obs in observations
            ]
        })
        
    return results


def save_enriched_data_and_cleanup(
    db: Session, 
    article: Article, 
    analysis_result: dict,
    statistics_data: list[dict]
):
    """
    LLM의 분석 결과와, 동적으로 조회된 시계열 데이터를 EnrichedArticle 테이블에 저장합니다.
    """
    try:
        background_data = analysis_result.get("background_knowledge")
        keywords_data = analysis_result.get("keywords")
        category_data = analysis_result.get("category", "기타")
        related_stats_meta = analysis_result.get("related_statistics")

        # enriched_articles 테이블에 저장할 객체 생성
        # (수정) statistics_data 필드 추가
        new_enriched = EnrichedArticle(
            article_id=article.id,
            background=background_data,
            keywords=keywords_data,
            category=category_data,
            related_statistics=related_stats_meta,
            statistics_data=statistics_data  # 새로 가공된 시계열 데이터 저장
        )
        db.add(new_enriched)

        # articles 테이블의 상태와 카테고리 업데이트
        article.category = category_data
        article.status = ArticleStatus.PROCESSED
    
        db.commit()
        logger.info(f"기사 ID {article.id}의 분석 결과 및 통계 데이터 저장 완료")
    
    except SQLAlchemyError as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 DB 오류 발생: {e}")
        db.rollback()
        raise DatabaseError("분석 결과 저장 중 데이터베이스 오류가 발생했습니다.")
    except Exception as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 예상치 못한 오류 발생: {e}")
        db.rollback()
        raise